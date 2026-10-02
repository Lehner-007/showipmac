import io,json,unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import test_core
from core import Vendors, VendorUpdateError, OUI_URLS

class Response(io.BytesIO):
    def __init__(self):
        super().__init__(b'Assignment,Organization Name\n001122,Example Vendor\n')
        self.headers={'Last-Modified':'Tue, 29 Sep 2026 16:01:16 GMT'}

class VendorUpdateTests(unittest.TestCase):
    setUp=test_core.CoreTests.setUp
    tearDown=test_core.CoreTests.tearDown

    def test_success_user_agent_metadata_and_reload(self):
        path=self.path/'vendors.json'
        with patch('core.urlopen',side_effect=lambda *a,**kw:Response()) as download:
            db=Vendors.update(path,Event())
        self.assertEqual(db.data['date'],'2026-09-29')
        self.assertEqual(len(db.data['source_dates']),4)
        self.assertTrue(db.data['fetched_at'])
        self.assertEqual(Vendors.load(path).lookup('00:11:22:33:44:55'),'Example Vendor')
        for call in download.call_args_list:
            request=call.args[0]
            self.assertIn('showipmac/',request.get_header('User-agent'))
            self.assertIn(request.full_url,OUI_URLS.values())
            self.assertIsNone(request.data)

    def test_http_error_preserves_bytes_and_vendor(self):
        path=self.path/'vendors.json'
        with patch('core.urlopen',side_effect=lambda *a,**kw:Response()):Vendors.update(path,Event())
        before=path.read_bytes()
        with patch('core.urlopen',side_effect=HTTPError('https://standards-oui.ieee.org/',418,'Blocked',{},None)):
            with self.assertRaises(VendorUpdateError) as failure:Vendors.update(path,Event())
        self.assertEqual(failure.exception.code,'vendor_http')
        self.assertEqual(failure.exception.status,418)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(Vendors.load(path).lookup('00:11:22:33:44:55'),'Example Vendor')

    def test_partial_failure_keeps_database(self):
        path=self.path/'vendors.json';path.write_text('existing')
        with patch('core.urlopen',side_effect=[Response(),URLError('offline')]):
            with self.assertRaises(VendorUpdateError) as failure:Vendors.update(path,Event())
        self.assertEqual(failure.exception.code,'vendor_network')
        self.assertEqual(path.read_text(),'existing')

    def test_empty_individual_list_rejected(self):
        path=self.path/'vendors.json';path.write_text('existing')
        with patch('core.urlopen',side_effect=[Response(),io.BytesIO(b'Assignment,Organization Name\n')]):
            with self.assertRaises(VendorUpdateError):Vendors.update(path,Event())
        self.assertEqual(path.read_text(),'existing')
