import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import ROOT

spec = importlib.util.spec_from_file_location('desktop_lifecycle', ROOT / 'packaging/desktop_lifecycle.py')
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)


class LifecycleTests(unittest.TestCase):
    def test_install_reinstall_upgrade_remove_and_foreign_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='lifecycle-') as folder:
            home = Path(folder) / 'home'; home.mkdir()
            config = home / '.config'; config.mkdir()
            (config / 'user-dirs.dirs').write_text('XDG_DESKTOP_DIR="$HOME/Mein Desktop"\n')
            with patch.object(lifecycle.shutil, 'which', return_value=None):
                lifecycle.user_action('configure', home)
                lifecycle.user_action('configure', home)
            shortcut = home / 'Mein Desktop/showipmac.desktop'
            self.assertTrue(shortcut.exists())
            self.assertEqual(shortcut.stat().st_mode & 0o777, 0o755)
            for base in ('.config', '.cache', '.local/share', '.local/state'):
                path = home / base / 'showipmac'; path.mkdir(parents=True)
                (path / 'private').write_text('keep during upgrades')
            lifecycle.user_action('upgrade', home)
            with patch.object(lifecycle.shutil, 'which', return_value=None):
                lifecycle.user_action('configure', home)
            self.assertTrue((config / 'showipmac/private').exists())
            foreign = home / 'Mein Desktop/foreign.desktop'
            foreign.write_text('[Desktop Entry]\nExec=other\n')
            with patch.dict(os.environ, {}, clear=True):
                lifecycle.user_action('remove', home)
                lifecycle.user_action('remove', home)
            self.assertFalse(shortcut.exists())
            self.assertTrue(foreign.exists())
            self.assertFalse((config / 'showipmac').exists())
            for value in ('$HOME', '${HOME}'):
                (config / 'user-dirs.dirs').write_text(f'XDG_DESKTOP_DIR="{value}"\n')
                lifecycle.user_action('configure', home)
                self.assertFalse((home / 'showipmac.desktop').exists())

    def test_symlink_ancestors_and_own_symlink_target(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='lifecycle-') as folder:
            root = Path(folder)
            home = root / 'home'; home.mkdir()
            other = root / 'foreign'; other.mkdir()
            (other / 'private').write_text('keep')
            (home / '.config').mkdir()
            (home / '.config/showipmac').symlink_to(other, target_is_directory=True)
            with patch.dict(os.environ, {}, clear=True):
                lifecycle.user_action('remove', home)
            self.assertTrue((other / 'private').exists())
            (home / '.config').rmdir()
            (home / '.config').symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                lifecycle.user_action('remove', home)
            self.assertTrue((other / 'private').exists())
