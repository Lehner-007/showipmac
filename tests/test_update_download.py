import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess
from modules import model
from modules.updates import release_info,download_update,check_package
from modules.jobs import JobContext,Cancelled

ROOT=Path(__file__).resolve().parent.parent
SOURCE='https://raw.githubusercontent.com/Lehner-007/showipmac/main/github/version.json'
PAYLOAD=b'!<arch>\nTest package data'
INFO=dict(version='9.0.0',deb=dict(url='https://github.com/Lehner-007/showipmac/releases/download/v9.0.0/test.deb',filename='test.deb',sha256=hashlib.sha256(PAYLOAD).hexdigest()))

class Response:
    is_redirect=False
    headers={'Content-Length':str(len(PAYLOAD))}
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def raise_for_status(self):pass
    def iter_content(self,size):yield PAYLOAD

class Session:
    trust_env=False
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def get(self,*_,**kwargs):return Response()

class UpdateTests(unittest.TestCase):
    def context(self):return JobContext(threading.Event(),lambda *_:None)
    def test_metadata_identity_hash_and_project_binding(self):
        data=dict(INFO,program_id=model.PROGRAM_ID)
        with patch('modules.updates.github_json',return_value=data):self.assertEqual(release_info(SOURCE),INFO)
        for deb in [dict(INFO['deb'],sha256='bad'),dict(INFO['deb'],filename='../test.deb'),dict(INFO['deb'],url=INFO['deb']['url'].replace('/showipmac/','/other/'))]:
            with patch('modules.updates.github_json',return_value=dict(data,deb=deb)),self.assertRaises(ValueError):release_info(SOURCE)
    def test_download_hash_collision_and_cancel(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
            folder=Path(temp)
            with patch('modules.updates.requests.Session',Session),patch('modules.updates.subprocess.run',side_effect=[CompletedProcess([],0,stdout='Package: '+model.PROJECT['deb']['package']+'\nVersion: 9.0.0\nArchitecture: all\n'),CompletedProcess([],0,stdout='amd64\n')]):
                result=download_update(INFO,self.context(),folder)
            self.assertEqual(result.read_bytes(),PAYLOAD)
            result.write_bytes(b'existing different file')
            with self.assertRaises(ValueError):download_update(INFO,self.context(),folder)
            self.assertEqual(result.read_bytes(),b'existing different file');result.unlink()
            bad=dict(INFO,deb=dict(INFO['deb'],sha256='0'*64))
            with patch('modules.updates.requests.Session',Session),self.assertRaises(ValueError):download_update(bad,self.context(),folder)
            self.assertEqual(list(folder.iterdir()),[])
            context=self.context();context.cancel_event.set()
            with patch('modules.updates.requests.Session',Session),self.assertRaises(Cancelled):download_update(INFO,context,folder)
            self.assertEqual(list(folder.iterdir()),[])
    def test_unsafe_redirect_and_cancel_after_partial_write(self):
        class UnsafeResponse(Response):
            is_redirect=True
            headers={'Location':'https://bad.invalid/package.deb'}
        class UnsafeSession(Session):
            def get(self,*_,**kwargs):return UnsafeResponse()
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
            folder=Path(temp)
            with patch('modules.updates.requests.Session',UnsafeSession),self.assertRaises(ValueError):download_update(INFO,self.context(),folder)
            self.assertEqual(list(folder.iterdir()),[])
            context=self.context()
            context._report=lambda *_:context.cancel_event.set()
            with patch('modules.updates.requests.Session',Session),self.assertRaises(Cancelled):download_update(INFO,context,folder)
            self.assertEqual(list(folder.iterdir()),[])

