"""Regression tests for the user change list, version 0.2.0."""
import os
import time
import unittest
from datetime import datetime, timezone
from threading import Event
from unittest.mock import patch
import test_core
from test_core import NET, observation
from core import Network, network_label, network_options, resolve_hostname, scan
from presentation import cell_value, device_sort_key, local_time, scan_summary
from runtime import Runtime
from core import ROOT

# Reuse fixture lifecycle without duplicating inherited tests in discovery.
class ChangesTests(unittest.TestCase):
    setUp = test_core.CoreTests.setUp
    tearDown = test_core.CoreTests.tearDown

    def test_subnet_only_and_multi_subnet_selection(self):
        original = Network('any-interface', ('10.0.0.12/24', '10.7.0.9/23', '2001:db8::1/64'), NET.mac, True)
        choices = network_options([original])
        self.assertEqual([network_label(n) for n in choices], ['10.0.0.0/24', '10.7.0.0/23'])
        self.assertEqual(choices[0].addresses, original.addresses)
        self.assertFalse(choices[0].contains('10.7.0.12'))
        self.assertTrue(choices[0].contains('2001:db8::9'))
        v6 = Network('any-interface',('2001:db8::1/64',),NET.mac,True)
        self.assertEqual(network_options([v6]), [])

    def test_scan_choices_preserve_ipv4_virtual_lan_and_wifi(self):
        vnet = Network('vnet0', ('fe80::1/64',), NET.mac, True)
        bridge = Network('virbr0', ('192.168.122.1/24', 'fe80::2/64'), NET.mac, True)
        lan = Network('enp1s0', ('192.0.2.1/24',), NET.mac, False)
        wifi = Network('wlan0', ('198.51.100.1/24',), NET.mac, False)
        detected = [vnet, bridge, lan, wifi]
        self.assertEqual(network_options(detected), [bridge, lan, wifi])
        self.assertEqual(len(detected), 4)
        self.assertEqual(network_options([]), [])

    def test_local_host_not_duplicated_and_actual_hostname(self):
        with patch('core.discover_networks',return_value=[NET]),patch('core.neighbors',return_value=[]),patch('core.socket.gethostname',return_value='actual-host'):
            results,_ = scan(NET,Event(),active=False)
        self.store.commit_scan(NET, results)
        devices=self.store.devices(NET.scope)
        self.assertEqual(len(devices),1)
        self.assertTrue(devices[0]['is_local'])
        self.assertEqual(devices[0]['hostname'],['actual-host'])
        self.assertEqual(len(devices[0]['history']),2)

    def test_mdns_fallback_and_no_guess(self):
        with patch('core.shutil.which',return_value='/usr/bin/avahi-resolve-address'),patch('core.command',side_effect=['','192.0.2.2\tprinter.local\n']) as run:
            self.assertEqual(resolve_hostname('192.0.2.2','test0',Event()),'printer.local')
            self.assertEqual(run.call_args_list[1].args[0][0],'avahi-resolve-address')
        with patch('core.shutil.which',return_value=None),patch('core.command',return_value='192.0.2.9 wrong.local'):
            self.assertEqual(resolve_hostname('192.0.2.2','test0',Event()),'')
        with patch('core.shutil.which',return_value=None),patch('core.command',return_value='192.0.2.2 192.0.2.2'):
            self.assertEqual(resolve_hostname('192.0.2.2','test0',Event()),'')

    def test_ipv6_compact_and_full_history(self):
        self.store.commit_scan(NET,[observation('2001:db8::2'),observation('2001:db8::3')])
        d=self.store.devices(NET.scope)[0]
        rt=Runtime(self.path)
        self.assertEqual(cell_value(d,'ipv6',rt.text,'de'),'2 IPv6-Adressen')
        self.assertEqual({o['ip'] for o in d['history']},{'2001:db8::2','2001:db8::3'})

    def test_numeric_sort_all_visible_columns(self):
        rt=Runtime(self.path)
        devices=[{'ipv4':[ip]} for ip in ('192.0.2.100','192.0.2.9','192.0.2.20')]
        result=sorted(devices,key=lambda d:device_sort_key(d,'ipv4',rt.text,'de'))
        self.assertEqual([d['ipv4'][0] for d in result],['192.0.2.9','192.0.2.20','192.0.2.100'])
        for key in ('name','hostname','ipv6','mac','vendor','status','last_seen'):
            values={'name':'Desk','hostname':['host'],'ipv6':['2001:db8::1'],'mac':['00:11:22:33:44:55'],'vendor':['Vendor'],'status':'known','last_seen':'2026-01-01T12:00:00+00:00'}
            self.assertIsNotNone(device_sort_key(values,key,rt.text,'de'))

    def test_local_time_germany_winter_summer(self):
        old=os.environ.get('TZ')
        try:
            os.environ['TZ']='Europe/Berlin';time.tzset()
            self.assertEqual(local_time('2026-01-01T12:34:56+00:00'),'01.01.2026 13:34:56')
            self.assertEqual(local_time('2026-07-01T12:34:56+00:00'),'01.07.2026 14:34:56')
            self.assertEqual(local_time('bad'),'')
        finally:
            if old is None:os.environ.pop('TZ',None)
            else:os.environ['TZ']=old
            time.tzset()

    def test_summary_counts_found_not_missing(self):
        self.assertEqual(scan_summary([{'status':s} for s in ('new','known','known','missing')]),{'found':3,'new':1,'known':2})

    def test_merge_preserves_both_names(self):
        self.store.commit_scan(NET,[observation(),observation('192.0.2.3','00:11:22:33:44:77')])
        a,b=self.store.devices(NET.scope)
        self.store.rename(a['id'],'Office')
        self.store.rename(b['id'],'Printer')
        self.store.merge(a['id'],b['id'])
        device=self.store.devices(NET.scope)[0]
        self.assertEqual(device['name'],'Office')
        self.assertEqual(device['other_names'],['Printer'])
        self.store.commit_scan(NET,[observation('192.0.2.8')])
        self.assertEqual(self.store.devices(NET.scope)[0]['name'],'Office')
        self.assertEqual(self.store.devices(NET.scope)[0]['status'],'known')

    def test_legacy_database_migration_retains_data(self):
        self.store.commit_scan(NET,[observation()])
        before=self.store.devices(NET.scope)[0]
        self.store.rename(before['id'],'Preserved')
        self.store.db.execute('DROP TABLE device_names')
        self.store.db.commit()
        self.store.close()
        from core import Store
        self.store=Store(self.path/'devices.sqlite3')
        after=self.store.devices(NET.scope)[0]
        self.assertEqual(after['id'],before['id'])
        self.assertEqual(after['name'],'Preserved')
        self.assertEqual(len(after['history']),1)
