"""Connect shared window components to showipmac without replacing network logic."""
import logging
from gi.repository import Gtk, GLib
from core import VERSION, now
from presentation import cell_value
from .model import bind_runtime, update_due
from .window_state import WindowState


class Translations:
    def __init__(self, runtime):
        self.runtime = runtime

    @property
    def code(self):
        return self.runtime.settings['language']

    def __call__(self, key, **values):
        return self.runtime.text(key, **values)

    def language_name(self, code):
        return self.runtime.languages[code]['language_name']

    def display_value(self, row, key):
        return cell_value(row, key, self, self.code)


class DeviceResults:
    def __init__(self, app):
        self.app = app
        self.columns = [(key, key) for key, _ in app.columns]

    def rows(self, visible=False):
        # Includes missing records: export scope is selected consciously.
        return [dict(row) for row in (self.app.visible_devices if visible else self.app.devices)]


def attach(app):
    window = app.window
    bind_runtime(app.rt)
    window.opts = app.rt.settings
    window.runtime = app.rt
    window.tr = Translations(app.rt)
    window.alive = True
    window.dialogs = []
    window.file_dialogs = []
    window.bindings = []
    window.logger = logging.getLogger()
    window.results = DeviceResults(app)
    window.set_status = app.set_status
    window.notify = lambda key, **values: app.set_status('error', error=app.text(key, **values))
    def track(dialog):
        window.dialogs.append(dialog)
        dialog.connect('destroy', lambda *_: forget(dialog))
        return dialog
    def forget(dialog):
        if dialog in window.dialogs:
            window.dialogs.remove(dialog)
        window.bindings[:] = [(w, m, k) for w, m, k in window.bindings if w is not dialog and w.get_root() is not None]
    def close_dialog(dialog):
        forget(dialog)
        dialog.destroy()
    def label(key, **kwargs):
        widget = Gtk.Label(label=app.text(key), **kwargs)
        window.bindings.append((widget, 'set_label', key))
        return widget
    def button(key, callback):
        widget = Gtk.Button(label=app.text(key))
        widget.connect('clicked', callback)
        window.bindings.append((widget, 'set_label', key))
        return widget
    window.track, window.close_dialog, window.label, window.button = track, close_dialog, label, button
    window.apply_language = app.change_language
    window.update_vendors = app.update_vendors
    def import_language(parent, refresh):
        def installed(code):
            app.rt.reload_languages()
            refresh(code)
        return app.import_language(parent, installed)
    window.import_language = import_language
    window.download_language = lambda source, parent, refresh: app.download_language(source, parent, lambda code: (app.rt.reload_languages(), refresh(code)))
    window.check_update = lambda source: check_update(app, source)
    app.window_state = WindowState(window)
    app.update_timer = GLib.timeout_add_seconds(60, lambda: automatic_update(app))
    GLib.idle_add(lambda: (automatic_update(app), False)[1])


def automatic_update(app):
    if app.window.alive and not app.worker and not app.closing and update_due(app.rt.settings):
        check_update(app, app.rt.settings['update_url'], automatic=True)
    return app.window.alive


def check_update(app, source, automatic=False):
    from languages import download_version
    if app.worker:
        return
    if not source.strip() or 'xxxx' in source.split('/'):
        app.window.notify('no_source' if not source.strip() else 'repository_placeholder')
        return
    def done(version):
        if source == app.rt.settings['update_url']:
            app.rt.settings['last_update_check'] = now()
            app.rt.save()
        newer = tuple(map(int, version.split('.'))) > tuple(map(int, VERSION.split('.')))
        if newer or not automatic:
            key = 'new_version' if newer else 'latest'
            dialog = app.window.track(Gtk.Window(title=app.text('update_settings'), transient_for=app.window, modal=True, default_width=420))
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
            box.append(Gtk.Label(label=app.text(key, version=version if newer else VERSION), wrap=True))
            box.append(app.window.button('close', lambda *_: app.window.close_dialog(dialog)))
            dialog.set_child(box)
            dialog.present()
    app.run_job(lambda: download_version(source), done, title_key='checking_version', cancellable=False)
