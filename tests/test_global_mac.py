"""Global MAC recognition with persisted interface-specific observations."""
import unittest
import test_core
from core import Network, Store

class GlobalMacTests(unittest.TestCase):
    setUp = test_core.CoreTests.setUp
    tearDown = test_core.CoreTests.tearDown

    def scan(self, interface, mac='AA:BB:CC:DD:EE:01', ip='10.0.0.50', virtual=False):
        address = '192.168.122.1/24' if virtual else '10.0.0.1/24'
        net = Network(interface, (address,), '', virtual)
        self.store.commit_scan(net, [dict(mac=mac, ip=ip, interface=interface,
                                         hostname='same-host', evidence='REACHABLE')])
        return self.store.devices(net.scope)[0]

    def test_two_lan_interfaces_after_reopen(self):
        first = self.scan('enp16s0')
        self.assertEqual(first['status'], 'new')
        self.store.rename(first['id'], 'Desk')
        self.store.close()
        self.store = Store(self.path/'devices.sqlite3')
        second = self.scan('enp7s0')
        self.assertEqual(second['status'], 'known')
        self.assertEqual(second['id'], first['id'])
        self.assertEqual(second['name'], 'Desk')
        self.assertEqual(second['first_seen'], first['first_seen'])
        self.assertEqual({o['interface'] for o in second['history']}, {'enp16s0','enp7s0'})

    def test_lan_to_wlan(self):
        first = self.scan('enp16s0')
        second = self.scan('wlp15s0', mac=' aa-bb-cc-dd-ee-01 ')
        self.assertEqual(second['status'], 'known')
        self.assertEqual(second['id'], first['id'])

    def test_changed_ip(self):
        first = self.scan('enp16s0')
        second = self.scan('enp7s0', ip='10.0.0.60')
        self.assertEqual(second['status'], 'known')
        self.assertEqual(second['id'], first['id'])
        self.assertEqual(second['ipv4'], ['10.0.0.60'])
        self.assertEqual({o['ip'] for o in second['history']}, {'10.0.0.50','10.0.0.60'})

    def test_distinct_local_macs_not_merged_by_ip_or_hostname(self):
        devices = [self.scan(interface, mac) for interface,mac in
                   [('enp16s0','fc:9d:05:65:e4:14'),('enp7s0','fc:9d:05:65:e4:15'),
                    ('wlp15s0','44:f7:9f:3b:dd:af')]]
        self.assertEqual(len({d['id'] for d in devices}), 3)
        self.assertTrue(all(d['status']=='new' for d in devices))

    def test_virtual_device_stays_separate(self):
        physical = self.scan('enp16s0')
        virtual = self.scan('virbr0', '52:54:00:12:34:56', '192.168.122.50', True)
        self.assertNotEqual(physical['id'], virtual['id'])
        self.assertEqual(virtual['status'], 'new')
        self.assertEqual(self.scan('virbr0', '52:54:00:12:34:56', '192.168.122.60', True)['status'], 'known')

    def test_legacy_duplicates_keep_names_and_history(self):
        first = self.scan('enp16s0')
        self.store.rename(first['id'], 'LAN name')
        with self.store.db:
            self.store.db.execute('INSERT INTO devices VALUES(?,?,?,?)',
                                 ('legacy','Other name',first['first_seen'],first['last_seen']))
            self.store.db.execute('''INSERT INTO observations (device,scope,mac,ip,interface,hostname,evidence,first_seen,last_seen,scan,first_scan) SELECT 'legacy',
                'enp7s0|10.0.0.0/24',mac,ip,'enp7s0',hostname,evidence,
                first_seen,last_seen,scan,first_scan FROM observations LIMIT 1''')
        second = self.scan('enp7s0')
        self.assertEqual(second['status'], 'known')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM devices').fetchone()[0], 1)
        self.assertEqual({second['name'], *second['other_names']}, {'LAN name','Other name'})
        self.assertEqual(len(second['history']), 2)
