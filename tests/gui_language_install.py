"""Real GTK language install, catalog selection, RTL/LTR and offline help."""
import sys,tempfile,json,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib, Gio
from core import ROOT,Network
from languages import import_pack
from runtime import Runtime
from showipmac import create_application
from test_language_packs import pack
net=Network('qa0',('192.0.2.1/24',),'',True)
with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='language-gui-') as directory:
 path=Path(directory);rt=Runtime(path/'profile');app=create_application(rt)
 source=path/'custom.json';source.write_text(json.dumps(pack('ar-QA')))
 errors=[];phase=0;dialog=None;started=time.monotonic()
 def tick():
  global phase,dialog
  try:
   assert time.monotonic()-started<20,'timeout'
   if app.worker:return True
   if phase==0:
    assert app.lookup_action('language_install')
    settings=app.language_settings()
    from core import LANGUAGE_SOURCE_URL
    assert settings.source_entry.get_text()==LANGUAGE_SOURCE_URL
    settings.destroy()
    about=app.about();assert about.get_website()=='https://github.com/Lehner-007/showipmac';about.destroy()
    app.search.set_text('retain search')
    dialog=app.import_language()
    phase=0.25
   elif phase==0.25:
    dialog.set_current_folder(Gio.File.new_for_path(str(path)))
    phase=0.5
   elif phase==0.5:
    dialog.set_file(Gio.File.new_for_path(str(source)))
    phase=0.75
   elif phase==0.75:
    assert dialog.get_file().get_path()==str(source), 'selected import path'
    dialog.emit('response',Gtk.ResponseType.ACCEPT)
    phase=1
   elif phase==1:
    if 'ar-QA' not in rt.languages:
     return True
    assert rt.settings['language']=='ar-QA'
    assert app.window.get_direction()==Gtk.TextDirection.RTL
    assert 'ar-QA' in app.lang_codes
    assert app.search.get_text()=='retain search'
    with patch('showipmac.webbrowser.open') as browser:
     app.open_help()
     browser.assert_called_once_with((rt.path/'languages/ar-QA/help.html').as_uri())
    app.change_language('en')
    assert app.window.get_direction()==Gtk.TextDirection.LTR
    dialog=app.download_language('https://raw.githubusercontent.com/test/test/main/packs')
    phase=2
   elif phase==2:
    assert dialog.language_choice.get_model().get_n_items()==1
    dialog.emit('response',Gtk.ResponseType.OK)
    phase=3
   elif phase==3:
    assert rt.settings['language']=='zz'
    assert 'zz' in app.lang_codes
    assert (rt.path/'languages/zz/help.html').is_file()
    dialog=app.download_language('https://raw.githubusercontent.com/test/test/main/packs')
    phase=4
   elif phase==4:
    assert dialog.language_choice.get_model().get_n_items()==0
    assert not dialog.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive()
    dialog.destroy()
    app.change_language('de')
    app.download_language('')
    assert app.status_key=='no_language_source'
    app.on_close();return False
  except Exception as exc:
   import traceback
   errors.append(f'phase {phase}: '+traceback.format_exc())
   if dialog:dialog.destroy()
   app.on_close();return False
  return True
 catalog=dict(program_id='showipmac',languages=[dict(code='ar-QA',name='Custom RTL'),dict(code='zz',name='Custom')])
 def fake_json(url):
  return catalog if url.endswith('catalog.json') else pack('zz')
 with patch('showipmac.discover_networks',return_value=[net]),patch('languages.github_json',side_effect=fake_json):
  GLib.timeout_add(400,tick)
  app.run(['gui-language-install'])
 assert not errors,errors
print('GTK: custom install, immediate language/RTL switch, preserved search, offline help, catalog download, existing/empty and no source passed.')
