"""Configuration and external translations. SPDX-License-Identifier: GPL-3.0-only."""
import json
import logging
import locale
import os
import re
from pathlib import Path
from core import ROOT, LANGUAGE_SOURCE_URL, VERSION_INFO_URL, atomic_json

DEFAULTS = {'config_version': 1, 'language': 'de', 'active': True, 'max_hosts': 4096, 'width': 1500, 'height': 800, 'source_url': LANGUAGE_SOURCE_URL,
            'update_check': False, 'update_interval_value': 1, 'update_interval_unit': 'weeks',
            'update_url': VERSION_INFO_URL, 'last_update_check': '',
            'window_width': 1500, 'window_height': 800, 'window_x': 0, 'window_y': 0,
            'window_position_known': False, 'window_maximized': False}

class Runtime:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.settings = dict(DEFAULTS)
        self.warnings = []
        config = self.path / 'settings.json'
        self.bad_config = False
        if config.exists():
            try:
                data = json.loads(config.read_text())
                if not isinstance(data, dict):
                    raise ValueError('settings')
                for key, default in DEFAULTS.items():
                    value = data.get(key, default)
                    if type(value) is not type(default):
                        self.warnings.append('config_error')
                        continue
                    if key == 'max_hosts' and not 1 <= value <= 65536:
                        self.warnings.append('config_error')
                        continue
                    if key in ('width', 'height') and not 240 <= value <= 10000:
                        self.warnings.append('config_error')
                        continue
                    if key == 'update_interval_value' and not 1 <= value <= 365:
                        self.warnings.append('config_error')
                        continue
                    if key == 'update_interval_unit' and value not in ('days', 'weeks', 'months'):
                        self.warnings.append('config_error')
                        continue
                    if key in ('window_width', 'window_height') and not 240 <= value <= 10000:
                        continue
                    if key in ('window_x', 'window_y') and not -100000 <= value <= 100000:
                        continue
                    if key == 'config_version' and value != 1:
                        raise ValueError('config_version')
                    self.settings[key] = value
                for old, new in (('width', 'window_width'), ('height', 'window_height')):
                    if new not in data:
                        self.settings[new] = self.settings[old]
            except (ValueError, OSError):
                self.warnings.append('config_error')
                self.bad_config = True
        self.settings['source_url'] = LANGUAGE_SOURCE_URL
        self.settings['update_url'] = VERSION_INFO_URL
        self.reload_languages()
        if self.settings['language'] not in self.languages:
            self.settings['language'] = 'en'

    def save_values(self, values):
        previous = self.settings
        self.settings = dict(values)
        try:
            self.save()
        finally:
            self.settings = previous
        previous.update(values)

    def reload_languages(self):
        self.languages = {}
        for folder in (ROOT / 'lang', self.path / 'lang'):
            for source in folder.glob('*.json'):
                if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,30}', source.stem):
                    continue
                try:
                    data = json.loads(source.read_text())
                    if not isinstance(data, dict) or not all(isinstance(v,str) for v in data.values()) or not data.get('language_name'):
                        continue
                    self.languages[source.stem] = data
                except (OSError, ValueError):
                    logging.warning('invalid_language: %s', source.name)
        from languages import validate_pack
        for folder in sorted((self.path / 'languages').glob('*')):
            if not folder.is_dir() or folder.is_symlink():
                continue
            try:
                code, strings, _ = validate_pack(json.loads((folder / 'pack.json').read_text('utf-8')))
                if folder.name != code:
                    continue
                data = dict(strings)
                if not data.get('language_name'):
                    metadata = json.loads((folder / 'metadata.json').read_text('utf-8'))
                    data['language_name'] = metadata['name']
                self.languages[code] = data
            except (OSError, ValueError, KeyError):
                logging.warning('invalid_language_pack: %s', folder.name)

    def text(self, key, **values):
        text = self.languages.get(self.settings['language'], {}).get(key)
        if text is None:
            text = self.languages.get('en', {}).get(key, key)
            logging.warning('missing_translation: %s', key)
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return self.languages.get('en', {}).get(key, key).format(**values)

    def save(self):
        config = self.path / 'settings.json'
        if self.bad_config and config.exists():
            from datetime import datetime
            config.rename(config.with_name('settings.invalid.' + datetime.now().strftime('%Y%m%d%H%M%S%f') + '.json'))
            self.bad_config = False
        atomic_json(config, self.settings)


def native_language(code):
    """Keep native GTK dialog strings in the application language (process only)."""
    os.environ['LANGUAGE'] = code + ':en'
    candidates = ['de_DE.UTF-8'] if code == 'de' else ['en_US.UTF-8'] if code == 'en' else [locale.normalize(code + '.UTF-8')]
    locale.setlocale(locale.LC_MESSAGES, 'C')
    for candidate in [*candidates, 'C.UTF-8', '']:
        try:
            locale.setlocale(locale.LC_MESSAGES, candidate)
            return
        except locale.Error:
            continue
