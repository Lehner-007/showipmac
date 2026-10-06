import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import ROOT, Vendors, atomic_json


def concurrent_writer(path, identity, start, result):
    start.wait(10)
    failures = []
    for index in range(80):
        try:
            atomic_json(Path(path), {'writer': identity, 'index': index, 'payload': 'x' * 4096})
        except Exception as exc:
            failures.append(type(exc).__name__)
    result.put(failures)


class StorageRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / 'work')
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_concurrent_processes_produce_complete_snapshots(self):
        ctx = multiprocessing.get_context('spawn')
        start, results = ctx.Event(), ctx.Queue()
        target = self.path / 'settings.json'
        processes = [ctx.Process(target=concurrent_writer, args=(str(target), i, start, results)) for i in range(2)]
        for process in processes: process.start()
        start.set()
        for process in processes:
            process.join(20)
            if process.is_alive(): process.kill(); process.join(); self.fail('Writer timed out')
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(results.get(timeout=2), [])
        self.assertEqual(results.get(timeout=2), [])
        data = json.loads(target.read_text())
        self.assertEqual(data['index'], 79)
        self.assertEqual(data['payload'], 'x' * 4096)
        self.assertEqual(list(self.path.glob('.settings.json-*')), [])
        atomic_json(target, {'writer': 'last'})
        self.assertEqual(json.loads(target.read_text()), {'writer': 'last'})

    def test_failed_replace_keeps_previous_snapshot_and_cleans_temp(self):
        target = self.path / 'settings.json'
        atomic_json(target, {'old': True})
        with patch('core.os.replace', side_effect=OSError('test')), self.assertRaises(OSError):
            atomic_json(target, {'new': True})
        self.assertEqual(json.loads(target.read_text()), {'old': True})
        self.assertEqual(list(self.path.glob('.settings.json-*')), [])

    def test_invalid_vendor_structures_preserved_and_rejected_as_value_error(self):
        path = self.path / 'vendors.json'
        invalid = [[], None, 42, {}, {'date': [], 'prefixes': {}},
                   {'date': '2026-02-30', 'prefixes': {}},
                   {'date': '2026-10-05', 'prefixes': {'BAD': 'Vendor'}},
                   {'date': '2026-10-05', 'prefixes': {'001122': []}},
                   {'date': '2026-10-05', 'prefixes': {'001122': ''}}]
        for value in invalid:
            with self.subTest(value=value):
                original = json.dumps(value)
                path.write_text(original)
                with self.assertRaises(ValueError): Vendors.load(path)
                self.assertEqual(path.read_text(), original)
        atomic_json(path, {'date': '2026-10-05', 'prefixes': {'001122': 'Vendor'}})
        self.assertEqual(Vendors.load(path).lookup('00:11:22:33:44:55'), 'Vendor')
        self.assertTrue(Vendors.load(None).data['prefixes'])

    def test_application_starts_with_bundled_data_and_preserves_invalid_file(self):
        from runtime import Runtime
        from showipmac import create_application
        path = self.path / 'vendors.json'; path.write_text('[]')
        app = create_application(Runtime(self.path))
        try:
            self.assertIn('oui_error', app.rt.warnings)
            self.assertTrue(app.vendors.data['prefixes'])
            self.assertEqual(app.vendors.data['date'], '2026-10-05')
            self.assertEqual(path.read_text(), '[]')
        finally:
            app.store.close()
