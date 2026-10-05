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
    app.update_info=None
    app.update_status_key='software_checking'
    app.update_check_running=False
    window.check_update=lambda source=None:check_update(app,source)
    window.download_update=lambda:download_available(app)
    window.refresh_updates=lambda:refresh_updates(app)
    app.window_state = WindowState(window)
    app.update_timer = GLib.timeout_add_seconds(60, lambda: automatic_update(app))
    GLib.idle_add(lambda: (initial_update(app), False)[1])


def initial_update(app):
    check_update(app)


def automatic_update(app):
    if app.window.alive and not app.worker and not app.closing and update_due(app.rt.settings):
        check_update(app, app.rt.settings['update_url'], automatic=True)
    return app.window.alive


def refresh_updates(app):
    for dialog in app.window.dialogs[:]:
        if dialog.get_name()!='settings_dialog':continue
        controls=dialog.template_controls
        controls['update_status'].set_label(app.text(app.update_status_key))
        newer=app.update_info and tuple(map(int,app.update_info['version'].split('.')))>tuple(map(int,VERSION.split('.')))
        controls['download'].set_sensitive(bool(newer and app.update_info.get('deb') and not app.worker and not app.update_check_running and not app.closing))


def check_update(app, source=None, automatic=False):
    from .updates import release_info
    from .model import PROJECT
    import threading
    if not app.window.alive or app.update_check_running:return
    app.update_check_running=True
    app.update_status_key='software_checking'
    refresh_updates(app)
    def finish(info,error):
        if not app.window.alive:return False
        app.update_check_running=False
        app.update_info=info
        if error:
            app.update_status_key='software_check_failed'
            logging.warning(app.text('software_check_failed'))
        else:
            app.rt.settings['last_update_check']=now()
            try:app.rt.save()
            except OSError as exc:app.fail(exc)
            newer=tuple(map(int,info['version'].split('.')))>tuple(map(int,VERSION.split('.')))
            app.update_status_key='software_update' if newer else 'software_current'
        refresh_updates(app)
        return False
    def worker():
        try:info,error=release_info(PROJECT['update_url']),None
        except Exception as exc:info,error=None,exc
        GLib.idle_add(finish,info,error)
    threading.Thread(target=worker,daemon=True).start()


def download_available(app):
    from .updates import download_update
    from .jobs import JobContext
    if app.worker or app.update_check_running or not app.update_info:return False
    info=app.update_info
    if not info.get('deb') or tuple(map(int,info['version'].split('.')))<=tuple(map(int,VERSION.split('.'))):return False
    def task():
        from .jobs import Cancelled
        try:return download_update(info,JobContext(app.cancel_event,lambda current,total:app.progress('progress',(current,total))))
        except Cancelled:raise
        except Exception:raise ValueError(app.text('update_download_error')) from None
    return app.run_job(task,lambda path:app.set_status('update_downloaded',path=str(path)),title_key='update_download')
