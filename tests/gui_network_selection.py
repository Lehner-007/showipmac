"""Real GTK regression: scan choices filtered, technical interfaces retained."""
import sys
import tempfile
import time
import subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from core import ROOT, Network
from runtime import Runtime
from showipmac import create_application

profile = Path(tempfile.mkdtemp(prefix='gui-network-024-', dir=ROOT/'work'))
vnet = Network('vnet0', ('fe80::1/64',), '00:11:22:33:44:55', True)
bridge = Network('virbr0', ('192.168.122.1/24', 'fe80::2/64'), '00:11:22:33:44:66', True)
app = create_application(Runtime(profile))
errors = []
phase = 0
started = time.monotonic()

def widgets(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from widgets(child)
        child = child.get_next_sibling()

def details_for_vnet():
    window = app.network_info()
    assert window is not None
    selector = next(w for w in widgets(window) if isinstance(w, Gtk.DropDown))
    assert 'vnet0' in selector.get_model().get_string(0)
    selector.set_selected(0)
    labels = [w.get_label() for w in widgets(window) if isinstance(w, Gtk.Label)]
    assert 'fe80::1' in labels
    assert vnet.mac in labels
    return window

def pump():
    global phase, details
    try:
        assert time.monotonic() - started < 15, 'timeout'
        if app.worker:
            return True
        if phase == 0:
            assert app.networks == [bridge]
            assert app.detected_networks == [vnet, bridge]
            assert app.network_select.get_model().get_n_items() == 1
            assert app.actions['start'].get_enabled()
            details = details_for_vnet()
            assert app.selected_network() == bridge
            phase = 1
        elif phase == 1:
            subprocess.run(['gnome-screenshot', '-w', '-f', str(profile/'details-de.png')], check=True)
            details.destroy()
            app.change_language('en')
            mock_discover.return_value = [vnet]
            app.refresh()
            phase = 2
        elif phase == 2:
            assert app.networks == []
            assert app.network_select.get_model().get_n_items() == 0
            assert not app.actions['start'].get_enabled()
            assert app.status_key == 'no_network'
            details = details_for_vnet()
            phase = 3
        elif phase == 3:
            subprocess.run(['gnome-screenshot', '-w', '-f', str(profile/'details-en.png')], check=True)
            details.destroy()
            mock_discover.return_value = []
            app.refresh()
            phase = 4
        else:
            assert app.detected_networks == []
            assert app.network_info() is None
            assert not app.actions['start'].get_enabled()
            app.on_close()
            return False
    except Exception as exc:
        errors.append(repr(exc))
        app.quit()
        return False
    return True

with patch('showipmac.discover_networks', return_value=[vnet, bridge]) as mock_discover:
    GLib.timeout_add(500, pump)
    app.run(['network-selection-qa'])
assert not errors, errors
print('GTK network selection passed: DE/EN, vnet0 details, virbr0 scan choice, IPv6-only and empty discovery.')
print(profile)
