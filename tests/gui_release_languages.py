"""Render all eight release languages and verify their offline help selection."""
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
from core import ROOT,Network
from languages import install_pack
from runtime import Runtime
from showipmac import create_application
net=Network('qa0',('192.0.2.1/24',),'',True)
with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='release-languages-') as directory:
 path=Path(directory)
 for code in ('ar','es','fr','hi','pt','ru','tr','zh'):
  install_pack(json.loads((ROOT/f'github/sprachpakete/{code}.json').read_text()),path)
 app=create_application(Runtime(path));errors=[];index=0
 codes=['ar','es','fr','hi','pt','ru','tr','zh','de','en']
 def tick():
  global index
  try:
   if app.worker:return True
   code=codes[index];app.change_language(code)
   assert app.window.get_direction()==(Gtk.TextDirection.RTL if code=='ar' else Gtk.TextDirection.LTR)
   assert app.window.get_title().startswith(app.text('title'))
   assert app.menu_bar.get_menu_model().get_n_items()==6
   with patch('showipmac.webbrowser.open') as browser:
    app.open_help()
    selected=path/f'languages/{code}/help.html' if code not in ('de','en') else ROOT/f'help/{code}/index.html'
    browser.assert_called_once_with(selected.as_uri())
   index+=1
   if index==len(codes):app.on_close();return False
  except Exception as exc:
   errors.append(repr(exc));app.on_close();return False
  return True
 with patch('showipmac.discover_networks',return_value=[net]):
  GLib.timeout_add(200,tick);app.run(['gui-release-languages'])
 assert not errors,errors
print('GTK: eight release languages plus DE/EN; menu, titles, RTL/LTR and offline help passed.')
