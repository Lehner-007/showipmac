import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import ROOT, Cancelled, DiscoveryError, Network, Store, Vendors, command, scan
from runtime import Runtime


class AssignmentRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_cached_ipv4_and_ipv6_targets_share_hard_active_budget(self):
        net=Network('test0',('192.0.2.10/24','2001:db8::10/64'),'00:11:22:33:44:55',True)
        cached=[
            dict(ip='192.0.2.2',mac='00:11:22:33:44:01',interface='test0',evidence='STALE'),
            dict(ip='192.0.2.3',mac='00:11:22:33:44:02',interface='test0',evidence='STALE'),
            dict(ip='2001:db8::2',mac='00:11:22:33:44:03',interface='test0',evidence='STALE'),
            dict(ip='192.0.2.2',mac='00:11:22:33:44:01',interface='test0',evidence='STALE'),
        ]
        probes=[]
        with patch('core.discover_networks',return_value=[net]),patch('core.neighbors',side_effect=[cached,cached]),\
             patch('core.shutil.which',return_value='/mock/ping'),patch('core.probe',side_effect=lambda _n,address,_c:probes.append(address)),\
             patch('core.resolve_hostname',return_value=('', 'unknown')):
            observations,warnings=scan(net,threading.Event(),max_hosts=2)
        self.assertEqual(len(probes),2)
        self.assertEqual(len(set(probes)),2)
        self.assertNotIn('192.0.2.10',probes)
        self.assertEqual(warnings.metrics['active_targets'],2)
        self.assertEqual(warnings.metrics['cached_targets'],3)
        self.assertTrue(warnings.metrics['active_limited'])
        self.assertIn('active_limit_reached',warnings)
        self.assertTrue(observations)

    def test_passive_scan_never_probes_and_reports_separate_requests(self):
        net=Network('test0',('192.0.2.10/24',),'00:11:22:33:44:55',True)
        cached=[dict(ip='192.0.2.2',mac='00:11:22:33:44:01',interface='test0',evidence='STALE')]
        with patch('core.discover_networks',return_value=[net]),patch('core.neighbors',return_value=cached),\
             patch('core.probe',side_effect=AssertionError('passive scan probed')),patch('core.resolve_hostname',return_value=('', 'unknown')):
            _,warnings=scan(net,threading.Event(),active=False)
        self.assertEqual(warnings.metrics['active_targets'],0)
        self.assertEqual(warnings.metrics['passive_neighbor_rows'],1)
        # One local-address lookup plus one cached neighbor, kept separate from passive rows.
        self.assertEqual(warnings.metrics['hostname_lookups'],2)

    def test_invalid_manufacturer_contract_rejected_without_attribute_errors(self):
        for csv_data in (
            'Assignment,Organization Name\n001122,\n',
            'Assignment,Organization Name\n001122\n',
            'Wrong,Header\n001122,Vendor\n',
        ):
            with self.subTest(csv=csv_data),self.assertRaises(ValueError):
                Vendors.parse([csv_data],'2026-10-22')
        path=self.root/'vendors.json'
        path.write_text(json.dumps({'date':'','prefixes':{}}))
        with self.assertRaises(ValueError):Vendors.load(path)
        self.assertEqual(json.loads(path.read_text())['prefixes'],{})

    def test_private_directory_and_database_modes_under_umask_022(self):
        data=self.root/'private-data'
        previous=os.umask(0o022)
        try:
            runtime=Runtime(data)
            runtime.save()
            store=Store(data/'devices.sqlite3')
        finally:os.umask(previous)
        try:
            self.assertEqual(stat.S_IMODE(data.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE((data/'devices.sqlite3').stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE((data/'settings.json').stat().st_mode),0o600)
        finally:store.close()

    def test_sqlite_journal_and_rotated_logs_are_private(self):
        data=self.root/'private';data.mkdir(mode=0o700)
        store=Store(data/'devices.sqlite3')
        try:
            store.db.execute('BEGIN IMMEDIATE')
            store.db.execute('INSERT INTO scans VALUES(?,?,?,?)',('test-scan','192.0.2.0/24','2026-10-22T00:00:00Z','[]'))
            journal=data/'devices.sqlite3-journal'
            self.assertTrue(journal.exists())
            self.assertEqual(stat.S_IMODE(journal.stat().st_mode),0o600)
            store.db.rollback()
        finally:store.close()

        import sys
        sys.path.insert(0,str(ROOT))
        from showipmac import PrivateRotatingFileHandler
        log=data/'showipmac.log'
        handler=PrivateRotatingFileHandler(log,maxBytes=1,backupCount=1,encoding='utf-8')
        try:
            handler.emit(__import__('logging').LogRecord('test',20,__file__,1,'entry',(),None))
            handler.doRollover()
            self.assertEqual(stat.S_IMODE(log.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE((data/'showipmac.log.1').stat().st_mode),0o600)
        finally:handler.close()

    def test_owned_data_symlink_and_foreign_hardlink_rejected(self):
        actual=self.root/'actual';actual.mkdir(mode=0o700)
        link=self.root/'linked';link.symlink_to(actual,target_is_directory=True)
        with self.assertRaises(PermissionError):Runtime(link)
        db=self.root/'db';db.write_text('keep')
        hard=self.root/'hard';os.link(db,hard)
        with self.assertRaises(PermissionError):Store(hard)
        self.assertEqual(db.read_text(),'keep')

    def test_command_rejects_captured_output_beyond_byte_budget(self):
        with self.assertRaisesRegex(DiscoveryError,'output_limit'):
            command(['python3','-c','print("x" * 5000)'],timeout=3,max_stdout=1024)

    def test_command_preserves_output_and_return_code_contract(self):
        self.assertEqual(command([sys.executable,'-c','print("ready")'],timeout=3),'ready\n')
        self.assertEqual(command([sys.executable,'-c','print("partial"); raise SystemExit(1)'],
                                 timeout=3,allowed=(0,1)),'partial\n')
        with self.assertRaisesRegex(DiscoveryError,'python'):
            command([sys.executable,'-c','import sys; print("x" * 5000,file=sys.stderr)'],
                    timeout=3,max_stderr=1024)

    def _parent_with_child(self, child_code):
        """Start a child that inherits the command pipes, then exit the parent."""
        parent_code = 'import subprocess,sys; subprocess.Popen([sys.executable,"-c",sys.argv[1]])'
        return [sys.executable, '-c', parent_code, child_code]

    def test_command_timeout_kills_child_after_parent_exits(self):
        marker=self.root/'term-received'
        child_code=(
            'import signal,time,pathlib; '
            f'signal.signal(signal.SIGTERM,lambda *_: (pathlib.Path({str(marker)!r}).write_text("term"), exit(0))); '
            'time.sleep(20)'
        )
        started=time.monotonic()
        with self.assertRaisesRegex(DiscoveryError,'timeout'):
            command(self._parent_with_child(child_code),timeout=.15)
        self.assertLess(time.monotonic()-started,1.0)
        self.assertEqual(marker.read_text(), 'term')

    def test_command_timeout_escalates_when_child_ignores_sigterm(self):
        pid_file=self.root/'child-pid'
        child_code=(
            'import os,signal,time,pathlib; '
            f'pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); '
            'signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)'
        )
        started=time.monotonic()
        with self.assertRaisesRegex(DiscoveryError,'timeout'):
            command(self._parent_with_child(child_code),timeout=.15)
        elapsed=time.monotonic()-started
        self.assertLess(elapsed,1.0)
        child_pid=int(pid_file.read_text())
        # A killed orphan may briefly remain as a zombie until the system reaps it.
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            try:
                state=Path(f'/proc/{child_pid}/stat').read_text().split(') ',1)[1][0]
            except FileNotFoundError:
                break
            if state=='Z':break
            time.sleep(.01)
        else:self.fail('SIGTERM-ignoring descendant survived SIGKILL escalation')

    def test_command_cancellation_kills_child_after_parent_exits(self):
        marker=self.root/'cancel-term-received'
        child_code=(
            'import signal,time,pathlib; '
            f'signal.signal(signal.SIGTERM,lambda *_: (pathlib.Path({str(marker)!r}).write_text("term"), exit(0))); '
            'time.sleep(20)'
        )
        event=threading.Event()
        timer=threading.Timer(.15,event.set)
        timer.start();started=time.monotonic()
        try:
            with self.assertRaises(Cancelled):
                command(self._parent_with_child(child_code),event,timeout=3)
        finally:timer.join()
        self.assertLess(time.monotonic()-started,1.0)
        self.assertEqual(marker.read_text(),'term')


if __name__=='__main__':unittest.main()
