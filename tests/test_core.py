import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import *
from runtime import Runtime

NET = Network('test0', ('192.0.2.1/27', '2001:db8::1/64'), '00:11:22:33:44:55', True)

def observation(ip='192.0.2.2', mac='00:11:22:33:44:66'):
    return dict(ip=ip, mac=mac, interface='test0', hostname='example', evidence='REACHABLE')

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.path = Path(self.temp.name)
        self.store = Store(self.path/'devices.sqlite3')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_networks_use_real_prefixes_exclude_loopback_down(self):
        rows = [dict(ifname='test0', flags=['UP'], operstate='UP', address=NET.mac,
                     addr_info=[dict(family='inet',local='192.0.2.1',prefixlen=27),
                                dict(family='inet6',local='2001:db8::1',prefixlen=64)]),
                dict(ifname='lo',flags=['UP','LOOPBACK'],operstate='UP'),
                dict(ifname='off',flags=[],operstate='DOWN')]
        nets = networks_from_json(rows)
        self.assertEqual(len(nets),1)
        self.assertIn('192.0.2.0/27',nets[0].networks)
        self.assertFalse(nets[0].contains('192.0.2.80'))
        self.assertFalse(nets[0].contains('ff02::1'))

    def test_ipv4_ipv6_merge(self):
        self.store.commit_scan(NET,[observation(),observation('2001:db8::2')])
        devices=self.store.devices(NET.scope)
        self.assertEqual(len(devices),1)
        self.assertEqual(devices[0]['status'],'new')
        self.assertEqual(devices[0]['ipv6'],['2001:db8::2'])

    def test_changed_ip_keeps_name_and_history(self):
        self.store.commit_scan(NET,[observation()])
        device=self.store.devices(NET.scope)[0]
        self.store.rename(device['id'],'Printer')
        self.store.commit_scan(NET,[observation('192.0.2.3')])
        device=self.store.devices(NET.scope)[0]
        self.assertEqual(device['name'],'Printer')
        self.assertEqual(device['status'],'known')
        self.assertEqual(device['ipv4'],['192.0.2.3'])
        self.assertEqual(len(device['history']),2)
        self.assertTrue(device['changed'])

    def test_missing_reappearing(self):
        self.store.commit_scan(NET,[observation()])
        self.store.commit_scan(NET,[])
        self.assertEqual(self.store.devices(NET.scope)[0]['status'],'missing')
        self.store.commit_scan(NET,[observation()])
        self.assertEqual(self.store.devices(NET.scope)[0]['status'],'known')

    def test_scope_isolation(self):
        self.store.commit_scan(NET,[observation()])
        other=Network('test1',NET.addresses,NET.mac,True)
        self.store.commit_scan(other,[])
        self.assertEqual(self.store.devices(NET.scope)[0]['status'],'new')
        self.assertEqual(self.store.devices(other.scope),[])

    def test_bad_mac_and_foreign_address_excluded(self):
        self.store.commit_scan(NET,[observation(mac=''),observation('198.51.100.2'), observation(mac='ff:ff:ff:ff:ff:ff')])
        self.assertEqual(self.store.devices(NET.scope),[])

    def test_changed_private_mac_not_ip_merged(self):
        self.store.commit_scan(NET,[observation(mac='02:11:22:33:44:66')])
        self.store.commit_scan(NET,[observation(mac='02:11:22:33:44:77')])
        devices=self.store.devices(NET.scope)
        self.assertEqual(len(devices),2)
        self.assertTrue(all(d['private_mac'] for d in devices))
        self.assertEqual({d['status'] for d in devices},{'missing','new'})

    def test_manual_merge_and_future_recognition(self):
        self.store.commit_scan(NET,[observation(),observation('192.0.2.3','00:11:22:33:44:77')])
        a,b=self.store.devices(NET.scope)
        self.store.rename(a['id'],'Linked')
        self.store.merge(a['id'],b['id'])
        self.store.commit_scan(NET,[observation('192.0.2.4','00:11:22:33:44:77')])
        devices=self.store.devices(NET.scope)
        self.assertEqual(len(devices),1)
        self.assertEqual(devices[0]['name'],'Linked')
        self.assertEqual(len(devices[0]['history']),3)

    def test_persistence(self):
        self.store.commit_scan(NET,[observation()])
        other=Store(self.path/'devices.sqlite3')
        self.assertEqual(len(other.devices(NET.scope)),1)
        other.close()

    def test_neighbor_filter(self):
        rows=[dict(dst='192.0.2.2',lladdr='00:11:22:33:44:66',state=['REACHABLE']),
              dict(dst='192.0.2.3',state=['FAILED']),
              dict(dst='198.51.100.1',lladdr='00:11:22:33:44:77',state=['STALE'])]
        with patch('core.command',return_value=json.dumps(rows)):
            self.assertEqual(len(neighbors(NET,threading.Event())),1)

    def test_cancel_process_fast(self):
        event=threading.Event()
        timer=threading.Timer(.15,event.set)
        timer.start()
        start=time.monotonic()
        with self.assertRaises(Cancelled):
            command([sys.executable,'-c','import time; time.sleep(15)'],event)
        self.assertLess(time.monotonic()-start,1)
        timer.join()

    def test_timeout_and_missing_tool(self):
        with self.assertRaises(DiscoveryError):
            command([sys.executable,'-c','import time; time.sleep(2)'],timeout=.1)
        with self.assertRaises(DiscoveryError):
            command(['showipmac-nonexistent-executable'])

    def test_no_gateway_probe(self):
        with patch('core.command',return_value='[{"dev":"test0","gateway":"192.0.2.30"}]') as run:
            probe(NET,'192.0.2.2',threading.Event())
        self.assertEqual(run.call_count,1)

    def test_scan_changed_network_aborts(self):
        with patch('core.discover_networks',return_value=[]):
            with self.assertRaises(DiscoveryError):
                scan(NET,threading.Event())

    def test_scan_no_ping_is_usable(self):
        with patch('core.discover_networks',return_value=[NET]), patch('core.neighbors',return_value=[]), patch('core.shutil.which',return_value=None), patch('core.command',return_value=''):
            observations,warnings=scan(NET,threading.Event())
        self.assertIn('no_ping',warnings)
        self.assertEqual(len(observations),2)

    def test_oui_longest_prefix_private_unknown(self):
        vendor=Vendors.parse(['Assignment,Organization Name\n001122,General\n0011223,Specific\n001122334,Exact\n'],'today')
        self.assertEqual(vendor.lookup('00:11:22:33:44:55'),'Exact')
        self.assertEqual(vendor.lookup('00:11:22:35:44:55'),'Specific')
        self.assertEqual(vendor.lookup('02:11:22:33:44:55'),'')
        self.assertEqual(vendor.lookup('00:99:22:33:44:55'),'')

    def test_bad_vendor_update_keeps_existing(self):
        dest=self.path/'vendors.json'
        dest.write_text('old')
        response=io.BytesIO(b'bad,data\n')
        with patch('core.urlopen',return_value=response),self.assertRaises(VendorUpdateError):
            Vendors.update(dest,threading.Event())
        self.assertEqual(dest.read_text(),'old')

    def test_csv_json_and_formula_escape(self):
        self.store.commit_scan(NET,[observation()])
        devices=self.store.devices(NET.scope)
        devices[0]['name']='=CMD()'
        export(self.path/'test.csv',devices,lambda s:s)
        with (self.path/'test.csv').open(encoding='utf-8-sig') as handle:
            rows=list(csv.reader(handle))
        self.assertEqual(rows[1][0],"'=CMD()")
        export(self.path/'test.json',devices,lambda s:s,'json')
        self.assertEqual(json.loads((self.path/'test.json').read_text())[0]['name'],'=CMD()')

    def test_config_corruption_preserved(self):
        settings=self.path/'settings.json'
        settings.write_text('{broken')
        rt=Runtime(self.path)
        self.assertIn('config_error',rt.warnings)
        rt.save()
        self.assertEqual(len(list(self.path.glob('settings.invalid.*.json'))),1)
        self.assertEqual(json.loads(settings.read_text())['config_version'],1)

    def test_language_fallback_and_validation(self):
        (self.path/'settings.json').write_text(json.dumps({'language':'nonexistent','max_hosts':-1}))
        rt=Runtime(self.path)
        self.assertEqual(rt.settings['language'],'en')
        self.assertEqual(rt.settings['max_hosts'],4096)
        self.assertEqual(rt.text('new'),'New')

    def test_manual_merge_across_interfaces(self):
        self.store.commit_scan(NET,[observation()])
        other=Network('test1',('198.51.100.1/28',),'00:11:22:33:44:88',True)
        obs=dict(ip='198.51.100.2',mac='00:11:22:33:44:99',interface='test1',hostname='',evidence='STALE')
        self.store.commit_scan(other,[obs])
        first=self.store.devices(NET.scope)[0]
        second=self.store.devices(other.scope)[0]
        self.store.merge(first['id'],second['id'])
        self.assertEqual(self.store.devices(other.scope)[0]['id'],first['id'])
        self.assertEqual({o['interface'] for o in self.store.devices(NET.scope)[0]['history']},{'test0','test1'})

    def test_large_network_not_silently_truncated(self):
        large=Network('test0',('10.0.0.1/8',),NET.mac,True)
        with patch('core.shutil.which',return_value='/mock/ping'),patch('core.discover_networks',return_value=[large]),patch('core.neighbors',return_value=[]),patch('core.command',return_value=''),patch('core.probe') as probe_mock:
            results,warnings=scan(large,threading.Event(),max_hosts=32)
        self.assertIn('large_network',warnings)
        self.assertEqual(probe_mock.call_count,0)

    def test_vendor_update_atomically_saved_and_cancelled(self):
        dest=self.path/'vendors.json'
        with patch('core.urlopen',side_effect=lambda *a,**k:io.BytesIO(b'Assignment,Organization Name\n001122,Example Inc\n')):
            vendor=Vendors.update(dest,threading.Event())
        self.assertEqual(vendor.lookup('00:11:22:33:44:55'),'Example Inc')
        self.assertTrue(dest.exists())
        saved=dest.read_bytes()
        event=threading.Event();event.set()
        with self.assertRaises(Cancelled):
            Vendors.update(dest,event)
        self.assertEqual(dest.read_bytes(),saved)

    def test_translation_keys_placeholders_match(self):
        import string
        languages=[json.loads((ROOT/'lang'/f'{lang}.json').read_text()) for lang in ('de','en')]
        self.assertEqual(set(languages[0]),set(languages[1]))
        fmt=string.Formatter()
        for key in languages[0]:
            self.assertEqual({f for _,f,_,_ in fmt.parse(languages[0][key]) if f}, {f for _,f,_,_ in fmt.parse(languages[1][key]) if f})

if __name__=='__main__':
    unittest.main()
