#!/usr/bin/env python3
"""GTK 4 application for local network discovery. SPDX-License-Identifier: GPL-3.0-only."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
import webbrowser

from core import ROOT, VERSION, Cancelled, Store, Vendors, discover_networks, export, scan, network_options, network_label, VendorUpdateError
from presentation import local_time, cell_value, device_sort_key, scan_summary, display_date, connection_labels, selection_label
from runtime import Runtime, native_language
from core import PROJECT_URL


def data_path():
    if os.environ.get('SHOWIPMAC_DATA_DIR'):
        return Path(os.environ['SHOWIPMAC_DATA_DIR'])
    if (ROOT / 'start.sh').exists():
        return ROOT / '.config'
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'showipmac'


def main():
    # Parse command-line metadata without requiring a display or writing user data.
    language = 'de'
    try:
        import json
        language = json.loads((data_path() / 'settings.json').read_text()).get('language', 'de')
    except (OSError, ValueError, AttributeError):
        pass
    import json
    lang_path = ROOT / 'lang' / (language + '.json') if language in ('de', 'en') else ROOT / 'lang/en.json'
    texts = json.loads(lang_path.read_text())
    if language not in ('de', 'en'):
        try:
            from languages import validate_pack
            code, strings, _ = validate_pack(json.loads((data_path() / 'languages' / language / 'pack.json').read_text('utf-8')))
            if code == language:
                texts.update(strings)
        except (OSError, ValueError, TypeError):
            pass
    parser = argparse.ArgumentParser(description=texts['cli_description'], add_help=False)
    parser.add_argument('-h', '--help', action='help', help=texts['cli_help'])
    parser.add_argument('--version', action='version', version=f'showipmac {VERSION}', help=texts['cli_version'])
    parser.add_argument('--author', action='version', version='Josef', help=texts['cli_author'])
    parser.add_argument('--data-dir', type=Path, default=data_path(), help=texts['cli_data'])
    args = parser.parse_args()
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        from gi.repository import Gtk
    except (ImportError, ValueError):
        print(texts['missing_gtk'], file=sys.stderr)
        return 1
    runtime = Runtime(args.data_dir)
    (runtime.path / 'logs').mkdir(exist_ok=True)
    try:
        handler = RotatingFileHandler(runtime.path / 'logs/showipmac.log', maxBytes=250_000, backupCount=2, encoding='utf-8')
        logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s', datefmt='%d.%m.%Y %H:%M:%S')
    except OSError:
        logging.basicConfig(level=logging.INFO)
    logging.info(runtime.text('log_start'))
    app = create_application(runtime)
    result = app.run([sys.argv[0]])
    logging.info(runtime.text('log_end'))
    return result


def create_application(runtime):
    native_language(runtime.settings['language'])
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Gdk, Gio, GLib, Pango

    class Application(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='org.dogtruck.showipmac', flags=Gio.ApplicationFlags.NON_UNIQUE)
            self.rt = runtime
            self.text = runtime.text
            self.store = Store(runtime.path / 'devices.sqlite3')
            try:
                self.vendors = Vendors.load(runtime.path / 'vendors.json')
            except (OSError, ValueError):
                self.vendors = Vendors()
                self.rt.warnings.append('oui_error')
            self.worker = None
            self.cancel_event = threading.Event()
            self.closing = False
            self.networks = []
            self.detected_networks = []
            self.devices = []
            self.visible_devices = []
            self.bound = []
            self.status_key = 'ready'
            self.status_args = {}
            self.warning_keys = list(runtime.warnings)
            self.sort_column = 'name'
            self.sort_reverse = False
            self.actions = {}
            self.connect('activate', self.activate)

        def label(self, key):
            widget = Gtk.Label(xalign=0)
            self.bound.append((widget, key))
            widget.set_label(self.text(key))
            return widget

        def button(self, key, callback):
            widget = Gtk.Button(label=self.text(key))
            widget.connect('clicked', callback)
            self.bound.append((widget, key))
            return widget

        def row(self, parent):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            scroll.set_propagate_natural_height(True)
            scroll.set_child(box)
            parent.append(scroll)
            return box

        def activate(self, _app):
            if hasattr(self, 'window'):
                self.window.present()
                return
            self.window = Gtk.ApplicationWindow(application=self, title=self.text('title'))
            self.window.set_default_size(self.rt.settings['width'], self.rt.settings['height'])
            self.window.connect('close-request', self.on_close)
            display = Gdk.Display.get_default()
            theme = Gtk.IconTheme.get_for_display(display)
            theme.add_search_path(str(ROOT / 'assets'))
            self.window.set_icon_name('showipmac')
            css = Gtk.CssProvider()
            css.load_from_data(b'window.showipmac label, window.showipmac button {font-weight: normal;} .device-cell {padding: 8px 5px;}')
            Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.window.add_css_class('showipmac')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            for side in ('top', 'bottom', 'start', 'end'):
                getattr(box, 'set_margin_' + side)(12)
            self.window.set_child(box)
            self.lang_codes = sorted(self.rt.languages)
            self.create_actions()
            self.menu_bar = Gtk.PopoverMenuBar()
            box.append(self.menu_bar)
            top = self.row(box)
            logo = Gtk.Image.new_from_file(str(ROOT / 'assets/showipmac.png'))
            logo.set_pixel_size(40)
            top.append(logo)
            self.version_label = Gtk.Label(xalign=0, hexpand=True)
            top.append(self.version_label)
            self.vendor_label = Gtk.Label(xalign=1, hexpand=True, wrap=True)
            top.append(self.vendor_label)
            network_row = self.row(box)
            network_row.append(self.label('network'))
            self.network_select = Gtk.DropDown.new_from_strings([])
            self.network_select.set_hexpand(True)
            self.network_select.connect('notify::selected', self.network_changed)
            network_row.append(self.network_select)
            filters = self.row(box)
            self.search = Gtk.SearchEntry(hexpand=True)
            self.search.set_property('placeholder-text', self.text('search'))
            self.search.connect('search-changed', lambda *_: self.render_devices())
            filters.append(self.search)
            self.filter_keys = ['all', 'new', 'known', 'missing']
            self.filter = Gtk.DropDown.new_from_strings([self.text(k) for k in self.filter_keys])
            self.filter.connect('notify::selected', lambda *_: self.render_devices())
            filters.append(self.filter)
            scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
            overlay = Gtk.Overlay()
            overlay.set_child(scroller)
            watermark = Gtk.Image.new_from_file(str(ROOT / 'assets/wasserzeichen.png'))
            watermark.set_pixel_size(280)
            watermark.set_opacity(.10)
            watermark.set_can_target(False)
            watermark.set_halign(Gtk.Align.CENTER)
            watermark.set_valign(Gtk.Align.CENTER)
            self.watermark = watermark
            overlay.add_overlay(watermark)
            box.append(overlay)
            table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            scroller.set_child(table)
            self.columns = [('name', 145), ('hostname', 155), ('ipv4', 145), ('ipv6', 185),
                            ('mac', 165), ('vendor', 175), ('status', 180), ('last_seen', 180)]
            header = Gtk.Box()
            self.headers = {}
            for key, width in self.columns:
                label = self.label(key)
                label.set_size_request(width, -1)
                label.add_css_class('device-cell')
                gesture = Gtk.GestureClick()
                gesture.connect('released', lambda _g, _n, _x, _y, key=key: self.choose_sort(key))
                label.add_controller(gesture)
                self.headers[key] = label
                header.append(label)
            table.append(header)
            table.append(Gtk.Separator())
            self.listbox = Gtk.ListBox()
            self.listbox.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
            self.listbox.connect('row-activated', lambda *_: self.details(None))
            table.append(self.listbox)
            bottom = self.row(box)
            self.spinner = Gtk.Spinner()
            bottom.append(self.spinner)
            self.status = Gtk.Label(xalign=0, wrap=True, selectable=True, hexpand=True)
            bottom.append(self.status)
            self.warnings = Gtk.Label(xalign=0, wrap=True, selectable=True)
            box.append(self.warnings)
            self.retranslate()
            self.window.present()
            self.refresh()

        def retranslate(self):
            self.window.set_title(self.text('title') + ' · ' + VERSION)
            self.version_label.set_label('showipmac · ' + self.text('version') + ' ' + VERSION)
            self.build_menu()
            for widget, key in self.bound:
                widget.set_label(self.text(key))
            self.search.set_property('placeholder-text', self.text('search'))
            selected = self.filter.get_selected()
            self.filter.set_model(Gtk.StringList.new([self.text(k) for k in self.filter_keys]))
            self.filter.set_selected(min(selected, len(self.filter_keys)-1))
            self.update_vendor_label()
            self.window.set_direction(Gtk.TextDirection.RTL if self.rt.settings['language'].replace('-', '_').split('_')[0] in ('ar', 'he', 'fa', 'ur') else Gtk.TextDirection.LTR)
            self.update_network_labels()
            self.set_status(self.status_key, **self.status_args)
            self.show_warnings()
            self.render_devices()

        def update_vendor_label(self):
            date = self.vendors.data.get('date')
            fetched = self.vendors.data.get('fetched_at')
            if date:
                label = self.text('oui_date', date=display_date(date))
            elif fetched:
                label = self.text('oui_downloaded', date=local_time(fetched, self.rt.settings['language']))
            else:
                label = self.text('oui_date', date=self.text('unknown'))
            self.vendor_label.set_label(label)
            self.vendor_label.set_tooltip_text('\n'.join(
                name + ': ' + local_time(stamp) for name, stamp in self.vendors.data.get('source_dates', {}).items()))

        def change_language(self, language):
            self.rt.settings['language'] = language
            native_language(language)
            self.actions['language'].set_state(GLib.Variant('s', language))
            try:
                self.rt.save()
            except OSError as exc:
                self.fail(exc)
            self.retranslate()

        def create_actions(self):
            callbacks = {'start': self.start_scan, 'cancel': self.cancel, 'refresh': self.refresh,
                         'details': self.details, 'merge': self.merge_devices, 'oui_update': self.update_vendors,
                         'csv': lambda: self.export_dialog('csv'), 'json': lambda: self.export_dialog('json'),
                         'help': self.open_help, 'about': self.about, 'quit': self.on_close,
                         'network_info': self.network_info}
            callbacks['language_install'] = self.language_settings
            for name, callback in callbacks.items():
                action = Gio.SimpleAction.new(name, None)
                action.connect('activate', lambda _a, _p, cb=callback: cb())
                self.add_action(action)
                self.actions[name] = action
            language = Gio.SimpleAction.new_stateful('language', GLib.VariantType.new('s'), GLib.Variant('s', self.rt.settings['language']))
            language.connect('activate', lambda _a, value: self.change_language(value.get_string()))
            self.add_action(language)
            self.actions['language'] = language
            active = Gio.SimpleAction.new_stateful('active', None, GLib.Variant('b', self.rt.settings['active']))
            def toggle_active(action, _value):
                self.rt.settings['active'] = not action.get_state().get_boolean()
                action.set_state(GLib.Variant('b', self.rt.settings['active']))
                try:
                    self.rt.save()
                except OSError as exc:
                    self.fail(exc)
            active.connect('activate', toggle_active)
            self.add_action(active)
            self.actions['active'] = active
            sort = Gio.SimpleAction.new('sort', GLib.VariantType.new('s'))
            sort.connect('activate', lambda _a, value: self.choose_sort(value.get_string()))
            self.add_action(sort)
            self.actions['sort'] = sort
            for action, keys in {'start':['F5'], 'cancel':['Escape'], 'csv':['<Primary>e'],
                                 'details':['<Alt>Return'], 'quit':['<Primary>q'], 'help':['F1']}.items():
                self.set_accels_for_action('app.' + action, keys)

        def build_menu(self):
            root = Gio.Menu()
            def group(key, names):
                menu = Gio.Menu()
                for name in names:
                    menu.append(self.text(name), 'app.' + name)
                root.append_submenu(self.text(key), menu)
                return menu
            file_menu = group('menu_file', [])
            exports = Gio.Menu()
            exports.append(self.text('csv'), 'app.csv')
            exports.append(self.text('json'), 'app.json')
            file_menu.append_submenu(self.text('database'), exports)
            file_menu.append(self.text('quit'), 'app.quit')
            group('menu_network', ['start', 'cancel', 'refresh', 'network_info'])
            group('menu_devices', ['details', 'merge'])
            view = group('menu_view', [])
            sorting = Gio.Menu()
            for key, _width in self.columns:
                item = Gio.MenuItem.new(self.text(key) + (' ↓' if self.sort_reverse else ' ↑') if key == self.sort_column else self.text(key), None)
                item.set_action_and_target_value('app.sort', GLib.Variant('s', key))
                sorting.append_item(item)
            view.append_section(self.text('sort_by'), sorting)
            settings = group('menu_settings', ['active', 'oui_update', 'language_install'])
            languages = Gio.Menu()
            for code in self.lang_codes:
                item = Gio.MenuItem.new(self.rt.languages[code]['language_name'], None)
                item.set_action_and_target_value('app.language', GLib.Variant('s', code))
                languages.append_item(item)
            settings.append_submenu(self.text('language'), languages)
            group('help', ['help', 'about'])
            self.menu_bar.set_menu_model(root)

        def choose_sort(self, column):
            self.sort_reverse = not self.sort_reverse if self.sort_column == column else False
            self.sort_column = column
            self.build_menu()
            self.render_devices()

        def network_info(self, *_):
            networks = list(self.detected_networks)
            if not networks:
                return
            import ipaddress
            window, box = self.dialog('network_info', 640, 480)
            connections = connection_labels(networks, self.text)
            box.append(Gtk.Label(label=self.text('interface_name'), xalign=0))
            selector = Gtk.DropDown.new_from_strings([
                selection_label(n, connections.get(n.interface, ''), self.text('no_ipv4'))
                for n in networks])
            selected = self.selected_network()
            selector.set_selected(next((i for i, n in enumerate(networks)
                                        if selected and n.interface == selected.interface), 0))
            box.append(selector)
            scroll = Gtk.ScrolledWindow(vexpand=True)
            box.append(scroll)
            note = Gtk.Label(label=self.text('port_number_note'), wrap=True, xalign=0)
            note.add_css_class('dim-label')
            box.append(note)

            def update_details(*_):
                network = networks[selector.get_selected()]
                grid = Gtk.Grid(column_spacing=24, row_spacing=12)
                scroll.set_child(grid)
                connection = connections.get(network.interface, '')
                rows = [('network', network_label(network, self.text('no_ipv4'))),
                        ('connection', connection or self.text('unknown')),
                        ('interface_name', network.interface), ('mac', network.mac or self.text('unknown'))]
                for version, title in ((4, 'ipv4'), (6, 'ipv6')):
                    addresses = [ipaddress.ip_interface(a) for a in network.addresses if ipaddress.ip_interface(a).version == version]
                    rows.append((title + '_addresses', '\n'.join(str(a.ip) for a in addresses) or self.text('unknown')))
                    rows.append((title + '_networks', '\n'.join(sorted({str(a.network) for a in addresses})) or self.text('unknown')))
                    if version == 4:
                        rows.append(('netmask', '\n'.join(sorted({str(a.netmask) for a in addresses})) or self.text('unknown')))
                for index, (key, value) in enumerate(rows):
                    label = Gtk.Label(label=self.text(key), xalign=0, yalign=0)
                    label.add_css_class('dim-label')
                    grid.attach(label, 0, index, 1, 1)
                    content = Gtk.Label(label=value, xalign=0, yalign=0, selectable=True, wrap=True, hexpand=True)
                    content.set_direction(Gtk.TextDirection.LTR)
                    grid.attach(content, 1, index, 1, 1)
                note.set_visible(connection.rsplit(' ', 1)[-1].isdigit())

            selector.connect('notify::selected', update_details)
            update_details()
            box.append(self.button('close', lambda *_: window.destroy()))
            window.present()
            return window

        def set_status(self, key, **values):
            self.status_key, self.status_args = key, values
            self.status.set_label(self.text(key, **values))
            return False

        def show_warnings(self):
            self.warnings.set_label('\n'.join(self.text(k) for k in dict.fromkeys(self.warning_keys)))

        def selected_network(self):
            selected = self.network_select.get_selected()
            return self.networks[selected] if selected < len(self.networks) else None

        def update_network_labels(self):
            selected = self.network_select.get_selected()
            connections = connection_labels(self.networks, self.text)
            self.network_select.set_model(Gtk.StringList.new([
                selection_label(n, connections.get(n.interface, ''), self.text('no_ipv4')) for n in self.networks]))
            if self.networks:
                self.network_select.set_selected(min(selected, len(self.networks)-1))

        def refresh(self, *_):
            if self.worker:
                return
            def done(networks):
                self.detected_networks = list(networks)
                self.networks = network_options(self.detected_networks)
                self.update_network_labels()
                self.network_changed()
                self.set_status('ready' if self.networks else 'no_network')
            self.run_job(lambda: discover_networks(self.cancel_event), done)

        def network_changed(self, *_):
            net = self.selected_network()
            try:
                self.devices = self.store.devices(net.scope) if net else []
                for device in self.devices:
                    device['vendor'] = sorted({v for m in device['mac'] if (v := self.vendors.lookup(m))})
                self.render_devices()
            except Exception as exc:
                self.fail(exc)
            self.actions['start'].set_enabled(bool(net) and self.worker is None)

        def render_devices(self):
            if not hasattr(self, 'listbox'):
                return
            ids = {r.device['id'] for r in self.listbox.get_selected_rows()}
            child = self.listbox.get_first_child()
            while child:
                following = child.get_next_sibling()
                self.listbox.remove(child)
                child = following
            for key, label in self.headers.items():
                label.set_label(self.text(key) + ((' ↓' if self.sort_reverse else ' ↑') if key == self.sort_column else ''))
            query = self.search.get_text().casefold()
            index = self.filter.get_selected()
            status = self.filter_keys[index] if index < len(self.filter_keys) else 'all'
            self.visible_devices = []
            for device in sorted(self.devices, key=lambda d: device_sort_key(d, self.sort_column, self.text, self.rt.settings['language']), reverse=self.sort_reverse):
                if status != 'all' and device['status'] != status:
                    continue
                if query and query not in str(device).casefold() and query not in self.text(device['status']).casefold():
                    continue
                self.visible_devices.append(device)
                row = Gtk.ListBoxRow()
                row.device = device
                box = Gtk.Box()
                for key, width in self.columns:
                    value = cell_value(device, key, self.text, self.rt.settings['language'])
                    label = Gtk.Label(label=value or self.text('unknown'), xalign=0, yalign=.5,
                                      ellipsize=Pango.EllipsizeMode.END)
                    label.set_size_request(width, -1)
                    label.set_max_width_chars(max(8, width // 9))
                    full = device.get(key, value)
                    label.set_tooltip_text('; '.join(full) if isinstance(full, list) else value)
                    label.add_css_class('device-cell')
                    box.append(label)
                row.set_child(box)
                self.listbox.append(row)
                if device['id'] in ids:
                    self.listbox.select_row(row)

        def busy(self, yes):
            for name in ('start', 'refresh', 'active', 'oui_update', 'merge', 'details', 'language_install'):
                self.actions[name].set_enabled(not yes)
            self.network_select.set_sensitive(not yes)
            self.actions['start'].set_enabled(not yes and self.selected_network() is not None)
            self.actions['cancel'].set_enabled(yes)
            self.spinner.set_spinning(yes)

        def run_job(self, function, done):
            if self.worker:
                return
            self.cancel_event = threading.Event()
            self.busy(True)
            def work():
                try:
                    result = function()
                    GLib.idle_add(finish, result, None)
                except Exception as exc:
                    GLib.idle_add(finish, None, exc)
            def finish(result, error):
                self.worker = None
                self.busy(False)
                if self.cancel_event.is_set() or isinstance(error, Cancelled):
                    self.set_status('cancelled')
                elif error:
                    self.fail(error)
                else:
                    try:
                        done(result)
                    except Exception as exc:
                        self.fail(exc)
                if self.closing:
                    self.shutdown_window()
                return False
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()

        def progress(self, key, value):
            def apply():
                if self.cancel_event.is_set():
                    return False
                if key == 'progress':
                    self.set_status(key, done=value[0], total=value[1])
                else:
                    self.set_status(key, value=value)
                return False
            GLib.idle_add(apply)

        def start_scan(self, *_):
            network = self.selected_network()
            if not network or self.worker:
                return
            try:
                self.rt.save()
            except OSError as exc:
                self.fail(exc)
                return
            self.set_status('busy')
            def done(result):
                observations, self.warning_keys = result
                self.store.commit_scan(network, observations, self.warning_keys)
                logging.info(self.text('log_scan'))
                self.network_changed()
                self.set_status('complete', **scan_summary(self.devices))
                self.show_warnings()
            self.run_job(lambda: scan(network, self.cancel_event, self.progress,
                                     self.rt.settings['active'], self.rt.settings['max_hosts']), done)

        def cancel(self, *_):
            if self.worker:
                self.cancel_event.set()
                self.actions['cancel'].set_enabled(False)
                self.set_status('cancelling')

        def fail(self, exc):
            logging.error('%s: %s', self.text('log_error'), exc, exc_info=exc)
            error = self.text(exc.code, status=exc.status) if isinstance(exc, VendorUpdateError) else (self.text(str(exc)) if str(exc) in ('network_changed',) else str(exc))
            self.set_status('error', error=error)

        def dialog(self, title_key, width=700, height=520):
            window = Gtk.Window(transient_for=self.window, modal=True, title=self.text(title_key))
            window.set_default_size(width, height)
            window.add_css_class('showipmac')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            for side in ('top', 'bottom', 'start', 'end'):
                getattr(box, 'set_margin_' + side)(16)
            window.set_child(box)
            return window, box

        def details(self, *_):
            rows = self.listbox.get_selected_rows()
            if len(rows) != 1:
                self.set_status('select_one')
                return
            device = rows[0].device
            window, box = self.dialog('details')
            box.append(self.label('name'))
            name = Gtk.Entry(text=device['name'], max_length=200)
            box.append(name)
            lines = [self.text('identity_note')]
            if device.get('is_local'):
                lines.append(self.text('local_device'))
            lines.append(self.text('vendor') + ': ' + ('; '.join(sorted({v for o in device['history'] if (v := self.vendors.lookup(o['mac']))})) or self.text('unknown')))
            if device.get('other_names'):
                lines.append(self.text('other_names') + ': ' + '; '.join(device['other_names']))
            if device['private_mac']:
                lines.append(self.text('private_mac'))
            if device['changed']:
                lines.append(self.text('changed'))
            lines.extend([self.text('first_seen') + ': ' + local_time(device['first_seen'], self.rt.settings['language']), self.text('last_seen') + ': ' + local_time(device['last_seen'], self.rt.settings['language']), '', self.text('history')])
            for obs in device['history']:
                lines.append('\n' + '\n'.join(self.text(k) + ': ' + ((local_time(obs.get(k), self.rt.settings['language']) if k in ('first_seen','last_seen') else obs.get(k)) or self.text('unknown'))
                             for k in ('scope', 'interface', 'mac', 'hostname', 'first_seen', 'last_seen', 'evidence'))
                             + '\nIP: ' + obs['ip'])
            view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            view.get_buffer().set_text('\n'.join(lines))
            scroll = Gtk.ScrolledWindow(vexpand=True)
            scroll.set_child(view)
            box.append(scroll)
            def save(*_):
                try:
                    self.store.rename(device['id'], name.get_text())
                    self.network_changed()
                    window.destroy()
                except Exception as exc:
                    self.fail(exc)
            box.append(self.button('save', save))
            box.append(self.button('close', lambda *_: window.destroy()))
            window.present()

        def merge_devices(self, *_):
            rows = self.listbox.get_selected_rows()
            if len(rows) not in (1, 2):
                self.set_status('select_two')
                return
            first = rows[0].device
            candidates = [dict(r) for r in self.store.db.execute(
                'SELECT * FROM devices WHERE id<>? ORDER BY name,first_seen', (first['id'],))]
            if len(rows) == 2:
                candidates = [rows[1].device]
            if not candidates:
                self.set_status('select_two')
                return
            window, box = self.dialog('merge', 600, 300)
            choices = []
            for d in candidates:
                macs = [r[0] for r in self.store.db.execute(
                    'SELECT DISTINCT mac FROM observations WHERE device=?', (d['id'],))]
                choices.append((d['name'] or self.text('unknown')) + ' · ' + ', '.join(macs))
            choice = Gtk.DropDown.new_from_strings(choices)
            box.append(choice)
            label = self.label('merge_note')
            label.set_wrap(True)
            box.append(label)
            box.append(Gtk.Label(label=first['name'] or ', '.join(first['mac']), selectable=True))
            def accept(*_):
                try:
                    self.store.merge(first['id'], candidates[choice.get_selected()]['id'])
                    self.network_changed()
                    window.destroy()
                except Exception as exc:
                    self.fail(exc)
            window.confirm_button = self.button('merge_confirm', accept)
            window.cancel_button = self.button('cancel', lambda *_: window.destroy())
            box.append(window.cancel_button)
            box.append(window.confirm_button)
            window.present()

        def export_dialog(self, kind, devices=None, parent=None):
            devices = [dict(device) for device in (self.visible_devices if devices is None else devices)
                       if device['status'] in ('new', 'known')]
            chooser = Gtk.FileChooserDialog(title=self.text(kind), transient_for=parent or self.window,
                                            modal=True, action=Gtk.FileChooserAction.SAVE)
            chooser.add_button(self.text('cancel'), Gtk.ResponseType.CANCEL)
            chooser.add_button(self.text('save'), Gtk.ResponseType.ACCEPT)
            chooser.set_default_response(Gtk.ResponseType.ACCEPT)
            file_filter = Gtk.FileFilter()
            file_filter.set_name(kind.upper())
            file_filter.add_pattern('*.' + kind)
            chooser.add_filter(file_filter)
            # Use an existing visible directory, never the private profile folder.
            folder = ROOT if (ROOT / 'start.sh').is_file() else Path.home()
            chooser.set_current_folder(Gio.File.new_for_path(str(folder.resolve())))
            chooser.set_current_name('showipmac.' + kind)
            def response(dialog, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    try:
                        selected = dialog.get_file()
                        if selected is None or selected.get_path() is None:
                            raise ValueError(self.text('export_local_file'))
                        path = Path(selected.get_path())
                        if path.resolve() == (self.rt.path / 'devices.sqlite3').resolve():
                            raise ValueError(self.text('export_database_protected'))
                        export(path, devices, self.text, kind)
                        self.set_status('exported', path=str(path))
                    except Exception as exc:
                        self.fail(exc)
                dialog.destroy()
            chooser.connect('response', response)
            chooser.present()
            return chooser

        def update_vendors(self, *_):
            if self.worker:
                return
            self.set_status('updating')
            def done(vendors):
                self.vendors = vendors
                self.retranslate()
                self.network_changed()
                self.set_status('updated')
            self.run_job(lambda: Vendors.update(self.rt.path / 'vendors.json', self.cancel_event), done)

        def language_settings(self):
            window, box = self.dialog('language_install', width=700, height=350)
            box.append(Gtk.Label(label=self.text('source_url'), xalign=0, wrap=True))
            source = Gtk.Entry(text=self.rt.settings['source_url'])
            source.set_name('language_source_url')
            window.source_entry = source
            box.append(source)
            box.append(Gtk.Label(label=self.text('language_pack_note'), xalign=0, wrap=True))
            def save_source():
                self.rt.settings['source_url'] = source.get_text().strip()
                self.rt.save()
            def download(*_):
                try:
                    save_source()
                    self.download_language(source.get_text().strip(), window)
                except Exception as exc:
                    self.fail(exc)
            def save(*_):
                try:
                    save_source()
                    window.destroy()
                except Exception as exc:
                    self.fail(exc)
            box.append(self.button('import_language', lambda *_: self.import_language(window)))
            box.append(self.button('download_language', download))
            box.append(self.button('save', save))
            box.append(self.button('cancel', lambda *_: window.destroy()))
            window.present()
            return window

        def language_installed(self, code):
            self.rt.reload_languages()
            self.lang_codes = sorted(self.rt.languages)
            self.change_language(code)
            self.set_status('language_installed', name=self.rt.languages[code]['language_name'])

        def language_job(self, function, done):
            from languages import ProgramIdentityError
            def work():
                try:
                    return function()
                except ProgramIdentityError as exc:
                    logging.exception('language_program_identity')
                    raise RuntimeError(self.text('language_wrong_program')) from exc
                except FileExistsError as exc:
                    raise RuntimeError(self.text('language_exists')) from exc
                except Exception as exc:
                    logging.exception('language_install_failed')
                    raise RuntimeError(self.text('language_failed')) from exc
            self.set_status('languages_loading')
            self.run_job(work, done)

        def import_language(self, parent=None):
            from languages import import_pack
            chooser = Gtk.FileChooserDialog(title=self.text('import_language'), transient_for=parent or self.window,
                                            modal=True, action=Gtk.FileChooserAction.OPEN)
            chooser.add_button(self.text('cancel'), Gtk.ResponseType.CANCEL)
            chooser.add_button(self.text('import_language'), Gtk.ResponseType.ACCEPT)
            file_filter = Gtk.FileFilter()
            file_filter.set_name('JSON')
            file_filter.add_pattern('*.json')
            chooser.add_filter(file_filter)
            chooser.set_current_folder(Gio.File.new_for_path(str(ROOT if (ROOT / 'start.sh').exists() else Path.home())))
            def response(dialog, result):
                selected = dialog.get_file()
                dialog.destroy()
                if result == Gtk.ResponseType.ACCEPT and selected and selected.get_path():
                    self.language_job(lambda: import_pack(selected.get_path(), self.rt.path), self.language_installed)
            chooser.connect('response', response)
            chooser.present()
            return chooser

        def download_language(self, source, parent=None):
            from languages import download_catalog, download_pack
            if self.worker:
                return
            if not source:
                self.set_status('no_language_source')
                return
            dialog = Gtk.Dialog(title=self.text('download_language'), transient_for=parent or self.window, modal=True)
            area = dialog.get_content_area()
            area.set_spacing(12)
            for side in ('top', 'bottom', 'start', 'end'):
                getattr(area, 'set_margin_' + side)(16)
            status = Gtk.Label(label=self.text('languages_loading'), xalign=0, wrap=True)
            area.append(status)
            choice = Gtk.DropDown.new_from_strings([])
            choice.set_sensitive(False)
            area.append(choice)
            entries = []
            dialog.add_button(self.text('cancel'), Gtk.ResponseType.CANCEL)
            dialog.add_button(self.text('download_language'), Gtk.ResponseType.OK)
            dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
            def load():
                try:
                    return download_catalog(source), None
                except Exception as exc:
                    logging.exception('language_catalog_failed')
                    return None, exc
            def loaded(result):
                if not dialog.get_visible():
                    return
                items, error = result
                if error:
                    status.set_label(self.text('language_failed'))
                    self.set_status('error', error=self.text('language_failed'))
                    return
                entries[:] = sorted((item for item in items if item['code'] not in self.rt.languages), key=lambda item: item['name'].casefold())
                choice.set_model(Gtk.StringList.new([item['name'] for item in entries]))
                choice.set_selected(0 if entries else Gtk.INVALID_LIST_POSITION)
                choice.set_sensitive(bool(entries))
                dialog.set_response_sensitive(Gtk.ResponseType.OK, bool(entries))
                status.set_label(self.text('languages_available' if entries else 'languages_none'))
                self.set_status('languages_available' if entries else 'languages_none')
            def response(window, result):
                selected = choice.get_selected()
                window.destroy()
                if result == Gtk.ResponseType.OK and selected < len(entries):
                    code = entries[selected]['code']
                    self.language_job(lambda: download_pack(source, code, self.rt.path), self.language_installed)
            dialog.connect('response', response)
            dialog.language_choice = choice
            dialog.language_status = status
            dialog.present()
            self.language_job(load, loaded)
            return dialog

        def open_help(self):
            language = self.rt.settings['language']
            choices = [self.rt.path / 'languages' / language / 'help.html', self.rt.path / 'help' / language / 'index.html', ROOT / 'help' / language / 'index.html', ROOT / 'help/en/index.html']
            for path in choices:
                if path.is_file():
                    webbrowser.open(path.as_uri())
                    return

        def about(self, *_):
            native_language(self.rt.settings['language'])
            dialog = Gtk.AboutDialog(transient_for=self.window, modal=True,
                                     program_name='showipmac', version=VERSION,
                                     comments=self.text('app_subtitle'), authors=['Josef'],
                                     license_type=Gtk.License.GPL_3_0_ONLY,
                                     website=PROJECT_URL, website_label='GitHub · showipmac')
            dialog.add_css_class('showipmac')
            dialog.set_logo(Gdk.Texture.new_from_filename(str(ROOT / 'assets/showipmac.png')))
            dialog.present()
            return dialog

        def on_close(self, *_):
            if self.worker:
                self.closing = True
                self.cancel()
            else:
                self.shutdown_window()
            return True

        def shutdown_window(self):
            self.rt.settings['width'] = max(500, min(3000, self.window.get_width()))
            self.rt.settings['height'] = max(500, min(3000, self.window.get_height()))
            try:
                self.rt.save()
            except OSError as exc:
                logging.error('%s: %s', self.text('log_error'), exc)
            self.store.close()
            self.window.destroy()
            self.quit()

    return Application()


if __name__ == '__main__':
    raise SystemExit(main())
