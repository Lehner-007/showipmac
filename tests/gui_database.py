"""Real GTK database window and its CSV action, using isolated data."""
import csv
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib
from core import ROOT, Network, export
from runtime import Runtime
from showipmac import create_application
net = Network('qa0', ('192.0.2.1/24',), '', True)
obs = dict(mac='00:11:22:33:44:66', ip='192.0.2.2', interface='qa0', hostname='printer.local', evidence='REACHABLE')
with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='gui-database-') as directory:
    path = Path(directory)
    app = create_application(Runtime(path))
    app.store.commit_scan(net, [obs, dict(obs, ip='192.0.2.3', mac='00:11:22:33:44:77', hostname='missing')])
    app.store.commit_scan(net, [obs])
    errors = []
    def check():
        try:
            for code in ('de', 'en'):
                app.change_language(code)
                menu = app.menu_bar.get_menu_model()
                file_menu = menu.get_item_link(0, 'submenu')
                assert file_menu.get_n_items() == 2
                exports = file_menu.get_item_link(0, 'submenu')
                assert exports.get_n_items() == 2
                assert exports.get_item_attribute_value(0, 'action', None).get_string() == 'app.csv'
                assert exports.get_item_attribute_value(1, 'action', None).get_string() == 'app.json'
                assert not app.lookup_action('database')
                assert not hasattr(app, 'database_window')
                for kind in ('csv', 'json'):
                    chooser = app.export_dialog(kind)
                    assert chooser.get_transient_for() is app.window
                    chooser.destroy()
            app.on_close()
            return False
        except Exception as exc:
            errors.append(repr(exc))
            app.on_close()
            return False
    with patch('showipmac.discover_networks', return_value=[net]):
        GLib.timeout_add(800, check)
        app.run(['gui-database-test'])
    assert not errors, errors
print('GTK export submenu passed: DE/EN, CSV/JSON actions, no database window.')
