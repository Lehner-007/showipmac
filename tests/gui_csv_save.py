"""Exercise actual GTK save chooser and its response callback."""
import csv
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib
from core import ROOT, Network
from runtime import Runtime
from showipmac import create_application
net = Network('qa0', ('192.0.2.1/24',), '', True)
obs = dict(mac='00:11:22:33:44:66', ip='192.0.2.2', interface='qa0', hostname='printer.local', evidence='REACHABLE')
with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='gui-save-') as directory:
    path = Path(directory)
    app = create_application(Runtime(path / 'profile'))
    app.store.commit_scan(net, [obs, dict(obs, ip='192.0.2.3', mac='00:11:22:33:44:77', hostname='missing')])
    app.store.commit_scan(net, [obs])
    errors = []
    phase = 0
    chooser = None
    database = None
    def tick():
        global phase, chooser, database
        try:
            if phase == 0:
                database = app.window
                chooser = app.export_dialog('csv')
                phase = 1
            elif phase == 1:
                assert chooser.get_current_folder().get_path() == str(ROOT)
                chooser.set_current_folder(Gio.File.new_for_path(str(path)))
                chooser.set_current_name('found.csv')
                phase = 2
            elif phase == 2:
                assert chooser.get_file().get_path() == str(path / 'found.csv')
                chooser.emit('response', Gtk.ResponseType.ACCEPT)
                phase = 2.5
            elif phase == 2.5:
                with (path / 'found.csv').open(encoding='utf-8-sig') as handle:
                    rows = list(csv.reader(handle))
                assert len(rows) == 2 and rows[1][0] == 'printer.local'
                assert app.status_key == 'exported'
                app.change_language('en')
                chooser = app.export_dialog('csv')
                phase = 3
            elif phase == 3:
                chooser.set_current_folder(Gio.File.new_for_path(str(path)))
                chooser.set_current_name('cancelled.csv')
                phase = 4
            elif phase == 4:
                chooser.emit('response', Gtk.ResponseType.CANCEL)
                assert not (path / 'cancelled.csv').exists()
                app.on_close()
                return False
        except Exception as exc:
            errors.append(repr(exc))
            if chooser:
                chooser.destroy()
            app.on_close()
            return False
        return True
    with patch('showipmac.discover_networks', return_value=[net]):
        GLib.timeout_add(1000, tick)
        app.run(['gui-save-test'])
    assert not errors, errors
print('Actual GTK chooser: CSV save, cancel, visible folder passed.')
