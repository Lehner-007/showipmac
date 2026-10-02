"""Verify automatic and edited names in real GTK rows, with synthetic observations."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gi.repository import GLib
from core import ROOT, Network
from runtime import Runtime
from showipmac import create_application
net = Network('qa0', ('192.0.2.1/24',), '', True)
obs = dict(mac='00:11:22:33:44:66', ip='192.0.2.2', interface='qa0', hostname='printer.local', evidence='REACHABLE')
with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='gui-names-') as directory:
    app = create_application(Runtime(Path(directory)))
    app.store.commit_scan(net, [obs])
    errors = []
    def check():
        try:
            for language in ('de', 'en'):
                app.change_language(language)
                app.render_devices()
                row = app.listbox.get_row_at_index(0)
                assert row.get_child().get_first_child().get_label() == 'printer.local'
            app.store.rename(row.device['id'], 'Office printer')
            app.store.commit_scan(net, [dict(obs, hostname='changed-host')])
            app.network_changed()
            app.render_devices()
            assert app.listbox.get_row_at_index(0).get_child().get_first_child().get_label() == 'Office printer'
        except Exception as exc:
            errors.append(repr(exc))
        app.on_close()
        return False
    with patch('showipmac.discover_networks', return_value=[net]):
        GLib.timeout_add(800, check)
        app.run(['gui-names-test'])
    assert not errors, errors
print('GTK name adoption, DE/EN display and user override passed.')
