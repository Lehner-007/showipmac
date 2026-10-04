"""Real GTK regression tests with synthetic networks and isolated user data."""
import csv
import io
import json
import logging
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio
from core import ROOT, VERSION, Network
from runtime import Runtime
from showipmac import create_application
from modules.export import serialize, write_export
from modules.integration import Translations
from modules.model import bind_runtime, update_due
from modules.window_state import reachable_bounds, x11_position
from modules.menus import descendants, compact_menus
from modules.logs import SessionFormatter

NET = Network('qa0', ('192.0.2.1/24',), '', True)


def pump(seconds=.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        GLib.MainContext.default().iteration(False)
        time.sleep(.005)


class SharedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='blocks-')
        self.path = Path(self.temp.name)
        self.rt = Runtime(self.path / 'profile')
        self.app = create_application(self.rt)
        self.app.set_application_id('org.dogtruck.qa' + uuid.uuid4().hex)
        self.app.register(None)
        obs = dict(mac='00:11:22:33:44:66', ip='192.0.2.2', interface='qa0', hostname='printer', evidence='REACHABLE')
        self.app.store.commit_scan(NET, [obs, dict(obs, mac='00:11:22:33:44:77', ip='192.0.2.3', hostname='router')])
        with patch('showipmac.discover_networks', return_value=[NET]):
            self.app.activate(self.app)
            pump(.4)
        self.assertIsNone(self.app.worker)

    def tearDown(self):
        if self.app.window.alive:
            self.app.on_close()
            pump(.5)
        self.temp.cleanup()

    def test_settings_cancel_save_language_and_existing_data(self):
        app = self.app
        before = dict(self.rt.settings)
        dialog = app.settings_dialog()
        controls = dialog.template_controls
        controls['fields']['max_hosts'].set_value(111)
        controls['fields']['active'].set_active(False)
        controls['cancel'].emit('clicked')
        self.assertEqual(before, self.rt.settings)
        app.listbox.select_row(app.listbox.get_row_at_index(0))
        dialog = app.settings_dialog(); controls = dialog.template_controls
        controls['fields']['max_hosts'].set_value(128)
        controls['fields']['active'].set_active(False)
        controls['language'].set_selected(controls['codes'].index('en'))
        controls['save'].emit('clicked'); pump()
        self.assertEqual(self.rt.settings['max_hosts'], 128)
        self.assertFalse(app.actions['active'].get_state().get_boolean())
        self.assertEqual(self.rt.settings['language'], 'en')
        self.assertEqual(len(app.devices), 2)
        self.assertEqual(len(app.listbox.get_selected_rows()), 1)
        saved = json.loads((self.rt.path / 'settings.json').read_text())
        self.assertEqual(saved['max_hosts'], 128)
        self.assertEqual(Runtime(self.rt.path).settings['language'], 'en')
        self.assertFalse(update_due(self.rt.settings))
        self.rt.settings['update_check'] = True
        self.assertTrue(update_due(self.rt.settings))
        with patch('languages.download_version', return_value='99.0.0'):
            app.window.check_update(self.rt.settings['update_url']); pump(.5)
        self.assertTrue(self.rt.settings['last_update_check'])
        self.assertFalse(update_due(self.rt.settings))
        self.assertFalse(app.worker)

    def test_export_formats_filtered_native_save_and_protection(self):
        app = self.app
        rows = app.window.results.rows()
        rows[0]['name'] = '=1+1;<script>Ä</script>'
        tr = app.window.tr
        columns = app.window.results.columns
        data = list(csv.reader(io.StringIO(serialize(rows, columns, 'csv', tr).lstrip('\ufeff')), delimiter=';'))
        self.assertTrue(data[1][0].startswith("'="))
        self.assertEqual(json.loads(serialize(rows, columns, 'json', tr))['results'], rows)
        html = serialize(rows, columns, 'html', tr)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('data:image/png;base64,', html)
        for name in ('settings.json', 'devices.sqlite3', 'logs/showipmac.log'):
            with self.assertRaises(ValueError):
                write_export(self.rt.path / name, rows, columns, 'json', tr)
        link = self.path / 'link.json'; link.symlink_to(self.rt.path / 'settings.json')
        with self.assertRaises(ValueError):
            write_export(link, rows, columns, 'json', tr)
        app.search.set_text('printer'); app.render_devices()
        self.assertEqual(len(app.visible_devices), 1)
        dialog = app.export_results()
        dialog.export_controls['format'].set_selected(2)
        dialog.export_controls['scope'].set_selected(1)
        dialog.export_controls['save'].emit('clicked'); pump(.3)
        native = app.window.file_dialogs[-1]
        self.assertIsInstance(native, Gtk.FileChooserNative)
        native.set_current_folder(Gio.File.new_for_path(str(self.path))); pump(.3)
        native.set_current_name('filtered.html'); pump(.3)
        native.emit('response', Gtk.ResponseType.ACCEPT)
        exported = (self.path / 'filtered.html').read_text()
        self.assertIn('printer', exported)
        self.assertNotIn('router', exported)
        self.assertFalse(app.window.file_dialogs)

    def test_progress_cancellation_noncancellable_close(self):
        app = self.app
        called = []
        def wait():
            while not app.cancel_event.wait(.02):
                app.progress('progress', (1, 10))
            from core import Cancelled
            raise Cancelled()
        self.assertTrue(app.run_job(wait, called.append, title_key='task_scan'))
        self.assertFalse(app.run_job(lambda: None, called.append))
        pump(.2)
        self.assertTrue(app.progress_dialog.get_modal())
        self.assertEqual(app.progress_dialog.get_transient_for(), app.window)
        self.assertEqual(app.progress_dialog.progress.get_fraction(), .1)
        app.cancel(); pump(.4)
        self.assertFalse(called)
        self.assertIsNone(app.progress_dialog)
        self.assertEqual(app.status_key, 'cancelled')
        app.run_job(lambda: time.sleep(.3), called.append, cancellable=False)
        self.assertFalse(app.progress_dialog.cancel_button.get_sensitive())
        app.on_close()
        self.assertTrue(app.window.alive)
        pump(.5)
        self.assertFalse(app.window.alive)
        self.assertFalse(called)

    def test_log_readonly_sessions_and_window_recovery(self):
        app = self.app
        folder = self.rt.path / 'logs'; folder.mkdir()
        log = folder / 'showipmac.log'
        record = logging.LogRecord('test', logging.INFO, '', 1, 'start', (), None)
        record.session_start = True
        entry = SessionFormatter('%(asctime)s %(message)s').format(record)
        log.write_text('older session\n' + entry)
        dialog = app.show_log()
        self.assertFalse(dialog.log_controls['view'].get_editable())
        self.assertEqual(log.read_text(), 'older session\n' + entry)
        text = dialog.log_controls['view'].get_buffer()
        self.assertIn('=' * 72, text.get_text(text.get_start_iter(), text.get_end_iter(), True))
        app.window.close_dialog(dialog)
        safe = reachable_bounds((2500, 100, 900, 600), [(0, 0, 800, 600)])
        self.assertLessEqual(safe[0] + safe[2], 800)
        self.assertLessEqual(safe[1] + safe[3] + 48, 600)
        self.assertLess(reachable_bounds((-1600, 100, 900, 600), [(-1920, 0, 1920, 1080)])[0], 0)
        app.window.set_default_size(700, 420); x11_position(app.window, (100, 60)); pump(.6)
        app.on_close(); pump(.2)
        settings = Runtime(self.rt.path).settings
        self.assertEqual((settings['window_width'], settings['window_height']), (700, 420))

    def test_real_single_entry_menu_and_visible_separators(self):
        app = self.app
        for code in ('de', 'en'):
            for dark in (False, True):
                Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', dark)
                app.change_language(code)
                file_menu = app.menu_bar.get_menu_model().get_item_link(0, 'submenu')
                self.assertEqual(file_menu.get_n_items(), 3)
                self.assertEqual(file_menu.get_item_link(1, 'section').get_item_attribute_value(0, 'action', None).get_string(), 'app.settings')
                first = app.menu_bar.get_first_child()
                popover = next(w for w in descendants(first) if isinstance(w, Gtk.Popover))
                popover.popup(); pump(.4)
                separators = [w for w in descendants(app.menu_bar) if isinstance(w, Gtk.Separator) and w.get_mapped()]
                self.assertGreaterEqual(len(separators), 2)
                self.assertGreaterEqual(sum(w.get_width() > 0 and w.get_height() >= 1 for w in separators), 2, [(w.get_width(), w.get_height()) for w in separators])
                for w in descendants(app.menu_bar):
                    if isinstance(w, Gtk.Popover): w.popdown()
                pump(.3)
                root = Gio.Menu(); single = Gio.Menu(); single.append('One', 'app.help'); root.append_submenu('Single', single)
                app.menu_bar.set_menu_model(root); compact_menus(app.menu_bar)
                single_popover = next(w for w in descendants(app.menu_bar.get_first_child()) if isinstance(w, Gtk.Popover))
                single_popover.popup(); pump(.4)
                scrolls = [w for w in descendants(app.menu_bar) if isinstance(w, Gtk.ScrolledWindow) and w.get_mapped()]
                self.assertTrue(scrolls)
                for scroll in scrolls:
                    natural = scroll.get_child().measure(Gtk.Orientation.VERTICAL, -1).natural
                    self.assertLessEqual(scroll.get_height(), natural + 2)
                for w in descendants(app.menu_bar):
                    if isinstance(w, Gtk.Popover): w.popdown()
                pump(.3)
                app.build_menu()
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', False)

    def test_progress_window_is_centered_and_rows_are_striped(self):
        import re
        import subprocess
        import shutil
        from PIL import Image
        app = self.app
        if not shutil.which('xwininfo') or not shutil.which('xprop'):
            self.skipTest('X11 geometry tools unavailable')
        import gi
        gi.require_version('GdkX11', '4.0')
        from gi.repository import GdkX11
        if not isinstance(app.window.get_surface(), GdkX11.X11Surface):
            self.skipTest('X11 geometric test requires an X11 surface')
        app.run_job(lambda: app.cancel_event.wait(2), lambda _: None, title_key='task_scan')
        pump(.35)
        def frame(widget):
            xid = str(GdkX11.X11Surface.get_xid(widget.get_surface()))
            output = subprocess.check_output(['xwininfo', '-id', xid], text=True)
            x = int(re.search(r'Absolute upper-left X:\s*(-?\d+)', output).group(1))
            y = int(re.search(r'Absolute upper-left Y:\s*(-?\d+)', output).group(1))
            w = int(re.search(r'Width:\s*(\d+)', output).group(1))
            h = int(re.search(r'Height:\s*(\d+)', output).group(1))
            ext = subprocess.check_output(['xprop', '-id', xid, '_NET_FRAME_EXTENTS'], text=True)
            values = [int(n) for n in re.findall(r'\d+', ext.split('=', 1)[-1])]
            left, right, top, bottom = values if len(values) == 4 else (0, 0, 0, 0)
            return (x - left + (w + left + right) / 2, y - top + (h + top + bottom) / 2)
        parent = frame(app.window); child = frame(app.progress_dialog)
        self.assertLessEqual(abs(parent[0] - child[0]), 2)
        self.assertLessEqual(abs(parent[1] - child[1]), 2)
        app.cancel(); pump(.3)
        app.listbox.unselect_all()
        for dark in (False, True):
            Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', dark); pump(.3)
            view = app.listbox
            snapshot = Gtk.Snapshot()
            paintable = Gtk.WidgetPaintable.new(view)
            paintable.snapshot(snapshot, view.get_width(), view.get_height())
            node = snapshot.to_node()
            texture = app.window.get_renderer().render_texture(node, None)
            target = self.path / 'rows.png'; texture.save_to_png(str(target))
            with Image.open(target) as image:
                # Sample a blank edge, away from cell text and the watermark.
                first = view.get_row_at_index(0); second = view.get_row_at_index(1)
                colors = [image.getpixel((2, int(r.get_allocation().y + r.get_height()/2)))[:3] for r in (first, second)]
            self.assertNotEqual(colors[0], colors[1])
            if dark:
                self.assertGreater(sum(colors[1]), sum(colors[0]))
            else:
                self.assertLess(sum(colors[1]), sum(colors[0]))
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', False)
