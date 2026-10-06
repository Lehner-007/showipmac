import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from core import ROOT, VERSION
from languages import install_pack, validate_pack
from runtime import Runtime


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.path=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def fixture(self):
        root=self.path/'project';root.mkdir()
        for name in ('erstellegithub.sh','LICENSE'):
            shutil.copyfile(ROOT/name,root/name)
        for name,text in {'core.py':"VERSION = '1.2.3'\n",'showipmac.py':'print("test")\n','README.md':'GPL-3.0-only\n','erstelledeb.sh':'#!/bin/sh\nexit 0\n','.gitignore':'.config/\nwork/\ndist/\n'}.items():
            (root/name).write_text(text)
        (root/'tests').mkdir();(root/'tests/test_stub.py').write_text('# public test\n')
        return root
    def run_script(self,root,*args,input=''):
        return subprocess.run(['bash',str(root/'erstellegithub.sh'),*args],input=input,text=True,capture_output=True,timeout=20,env=dict(os.environ,GIT_CEILING_DIRECTORIES=str(self.path)))

    def test_standard_preparation_excludes_private_and_preserves_sources(self):
        root=self.fixture()
        for folder in ('.config','work','__pycache__'):
            (root/folder).mkdir();(root/folder/'private.txt').write_text('not public')
        (root/'TESTBERICHT.md').write_text('private test report')
        before=(root/'core.py').read_bytes()
        result=self.run_script(root)
        self.assertEqual(result.returncode,0,result.stderr)
        stage=next((root/'dist').glob('showipmac-github-*'))
        self.assertFalse((stage/'.config').exists())
        self.assertFalse((stage/'work').exists())
        self.assertFalse((stage/'TESTBERICHT.md').exists())
        self.assertEqual((stage/'core.py').read_bytes(),before)
        self.assertEqual((root/'core.py').read_bytes(),before)
        self.assertFalse((root/'.git').exists())
        self.assertEqual(self.run_script(root).returncode,0)
        self.assertEqual(len(list((root/'dist').glob('showipmac-github-*'))),2)

    def test_bad_missing_versions_and_required_files(self):
        for version in ('', '1.2', 'bad', '01.2.3'):
            root=self.fixture();(root/'core.py').write_text(f'VERSION = {version!r}\n')
            self.assertNotEqual(self.run_script(root).returncode,0)
            shutil.rmtree(root)
        for name in ('core.py','LICENSE','README.md'):
            root=self.fixture();(root/name).unlink()
            self.assertNotEqual(self.run_script(root).returncode,0)
            shutil.rmtree(root)

    def test_env_secret_and_symlink_rejected(self):
        for name in ('.env','secret_test.py','linked.py'):
            root=self.fixture()
            if name=='.env':(root/name).write_text('placeholder')
            elif name=='secret_test.py':
                (root/'tests'/name).write_text('value = "'+('gh'+'p_'+'x'*30)+'"\n')
            else:(root/'tests'/name).symlink_to(root/'core.py')
            self.assertNotEqual(self.run_script(root).returncode,0)
            shutil.rmtree(root)

    def test_publish_eof_and_existing_tag_no_push(self):
        root=self.fixture()
        def git(*args):return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)
        git('init','-b','main');git('config','user.name','Test');git('config','user.email','test@example.invalid')
        git('remote','add','origin','github:example/showipmac.git')
        result=self.run_script(root,'--publish')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Keine ausdrückliche Bestätigung',result.stderr)
        self.assertEqual(git('tag','--list').stdout,b'')
        git('add','.');git('commit','-m','Local fixture');git('tag','v1.2.3')
        result=self.run_script(root,'--publish')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('existiert bereits',result.stderr)

    def test_all_eight_packs_complete_importable_and_correct_version(self):
        folder=ROOT/'github/sprachpakete'
        catalog=json.loads((folder/'catalog.json').read_text())
        codes={row['code'] for row in catalog['languages']}
        self.assertEqual(codes,{'ar','es','fr','hi','pt','ru','tr','zh'})
        base=json.loads((ROOT/'lang/en.json').read_text())
        for code in sorted(codes):
            data=json.loads((folder/f'{code}.json').read_text())
            actual,strings,help_text=validate_pack(data)
            self.assertEqual(actual,code)
            self.assertEqual(set(strings),set(base))
            self.assertIn('<h1>',help_text)
            self.assertEqual(install_pack(data,self.path/'profile'),code)
        rt=Runtime(self.path/'profile')
        self.assertTrue(codes.issubset(rt.languages))
        metadata=json.loads((ROOT/'github/version.json').read_text())
        self.assertEqual(metadata['program_id'],'showipmac')
        self.assertEqual(metadata['version'],VERSION)
        if 'deb' in metadata:
            import hashlib
            from unittest.mock import patch
            from modules.updates import release_info
            from core import VERSION_INFO_URL
            with patch('modules.updates.github_json',return_value=metadata):
                info=release_info(VERSION_INFO_URL)
            package=ROOT/'dist'/info['deb']['filename']
            self.assertTrue(package.is_file())
            self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(),info['deb']['sha256'])
            import subprocess
            self.assertEqual(subprocess.check_output(['dpkg-deb','-f',str(package),'Package'],text=True).strip(),'showipmac')
            self.assertEqual(subprocess.check_output(['dpkg-deb','-f',str(package),'Version'],text=True).strip(),VERSION)
        self.assertEqual(set(p.stem for p in (ROOT/'lang').glob('*.json')),{'de','en'})
