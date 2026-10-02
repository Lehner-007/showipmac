"""Eleven-device repeat-scan regression including persisted state."""
import unittest
import test_core
from core import Network, Store
from presentation import scan_summary

class RecognitionTests(unittest.TestCase):
    setUp = test_core.CoreTests.setUp
    tearDown = test_core.CoreTests.tearDown

    def fixture(self):
        net=Network('lan0',('192.0.2.1/24','2001:db8:1::1/64'),'00:aa:bb:cc:00:01',False)
        observations=[{'mac':f'00:aa:bb:cc:00:{i:02x}','ip':f'192.0.2.{i}',
                       'interface':'lan0','hostname':'','evidence':'REACHABLE'} for i in range(1,12)]
        return net,observations

    def test_eleven_identical_devices_twice(self):
        net,observations=self.fixture()
        self.store.commit_scan(net,observations)
        first=self.store.devices(net.scope)
        self.assertEqual(scan_summary(first),{'found':11,'new':11,'known':0})
        self.store.rename(first[0]['id'],'My device')
        first_by_id={d['id']:d for d in first}
        self.store.commit_scan(net,observations)
        second=self.store.devices(net.scope)
        self.assertEqual(scan_summary(second),{'found':11,'new':0,'known':11})
        self.assertEqual({d['id'] for d in second},set(first_by_id))
        for device in second:
            self.assertEqual(device['first_seen'],first_by_id[device['id']]['first_seen'])
            self.assertGreaterEqual(device['last_seen'],first_by_id[device['id']]['last_seen'])
        self.assertIn('My device',[d['name'] for d in second])

    def test_eleven_after_reopening_and_uppercase_mac(self):
        net,observations=self.fixture()
        self.store.commit_scan(net,observations)
        self.store.close()
        self.store=Store(self.path/'devices.sqlite3')
        for obs in observations:obs['mac']=obs['mac'].upper()
        self.store.commit_scan(net,observations)
        self.assertEqual(scan_summary(self.store.devices(net.scope)),{'found':11,'new':0,'known':11})

    def test_same_lan_with_changed_ipv6_prefix(self):
        net,observations=self.fixture()
        self.store.commit_scan(net,observations)
        first=self.store.devices(net.scope)
        self.store.rename(first[0]['id'],'My device')
        newnet=Network('lan0',('192.0.2.1/24','2001:db8:2::1/64'),net.mac,False)
        self.store.commit_scan(newnet,observations)
        second=self.store.devices(newnet.scope)
        self.assertEqual(scan_summary(second),{'found':11,'new':0,'known':11})
        self.assertEqual({d['id'] for d in second},{d['id'] for d in first})
        self.assertIn('My device',[d['name'] for d in second])

    def test_other_lans_and_ipv6_only_remain_separate(self):
        from core import recognition_scope
        self.assertNotEqual(recognition_scope('lan0|192.0.2.0/24|2001:db8::/64'),recognition_scope('lan1|192.0.2.0/24|2001:db8::/64'))
        self.assertNotEqual(recognition_scope('lan0|192.0.2.0/24'),recognition_scope('lan0|198.51.100.0/24'))
        self.assertNotEqual(recognition_scope('lan0|2001:db8:1::/64'),recognition_scope('lan0|2001:db8:2::/64'))

    def test_missing_and_reappearing_across_prefix_change(self):
        net,observations=self.fixture()
        self.store.commit_scan(net,observations)
        newnet=Network('lan0',('192.0.2.1/24','2001:db8:2::1/64'),net.mac,False)
        self.store.commit_scan(newnet,observations[:5])
        devices=self.store.devices(newnet.scope)
        self.assertEqual(scan_summary(devices),{'found':5,'new':0,'known':5})
        self.assertEqual(sum(d['status']=='missing' for d in devices),6)
        self.store.commit_scan(newnet,observations)
        self.assertEqual(scan_summary(self.store.devices(newnet.scope)),{'found':11,'new':0,'known':11})

    def test_mac_whitespace_hyphen_case_normalized(self):
        net,observations=self.fixture()
        self.store.commit_scan(net,observations)
        for obs in observations:obs['mac']='  '+obs['mac'].upper().replace(':','-')+'  '
        self.store.commit_scan(net,observations)
        self.assertEqual(scan_summary(self.store.devices(net.scope)),{'found':11,'new':0,'known':11})
