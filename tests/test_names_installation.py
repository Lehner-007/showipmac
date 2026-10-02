import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import test_core
from core import ROOT, Store, VERSION
from presentation import cell_value
from runtime import Runtime
from showipmac import create_application, data_path


class NameTests(unittest.TestCase):
    setUp = test_core.CoreTests.setUp
    tearDown = test_core.CoreTests.tearDown

    def observe(self, hostname):
        obs = test_core.observation()
        obs['hostname'] = hostname
        self.store.commit_scan(test_core.NET, [obs])
        return self.store.devices(test_core.NET.scope)[0]

    def test_adoption_and_user_override(self):
        self.assertEqual(self.observe('')['name'], '')
        device = self.observe('printer.local')
        self.assertEqual(device['name'], 'printer.local')
        self.store.rename(device['id'], 'Office printer')
        self.assertEqual(self.observe('new-host')['name'], 'Office printer')
        self.store.close()
        self.store = Store(self.path / 'devices.sqlite3')
        self.assertEqual(self.observe('third-host')['name'], 'Office printer')

    def test_unknown_and_invalid_hostnames(self):
        for name in ('', 'Unbekannt', 'Unknown', '192.0.2.2', 'bad host'):
            self.assertEqual(self.observe(name)['name'], '')
        device = self.observe('')
        self.store.rename(device['id'], ' Unbekannt ')
        self.assertEqual(self.observe('pc')['name'], 'pc')
        self.assertEqual(self.observe('changed')['name'], 'pc')

    def test_legacy_database_adoption(self):
        device = self.observe('vm')
        self.store.rename(device['id'], '')
        self.store.close()
        self.store = Store(self.path / 'devices.sqlite3')
        device = self.store.devices(test_core.NET.scope)[0]
        self.assertEqual(device['name'], 'vm')
        self.assertEqual(cell_value(device, 'name', lambda k: 'Unbekannt', 'de'), 'vm')

    def test_fresh_profile_and_existing_profile(self):
        profile = self.path / 'fresh'
        rt = Runtime(profile)
        app = create_application(rt)
        self.assertTrue((profile / 'devices.sqlite3').exists())
        self.assertEqual(app.store.db.execute('SELECT COUNT(*) FROM devices').fetchone()[0], 0)
        app.store.commit_scan(test_core.NET, [test_core.observation()])
        device = app.store.devices(test_core.NET.scope)[0]
        app.store.rename(device['id'], 'Saved name')
        app.store.close()
        app = create_application(Runtime(profile))
        self.assertEqual(app.store.devices(test_core.NET.scope)[0]['name'], 'Saved name')
        app.store.close()

    def test_package_staging_excludes_private_data(self):
        spec = importlib.util.spec_from_file_location('build_deb', ROOT / 'packaging/build_deb.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        stage = self.path / 'package'
        self.assertEqual(builder.stage_package(stage), VERSION)
        files = [str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file()]
        self.assertFalse(any('.config' in f or '.sqlite' in f or '__pycache__' in f or '/tests/' in f for f in files))
        app_root = stage / 'usr/share/showipmac'
        self.assertTrue((app_root / 'languages.py').is_file())
        self.assertFalse((app_root / 'github').exists())
        self.assertFalse((app_root / 'start.sh').exists())
        with patch('showipmac.ROOT', app_root), patch.dict('os.environ', {'XDG_CONFIG_HOME': str(self.path / 'xdg')}, clear=True):
            self.assertEqual(data_path(), self.path / 'xdg/showipmac')
        output = subprocess.check_output(['/usr/bin/python3', '-B', str(app_root / 'showipmac.py'), '--version'], text=True)
        self.assertEqual(output.strip(), f'showipmac {VERSION}')
        for name in ('core.py', 'runtime.py', 'presentation.py', 'showipmac.py'):
            self.assertEqual((app_root / name).read_bytes(), (ROOT / name).read_bytes())
