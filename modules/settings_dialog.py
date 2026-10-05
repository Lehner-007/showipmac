"""Einstellungsanordnung aus der Grundvorlage, mit showipmac-Feldern."""
from gi.repository import Gtk
from .model import PROJECT

def vertical():
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)

def show_settings(self, *_):
    for existing in self.dialogs:
        if existing.get_name() == 'settings_dialog' and existing.get_visible():
            existing.present()
            return existing
    window = self.track(Gtk.Window(title=self.tr('settings'), transient_for=self, modal=True,
                                   default_width=650, default_height=700))
    window.set_name('settings_dialog')
    layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    window.set_child(layout)
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    layout.append(scroll)
    box = vertical()
    scroll.set_child(box)
    controls = {}
    def group(key):
        if box.get_first_child() is not None:
            box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(self.label(key, xalign=0, wrap=True))
    codes = sorted(self.runtime.languages)
    language = Gtk.DropDown.new_from_strings([self.tr.language_name(code) for code in codes])
    language.set_selected(codes.index(self.tr.code))
    def refresh(code):
        if window not in self.dialogs:
            return
        codes[:] = sorted(self.runtime.languages)
        language.set_model(Gtk.StringList.new([self.tr.language_name(c) for c in codes]))
        language.set_selected(codes.index(code))
        self.set_status('installed')
    if PROJECT['settings']:
        group('program_settings')
        for field in PROJECT['settings']:
            if field['type'] == 'boolean':
                widget = Gtk.CheckButton(label=self.tr(field['label']))
                widget.set_active(self.opts[field['key']])
                box.append(widget)
            else:
                row = Gtk.Box(spacing=8)
                row.append(self.label(field['label'], xalign=0, hexpand=True, wrap=True))
                widget = Gtk.SpinButton.new_with_range(field['min'], field['max'], 1)
                widget.set_value(self.opts[field['key']])
                row.append(widget)
                box.append(row)
            controls[field['key']] = widget
    vendor_button = self.button('oui_update', self.update_vendors)
    box.append(vendor_button)
    group('update_settings')
    automatic = Gtk.CheckButton(label=self.tr('update_check'), active=self.opts['update_check'])
    box.append(automatic)
    box.append(self.label('update_interval_label', xalign=0, wrap=True))
    row = Gtk.Box(spacing=8)
    row.append(self.label('every'))
    interval = Gtk.SpinButton.new_with_range(1, 365, 1)
    interval.set_value(self.opts['update_interval_value'])
    row.append(interval)
    units = ('days', 'weeks', 'months')
    unit = Gtk.DropDown.new_from_strings([self.tr(u) for u in units])
    unit.set_selected(units.index(self.opts['update_interval_unit']))
    row.append(unit)
    box.append(row)
    box.append(self.label('update_interval_help', xalign=0, wrap=True))
    status=self.label('software_checking',xalign=0,wrap=True)
    box.append(status)
    download=self.button('update_download',lambda *_:self.download_update())
    box.append(download)
    group('language_extensions')
    box.append(self.label('language', xalign=0))
    box.append(language)
    box.append(self.button('import_language', lambda *_: self.import_language(window, refresh)))
    box.append(self.button('download_language', lambda *_: self.download_language(PROJECT['source_url'], window, refresh)))
    def save(*_):
        new = self.opts.copy()
        interval.update()
        new.update(language=codes[language.get_selected()], update_check=automatic.get_active(),
                   update_interval_value=interval.get_value_as_int(),
                   update_interval_unit=units[unit.get_selected()], update_url=PROJECT['update_url'],
                   source_url=PROJECT['source_url'])
        for key, widget in controls.items():
            if isinstance(widget, Gtk.SpinButton):
                widget.update()
                new[key] = widget.get_value_as_int()
            else:
                new[key] = widget.get_active()
        try:
            self.runtime.save_values(new)
        except OSError:
            self.notify('write_error')
            return
        self.opts.update(new)
        self.close_dialog(window)
        self.apply_language(new['language'])
        self.set_status('saved')
        self.logger.info(self.tr('saved'))
    layout.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
    footer = Gtk.Box(spacing=10, halign=Gtk.Align.END, margin_top=12, margin_bottom=12,
                     margin_start=16, margin_end=16)
    cancel = self.button('cancel', lambda *_: self.close_dialog(window))
    save_button = self.button('save_settings', save)
    footer.append(cancel)
    footer.append(save_button)
    layout.append(footer)
    # Prüfzugang und Erweiterungspunkt für Projekte.
    window.template_controls = dict(language=language, codes=codes, fields=controls,
                    interval=interval, unit=unit, update_status=status, download=download,
                    automatic=automatic, save=save_button, cancel=cancel)
    self.refresh_updates()
    window.present()
    return window

