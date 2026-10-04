"""Exercise real GTK widgets/main loop with isolated synthetic data; no network probes."""
from pathlib import Path
import json
import sys
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
from core import ROOT, Network, Cancelled
from runtime import Runtime
from showipmac import create_application

import tempfile
path=Path(tempfile.mkdtemp(prefix='gui-qa-020-',dir=ROOT/'work'))
path.mkdir(exist_ok=True)
rt=Runtime(path)
# A synthetic extension validates discovery and RTL/LTR without shipping a new language.
langdir=path/'lang';langdir.mkdir(exist_ok=True)
extra=dict(rt.languages['en']);extra['language_name']='العربية (QA)'
(langdir/'ar.json').write_text(json.dumps(extra))
rt=Runtime(path)
network=Network('qa0',('192.0.2.1/27','2001:db8::1/64'),'00:11:22:33:44:55',True)
app=create_application(rt)
observations=[dict(mac='00:11:22:33:44:66',ip='192.0.2.2',interface='qa0',hostname='long-hostname-for-layout-testing.example',evidence='REACHABLE'),dict(mac='00:11:22:33:44:66',ip='2001:db8::2',interface='qa0',hostname='',evidence='STALE')]
app.store.commit_scan(network,observations)
app.store.rename(app.store.devices(network.scope)[0]['id'],'Testgerät – Printer')
errors=[]
phase=0
started=time.monotonic()

def pump():
 global phase
 try:
  if time.monotonic()-started>20:
   raise AssertionError('GUI timeout')
  if app.worker:
   return True
  if phase==0:
   assert len(app.devices)==1
   app.listbox.select_row(app.listbox.get_row_at_index(0))
   app.change_language('en')
   assert app.menu_bar.get_menu_model().get_n_items()==5
   assert app.network_select.get_model().get_string(0)=='192.0.2.0/27 — virtual → qa0'
   assert len(app.listbox.get_selected_rows())==1
   app.search.set_text('Printer')
   app.render_devices()
   assert len(app.visible_devices)==1
   app.filter.set_selected(3)
   assert len(app.visible_devices)==0
   app.filter.set_selected(0)
   assert len(app.visible_devices)==1
   app.listbox.select_row(app.listbox.get_row_at_index(0))
   app.change_language('ar')
   assert app.window.get_direction()==Gtk.TextDirection.RTL
   app.change_language('de')
   assert app.window.get_direction()==Gtk.TextDirection.LTR
   assert app.search.get_text()=='Printer'
   assert len(app.listbox.get_selected_rows())==1
   app.details()
   for win in list(Gtk.Window.list_toplevels()):
    if win is not app.window:
     win.destroy()
   app.window.set_default_size(900,600)
   Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',True)
   GLib.timeout_add(700,screenshot,'gui-dark-small.png')
   phase=1
   return True
  if phase==1:
   # Cancel a real background worker, then verify no additional scan was saved.
   before=app.store.db.execute('SELECT count(*) FROM scans').fetchone()[0]
   app.test_before=before
   def slow():
    while not app.cancel_event.wait(.02):
     pass
    raise Cancelled()
   app.run_job(slow,lambda _: (_ for _ in ()).throw(AssertionError('cancel committed')))
   app.cancel()
   phase=2
   return True
  if phase==2:
   assert app.status_key=='cancelled'
   assert app.store.db.execute('SELECT count(*) FROM scans').fetchone()[0]==app.test_before
   assert app.actions['start'].get_enabled()
   Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',False)
   app.window.set_default_size(1500,800)
   GLib.timeout_add(700,screenshot,'gui-light-de.png')
   phase=3
   return True
  if phase==3:
   app.change_language('en')
   GLib.timeout_add(700,screenshot,'gui-light-en.png')
   phase=4
   return True
  if phase==4:
   app.search.set_text('')
   other=dict(mac='00:11:22:33:44:77',ip='192.0.2.9',interface='qa0',hostname='other',evidence='REACHABLE')
   app.store.commit_scan(network,observations+[other])
   app.network_changed()
   app.render_devices()
   app.listbox.select_all()
   assert len(app.listbox.get_selected_rows())==2
   app.merge_devices()
   dialog=next(w for w in Gtk.Window.list_toplevels() if w is not app.window)
   assert len(app.store.devices(network.scope))==2
   dialog.cancel_button.emit('clicked')
   assert len(app.store.devices(network.scope))==2
   app.merge_devices()
   dialog=next(w for w in Gtk.Window.list_toplevels() if w is not app.window)
   dialog.confirm_button.emit('clicked')
   assert len(app.store.devices(network.scope))==1
   app.choose_sort('ipv4')
   assert app.sort_column=='ipv4' and not app.sort_reverse
   app.choose_sort('ipv4')
   assert app.sort_reverse
   app.on_close()
   return False
 except Exception as exc:
  errors.append(repr(exc))
  app.on_close()
  return False

def screenshot(name):
 import subprocess
 app.window.present()
 subprocess.run(['gnome-screenshot','-w','-f',str(ROOT/'work'/name)],check=True)
 return False

with patch('showipmac.discover_networks',return_value=[network]):
 GLib.timeout_add(1600,pump)
 app.run(['gui-qa'])
assert not errors,errors
assert json.loads((path/'settings.json').read_text())['language']=='en'
print('GUI QA passed: real GTK, selection, DE/EN, extension RTL/LTR, search, details, small/dark, cancellation, persistence, sorting, merge cancel/confirm, close.')
