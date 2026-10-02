import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import ROOT
from languages import (validate_pack, install_pack, import_pack, download_pack,
                       download_catalog, github_json, ProgramIdentityError, MAX_PACK)
from runtime import Runtime


def pack(code='zz'):
    return dict(program_id='showipmac', code=code, name='Custom language',
                strings={'language_name':'Custom language','menu_settings':'Custom settings',
                         'complete':'{found} / {new} / {known}'},
                help_html='<html><body><h1>Custom help</h1><script>alert(1)</script><img src="https://example.com/tracker"><p onclick="bad()">Offline</p></body></html>')


class LanguagePackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_import_and_restart_offline(self):
        source = self.path/'custom.json'
        source.write_text(json.dumps(pack()))
        self.assertEqual(import_pack(source,self.path/'profile'), 'zz')
        rt = Runtime(self.path/'profile')
        self.assertEqual(rt.languages['zz']['language_name'], 'Custom language')
        rt.settings['language']='zz'
        rt.save()
        rt = Runtime(self.path/'profile')
        self.assertEqual(rt.text('menu_settings'), 'Custom settings')
        self.assertEqual(rt.text('csv'), 'Export CSV')
        self.assertEqual(rt.text('complete',found=3,new=1,known=2), '3 / 1 / 2')
        help_text = (rt.path/'languages/zz/help.html').read_text()
        self.assertIn('Custom help',help_text)
        self.assertNotIn('<script',help_text)
        self.assertNotIn('<img',help_text)
        self.assertNotIn('onclick',help_text)

    def test_existing_pack_unchanged(self):
        install_pack(pack(),self.path)
        original=(self.path/'languages/zz/pack.json').read_bytes()
        data=pack();data['name']='Replacement'
        with self.assertRaises(FileExistsError):install_pack(data,self.path)
        self.assertEqual((self.path/'languages/zz/pack.json').read_bytes(),original)

    def test_validation_wrong_program_code_placeholders_and_help(self):
        for key,value in [('program_id','checkweb'),('code','../outside'),('code',None),('code','de'),('strings',{'complete':'{wrong}'}),('strings',{'unknown_key':'bad'}),('help_html','')]:
            with self.subTest(key=key,value=value):
                data=pack();data[key]=value
                with self.assertRaises(ValueError):validate_pack(data)
        self.assertFalse((self.path/'languages').exists())

    def test_custom_name_and_rtl(self):
        data=pack('xx-AA');data['strings'].pop('language_name')
        install_pack(data,self.path)
        self.assertEqual(Runtime(self.path).languages['xx-AA']['language_name'],'Custom language')
        code,_,help_text=validate_pack(pack('ar-QA'))
        self.assertIn('dir="rtl"',help_text)

    def test_download_catalog_and_pack(self):
        catalog=dict(program_id='showipmac',languages=[dict(code='de',name='German'),dict(code='zz',name='Custom')])
        with patch('languages.github_json',return_value=catalog):
            self.assertEqual(download_catalog('https://raw.githubusercontent.com/owner/repo/main/packs'),[dict(code='zz',name='Custom')])
        with patch('languages.github_json',return_value=pack()):
            self.assertEqual(download_pack('https://raw.githubusercontent.com/owner/repo/main/packs','zz',self.path),'zz')
        with patch('languages.github_json',return_value=pack('yy')):
            with self.assertRaises(ValueError):download_pack('https://raw.githubusercontent.com/owner/repo/main/packs','zz',self.path)
        with patch('languages.github_json',return_value=dict(catalog,program_id='checkweb')):
            with self.assertRaises(ProgramIdentityError):download_catalog('https://github.com/owner/repo')
        with patch('languages.github_json',return_value=dict(catalog,languages=[dict(code='zz',name='A'),dict(code='zz',name='B')])):
            with self.assertRaises(ValueError):download_catalog('https://github.com/owner/repo')

    def test_invalid_url_empty_source_and_size(self):
        for url in ('http://github.com/a','https://example.com/a','https://user:pass@github.com/a'):
            with self.assertRaises(ValueError):github_json(url)
        with self.assertRaises(ValueError):download_catalog('')
        path=self.path/'large.json';path.write_bytes(b'x'*(MAX_PACK+1))
        with self.assertRaises(ValueError):import_pack(path,self.path)

    def test_empty_source_uses_published_default_custom_source_preserved(self):
        from core import LANGUAGE_SOURCE_URL
        self.path.joinpath('settings.json').write_text(json.dumps({'source_url':''}))
        self.assertEqual(Runtime(self.path).settings['source_url'],LANGUAGE_SOURCE_URL)
        custom='https://raw.githubusercontent.com/example/custom/main/packs'
        self.path.joinpath('settings.json').write_text(json.dumps({'source_url':custom}))
        self.assertEqual(Runtime(self.path).settings['source_url'],custom)

    def test_download_size_timeout_and_redirect(self):
        from unittest.mock import MagicMock
        session=MagicMock();response=MagicMock()
        session.__enter__.return_value=session
        session.get.return_value.__enter__.return_value=response
        response.is_redirect=False
        response.iter_content.return_value=[b'x'*(MAX_PACK+1)]
        with patch('languages.requests.Session',return_value=session):
            with self.assertRaises(ValueError):github_json('https://raw.githubusercontent.com/owner/repo/main/pack.json')
        response.is_redirect=True
        with patch('languages.requests.Session',return_value=session):
            with self.assertRaises(ValueError):github_json('https://github.com/owner/repo')
