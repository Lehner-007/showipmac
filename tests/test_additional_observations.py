import unittest
from threading import Event
from unittest.mock import patch
import test_core
from test_core import NET, observation
from core import scan, network_details

class AdditionalTests(unittest.TestCase):
    setUp=test_core.CoreTests.setUp
    tearDown=test_core.CoreTests.tearDown
    def test_conflict_same_scan_not_dhcp_history(self):
        a=observation();b=observation(mac='00:11:22:33:44:77')
        self.store.commit_scan(NET,[a]);self.store.commit_scan(NET,[b])
        devices=self.store.devices(NET.scope)
        self.assertFalse(any(d['conflicts'] for d in devices))
        self.assertEqual(next(d for d in devices if d['mac']==[b['mac']])['assignment_changes'][0]['before'],[a['mac']])
        self.assertEqual(len(devices),2)  # no automatic identity merge
        self.store.commit_scan(NET,[a,b])
        self.assertTrue(all(d['conflicts'] for d in self.store.devices(NET.scope)))
        self.assertEqual(self.store.devices(NET.scope)[0]['conflicts'][0]['macs'],[a['mac'],b['mac']])
    def test_names_changes_missing_and_scope(self):
        self.store.commit_scan(NET,[observation()]);d=self.store.devices(NET.scope)[0];self.store.rename(d['id'],'Printer')
        changed=observation();changed['hostname']='renamed'
        self.store.commit_scan(NET,[changed]);d=self.store.devices(NET.scope)[0]
        self.assertEqual(d['name'],'Printer');self.assertEqual(d['changes']['hostname'],{'before':['example'],'after':['renamed']})
        self.store.commit_scan(NET,[changed]);self.assertFalse(self.store.devices(NET.scope)[0]['changed'])
        self.store.commit_scan(NET,[]);self.store.commit_scan(NET,[])
        self.assertEqual(self.store.devices(NET.scope)[0]['missing_scans'],2)
    def test_sources_and_name_source_preserved(self):
        cached=observation();new=observation('192.0.2.3','00:11:22:33:44:77')
        with patch('core.discover_networks',return_value=[NET]),patch('core.neighbors',side_effect=[[cached],[dict(cached),new]]),patch('core.resolve_hostname',return_value=('printer.local','mdns')):
            records,_=scan(NET,Event(),active=False)
        self.assertEqual(next(o for o in records if o['ip']=='192.0.2.2')['source'],'cache')
        self.assertEqual(next(o for o in records if o['ip']=='192.0.2.3')['source'],'scan_neighbor')
        self.store.commit_scan(NET,records)
        obs=next(d for d in self.store.devices(NET.scope) if not d['is_local'])['history'][0]
        self.assertEqual(obs['name_source'],'mdns');self.assertTrue(obs['observed_at'])
    def test_route_dns_queries_are_local_only(self):
        with patch('core.command',side_effect=['[{"dst":"default","gateway":"192.0.2.1"}]','[]','Link test0\n DNS Servers: 192.0.2.1']),patch('core.shutil.which',return_value='/usr/bin/resolvectl'):
            result=network_details(NET)
        self.assertEqual(result['routes'][0]['gateway'],'192.0.2.1');self.assertEqual(result['dns_source'],'resolvectl')

class AdditionalGUITests(unittest.TestCase):
    def setUp(self):
        import test_building_blocks as blocks
        self.blocks=blocks
        blocks.SharedTests.setUp(self)
    def tearDown(self):self.blocks.SharedTests.tearDown(self)
    def widgets(self,widget):
        yield widget
        child=widget.get_first_child()
        while child:
            yield from self.widgets(child)
            child=child.get_next_sibling()
    def test_details_and_network_metadata_de_en(self):
        from gi.repository import Gtk
        app=self.app
        for code in ('de','en'):
            app.rt.settings['language']=code
            obs=dict(mac='00:11:22:33:44:66',ip='192.0.2.2',interface='qa0',hostname='printer',evidence='STALE',source='cache',name_source='nss',observed_at='2026-10-06T10:00:00+00:00')
            app.store.commit_scan(self.blocks.NET,[obs,dict(obs,mac='00:11:22:33:44:77')]);app.network_changed()
            app.listbox.select_row(app.listbox.get_row_at_index(0));app.details()
            windows=[w for w in Gtk.Window.get_toplevels() if w.get_title()==app.text('details')]
            self.assertTrue(windows)
            win=windows[-1]
            views=[w for w in self.widgets(win) if isinstance(w,Gtk.TextView)]
            buf=views[0].get_buffer();content=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False)
            self.assertIn(app.text('source_cache'),content);self.assertIn(app.text('source_nss'),content)
            self.assertIn(app.text('possible_conflict'),content);self.assertIn('06.10.2026',content)
            win.destroy()
            data=dict(routes=[dict(family='4',destination='default',gateway='192.0.2.254',table='main')],dns='DNS: 192.0.2.253',dns_source='resolvectl',errors=[])
            with patch('core.network_details',return_value=data):
                network_window=app.network_info()
                self.blocks.wait_until(lambda: any(isinstance(w,Gtk.Label) and '192.0.2.254' in w.get_label() for w in self.widgets(network_window)))
                labels=' '.join(w.get_label() for w in self.widgets(network_window) if isinstance(w,Gtk.Label))
                self.assertIn(app.text('dns_note'),labels)
                network_window.destroy()
