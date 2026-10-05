"""Generate download metadata from the actual verified release DEB."""
import hashlib,json,subprocess,sys,re
from pathlib import Path

def metadata(package,version):
 package=Path(package)
 fields={key:subprocess.check_output(['dpkg-deb','-f',str(package),key],text=True).strip() for key in ('Package','Version','Architecture')}
 if fields!={'Package':'showipmac','Version':version,'Architecture':'all'}:raise ValueError('Release package identity mismatch')
 return {'program_id':'showipmac','version':version,'deb':{'url':f'https://github.com/Lehner-007/showipmac/releases/download/v{version}/{package.name}','filename':package.name,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}}

if __name__=='__main__':
 root=Path(__file__).resolve().parent.parent
 version=re.search(r"^VERSION = '([0-9]+\.[0-9]+\.[0-9]+)'$",(root/'core.py').read_text(),re.M).group(1)
 result=metadata(sys.argv[1],version)
 Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n')
