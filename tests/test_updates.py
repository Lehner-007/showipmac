"""Actual GTK building blocks and numeric IPv4 ordering."""
import json,time,threading,unittest
from unittest.mock import patch
from pathlib import Path
import test_building_blocks as helpers
from test_building_blocks import pump
from core import ROOT,VERSION
from presentation import device_sort_key
from modules.model import PROJECT
from runtime import Runtime
from modules.jobs import JobContext,Cancelled
from modules.updates import release_info
from modules.integration import initial_update as startup_check

class UpdateGuiTests(unittest.TestCase):
 setUp=helpers.SharedTests.setUp
 tearDown=helpers.SharedTests.tearDown
 def test_startup_check_without_opt_in(self):
  self.assertFalse(self.rt.settings['update_check'])
  with patch('modules.updates.release_info',return_value={'version':VERSION,'deb':None}) as fetch:
   startup_check(self.app);pump(.25)
  fetch.assert_called_once_with(PROJECT['update_url'])
  self.assertEqual(self.app.update_status_key,'software_current')
 def test_default_sort_and_info(self):
  app=self.app
  self.assertEqual(app.sort_column,'ipv4');self.assertFalse(app.sort_reverse)
  values=['192.0.2.10','192.0.2.9','192.0.2.1','192.0.2.0','192.0.2.2']
  devices=[{'ipv4':[v]} for v in values]+[{'ipv4':[]}]
  actual=sorted(devices,key=lambda d:device_sort_key(d,'ipv4',app.text,'de'))
  self.assertEqual([d['ipv4'][0].rsplit('.',1)[-1] for d in actual[:-1]],['0','1','2','9','10'])
  model=app.menu_bar.get_menu_model()
  self.assertEqual(model.get_n_items(),4)
  dialog=app.show_info();end=time.monotonic()+8
  while not hasattr(dialog,'tool_results') and time.monotonic()<end:pump(.05)
  names={t['name'] for t in dialog.tool_results}
  self.assertIn('ip',names);self.assertIn('ping',names);self.assertNotIn('tidy',names)
  app.change_language('en');self.assertEqual(dialog.get_title(),app.text('info'))
  app.window.close_dialog(dialog)
  about=app.about();pump();self.assertLessEqual(about.get_logo().get_width(),128);self.assertLessEqual(about.get_logo().get_height(),128);about.destroy()
 def test_update_status_fixed_sources(self):
  app=self.app;dialog=app.settings_dialog();c=dialog.template_controls
  self.assertNotIn('update_url',c);self.assertNotIn('source_url',c)
  for code in ('de','en'):
   app.change_language(code)
   for version,status,enabled in ((VERSION,'software_current',False),('99.0.0','software_update',True)):
    with patch('modules.updates.release_info',return_value={'version':version,'deb':{'url':'test'}}):
     app.window.check_update();pump(.25)
    self.assertEqual(c['update_status'].get_label(),app.text(status));self.assertEqual(c['download'].get_sensitive(),enabled)
   with patch('modules.updates.release_info',side_effect=ValueError('wrong')):app.window.check_update();pump(.25)
   self.assertEqual(c['update_status'].get_label(),app.text('software_check_failed'));self.assertFalse(c['download'].get_sensitive())
  self.rt.path.joinpath('settings.json').write_text(json.dumps(dict(self.rt.settings,source_url='https://bad.invalid',update_url='https://bad.invalid')))
  opts=Runtime(self.rt.path).settings
  self.assertEqual(opts['source_url'],PROJECT['source_url']);self.assertEqual(opts['update_url'],PROJECT['update_url'])
 def test_progress_four_lines_and_download_cancel(self):
  app=self.app;app.update_info={'version':'99.0.0','deb':{'url':'test'}}
  def task(info,context):
   context.progress(1,2)
   while True:context.check_cancel();time.sleep(.02)
  with patch('modules.updates.download_update',task):
   self.assertTrue(app.window.download_update());pump(.2)
   dialog=app.progress_dialog;sizes=[]
   self.assertFalse(app.window.download_update())
   for text in ('short','one\ntwo\nthree\nfour','https://example.org/'+'longtext'*140):
    dialog.task_label.set_label(text);pump(.2);sizes.append((dialog.get_width(),dialog.get_height()))
   self.assertEqual(len(set(sizes)),1)
   app.cancel();pump(.3);self.assertIsNone(app.worker);self.assertIsNone(app.progress_dialog)
