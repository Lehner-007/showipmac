"""Drive two menu scans with eleven controlled devices through real GTK."""
import sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','4.0')
from gi.repository import GLib
from core import Network, ROOT
from runtime import Runtime
from showipmac import create_application
net=Network('test0',('192.0.2.1/24',),'00:11:22:33:44:55',False)
observations=[dict(ip=f'192.0.2.{i}',mac=f'00:11:22:33:44:{i:02x}',interface='test0',hostname='',evidence='REACHABLE') for i in range(1,12)]
with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='recognition-gui-') as directory:
 app=create_application(Runtime(Path(directory)))
 phase=0;errors=[];started=time.monotonic()
 def tick():
  global phase
  try:
   assert time.monotonic()-started<15,'timeout'
   if app.worker:return True
   if phase==0:
    app.actions['start'].activate(None);phase=1
   elif phase==1:
    assert app.status_args==dict(found=11,new=11,known=0),app.status_args
    app.actions['start'].activate(None);phase=2
   else:
    assert app.status_args==dict(found=11,new=0,known=11),app.status_args
    assert all(d['status']=='known' for d in app.visible_devices)
    assert '11 bekannt' in app.status.get_label()
    print('GTK: 11/11/0 -> 11/0/11; table and summary verified')
    app.on_close();return False
  except Exception as exc:
   errors.append(repr(exc));app.on_close();return False
  return True
 with patch('showipmac.discover_networks',return_value=[net]),patch('showipmac.scan',return_value=(observations,[])):
  GLib.timeout_add(150,tick)
  app.run(['recognition-qa'])
 assert not errors,errors
