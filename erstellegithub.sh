#!/usr/bin/env bash
# Separater GitHub-Quellstand; Benutzerpaketierung bleibt in erstellezip.sh.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 /dev/fd/3 "$SCRIPT_DIR" "$@" 3<<'PY'
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(sys.argv[1]).resolve()
ROOT_FILES={'showipmac.py','core.py','runtime.py','presentation.py','languages.py','THIRD_PARTY.md','README.md','CHANGELOG.md','LICENSE',
            'start.sh','erstellezip.sh','erstelledeb.sh','erstellegithub.sh','.gitignore',
            '.gitattributes','pyproject.toml','setup.cfg','setup.py',
            'requirements.txt','requirements-dev.txt','MANIFEST.in'}
SOURCE_DIRS={'modules','tests','assets','help','lang','docs','github','.github','packaging','vendor'}
EXCLUDED_DIRS={'.git','.venv','venv','__pycache__','.config','dist','logs','log',
               'work','tmp','temp','.cache','.pytest_cache','.mypy_cache',
               '.ruff_cache','.idea','.vscode','node_modules','backups','backup'}
EXCLUDED_SUFFIXES={'.pyc','.pyo','.log','.tmp','.temp','.swp','.swo','.bak','.orig','.rej'}
SECRET_NAMES={'.env','credentials','credentials.json','credentials.yaml',
              'credentials.yml','secrets.json','secrets.yaml','secrets.yml',
              'id_rsa','id_ed25519','id_ecdsa','id_dsa','.netrc','.pypirc',
              '.npmrc','token.txt','tokens.json','passwords.txt'}
SECRET_SUFFIXES={'.pem','.key','.p12','.pfx','.keystore'}
PATTERNS=[
 re.compile(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
 re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{20,}\b'),
 re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{20,}\b'),
 re.compile(rb'\bAKIA[A-Z0-9]{16}\b'),
 re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b'),
]
ASSIGNMENT=re.compile(rb'''(?im)^\s*["']?(?:password|passwd|api_key|apikey|access_token|auth_token|client_secret|secret_key)["']?\s*[:=]\s*["']([^"'\r\n]+)["']''')
PLACEHOLDERS={b'',b'test',b'example',b'dummy',b'placeholder',b'changeme',b'...'}

class Refused(Exception):pass

def fail(message):raise Refused(message)

def excluded(path):
 return str(path) in {'fehler.txt','TESTBERICHT.md','python_showipmac.md'} or any(part in EXCLUDED_DIRS for part in path.parts) or path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.endswith('~') or path.name.startswith('.#')

def secret_name(path):
 name=path.name.lower()
 return name in SECRET_NAMES or name.split('.')[0] in {'credentials','secrets','passwords','tokens','token','access_token','api_key'} or name.startswith('.env.') or path.suffix.lower() in SECRET_SUFFIXES

def eligible(path):
 return not excluded(path) and (str(path) in ROOT_FILES or (len(path.parts)>1 and path.parts[0] in SOURCE_DIRS))

def check_content(path,data):
 if secret_name(path):fail(f'Verdächtige Datei: {path}. Datei prüfen; nichts wurde gelöscht.')
 if any(pattern.search(data) for pattern in PATTERNS):fail(f'Möglicher Schlüssel oder Token in: {path}. Inhalt prüfen; nichts wurde gelöscht.')
 for match in ASSIGNMENT.finditer(data):
  value=match.group(1).strip()
  if value.lower() not in PLACEHOLDERS and not value.startswith((b'${',b'<')):
   fail(f'Mögliche Zugangsdaten in: {path}. Inhalt prüfen; nichts wurde gelöscht.')

def git(*args,check=True):
 try:
  result=subprocess.run(['git','-c','core.hooksPath=/dev/null','-C',str(ROOT),*args],capture_output=True,timeout=120)
 except FileNotFoundError:fail('Git ist nicht installiert.')
 except subprocess.TimeoutExpired:fail('Git-Vorgang hat das Zeitlimit überschritten.')
 if check and result.returncode:
  # Git-Ausgaben können Zugangsdaten aus einer lokalen Konfiguration enthalten.
  suffix=' Bereits angelegte lokale Commits/Tags und der Git-Index bleiben erhalten.' if args[0] in ('commit','tag','push') else ''
  fail(f'Git-Vorgang „{args[0]}“ fehlgeschlagen (Exit-Code {result.returncode}). Repository, Rechte und Verbindung prüfen.'+suffix)
 return result

def text_git(*args,check=True):return git(*args,check=check).stdout.decode('utf-8').strip()

def inventory():
 result={}
 for folder,dirs,files in os.walk(ROOT,followlinks=False):
  rel=Path(folder).relative_to(ROOT)
  kept=[]
  for name in sorted(dirs):
   p=rel/name
   if name in EXCLUDED_DIRS:continue
   if secret_name(p):fail(f'Verdächtiger Pfad: {p}')
   if (ROOT/p).is_symlink():fail(f'Symbolischer Link nicht zulässig: {p}')
   if rel==Path('.') and name not in SOURCE_DIRS:
    fail(f'Unbekannter Projektordner: {p}. Veröffentlichungsumfang zuerst ausdrücklich festlegen.')
   kept.append(name)
  dirs[:]=kept
  for name in sorted(files):
   p=rel/name
   if secret_name(p):fail(f'Verdächtige Datei: {p}. Datei prüfen; nichts wurde gelöscht.')
   if excluded(p) or str(p)=='.git':continue
   if not eligible(p):fail(f'Nicht zugeordnete Datei: {p}. Veröffentlichungsumfang zuerst ausdrücklich festlegen.')
   source=ROOT/p
   if source.is_symlink() or not source.is_file():fail(f'Keine reguläre Quelldatei: {p}')
   data=source.read_bytes();check_content(p,data)
   result[p]=data
 return result

def repo_info(remote):
 if not shutil.which('git'):return None,None,None
 probe=git('rev-parse','--show-toplevel',check=False)
 if probe.returncode:return None,None,None
 if Path(probe.stdout.decode().strip()).resolve()!=ROOT:fail('Projekt ist nicht die Wurzel des Git-Repositorys.')
 branch=text_git('symbolic-ref','--quiet','--short','HEAD',check=False) or None
 urls=text_git('remote','get-url','--push','--all',remote,check=False).splitlines()
 if len(urls)>1:fail('Mehrere Push-Adressen konfiguriert; eindeutiges Remote erforderlich.')
 url=urls[0] if urls else None
 if url and not re.fullmatch(r'(?:https://github\.com/|git@github\.com:|github:|ssh://git@github\.com/)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',url):
  fail('Remote muss eine GitHub-Adresse ohne eingebettete Zugangsdaten sein (SSH-Alias github ist erlaubt).')
 return ROOT,branch,url

def validate_index(candidates):
 # Also checks already tracked files: .gitignore alone never untracks them.
 staged=set(filter(None,git('diff','--cached','--name-only','-z').stdout.decode().split('\0')))
 names=git('ls-files','-z').stdout.decode().split('\0')
 removed=[]
 for name in filter(None,names):
  p=Path(name)
  if secret_name(p) or not eligible(p):fail(f'Unzulässige Datei bereits im Git-Index: {p}')
  if p not in candidates:
   if (ROOT/p).exists():fail(f'Git-Datei fehlt im geprüften Umfang: {p}')
   removed.append(p)
 # The snapshot must not silently publish unrelated staged content.
 for line in filter(None,git('ls-files','--stage','-z').stdout.decode().split('\0')):
  meta,name=line.split('\t',1)
  mode,oid,stage=meta.split()
  if stage!='0':fail(f'Ungelöster Git-Konflikt: {name}')
  if mode not in ('100644','100755'):fail(f'Nicht unterstützter Git-Dateityp: {name}')
  data=git('cat-file','blob',oid).stdout
  check_content(Path(name),data)
  if name in staged and Path(name) in candidates and data!=candidates[Path(name)]:
   fail(f'Gestagte Änderungen weichen vom geprüften Arbeitsstand ab: {name}. Index zuerst bewusst abstimmen.')
 return removed

def validate_history():
 if git('rev-parse','--verify','HEAD',check=False).returncode:return
 for line in text_git('rev-list','--objects','HEAD').splitlines():
  oid,sep,name=line.partition(' ')
  if not sep:continue
  path=Path(name)
  if secret_name(path) or excluded(path):fail(f'Unzulässiger Pfad in der mitzuübertragenden Git-Historie: {path}')
  if text_git('cat-file','-t',oid)=='blob':check_content(path,git('cat-file','blob',oid).stdout)

def main():
 parser=argparse.ArgumentParser(description='showipmac-Quellstand für GitHub prüfen und vorbereiten. Standard: kein Commit, Tag oder Push.')
 parser.add_argument('--publish',action='store_true',help='Nach Prüfung und ausdrücklicher Bestätigung committen, taggen und pushen')
 parser.add_argument('--remote',default='origin',help='Git-Remote (Standard: origin)')
 args=parser.parse_args(sys.argv[2:])
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',args.remote):fail('Ungültiger Remote-Name.')
 for name in ('core.py','README.md','LICENSE','showipmac.py','erstelledeb.sh','erstellegithub.sh','.gitignore'):
  path=ROOT/name
  if not path.is_file() or path.is_symlink():fail(f'Pflichtdatei fehlt oder ist verlinkt: {name}')
 import ast
 try:
  tree=ast.parse((ROOT/'core.py').read_text(encoding='utf-8'))
  values=[ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets)]
  if len(values)!=1 or not isinstance(values[0],str):fail('Zentrale Version fehlt oder ist uneindeutig.')
  version=values[0]
 except (SyntaxError,ValueError):fail('Zentrale Version ist ungültig.')
 if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)',version):fail('VERSION ist leer oder hat kein gültiges MAJOR.MINOR.PATCH-Format.')
 if not (ROOT/'tests').is_dir() or not any((ROOT/'tests').glob('test_*.py')):fail('Pflichtordner tests/ fehlt oder enthält keine Tests.')
 license_text=(ROOT/'LICENSE').read_text(encoding='utf-8')
 if 'GNU GENERAL PUBLIC LICENSE' not in license_text or 'Version 3, 29 June 2007' not in license_text:fail('LICENSE ist nicht als GNU GPL Version 3 erkennbar. Lizenz manuell prüfen.')
 if (ROOT/'github/version.json').is_file():
  import json
  metadata=json.loads((ROOT/'github/version.json').read_text())
  if metadata.get('program_id')!='showipmac' or metadata.get('version')!=version:fail('github/version.json stimmt nicht mit der zentralen Version überein.')
 candidates=inventory()
 repo,branch,url=repo_info(args.remote)
 tag='v'+version
 tag_exists=bool(repo and git('show-ref','--verify','--quiet','refs/tags/'+tag,check=False).returncode==0)
 removed=validate_index(candidates) if repo else []
 if repo:validate_history()
 print(f'showipmac {version}\n\nGitHub-Prüfung: OK\nRepository: {url or "nicht konfiguriert"}\nBranch: {branch or "nicht vorhanden / nicht feststellbar"}\nVersion: {version}\nTag: {tag}'+(' (bereits vorhanden; wird nicht überschrieben)' if tag_exists else ' (vorgesehen)'),flush=True)
 print(f'\nDateien für GitHub: {len(candidates)}',flush=True)
 for p in sorted(candidates):print('  '+str(p))
 for p in removed:print('  ENTFERNT: '+str(p))
 print('\nKeine ausgeschlossenen Dateien oder erkennbaren Geheimnisse im vorgesehenen Umfang gefunden.',flush=True)
 print('Die Prüfung erkennt offensichtliche Muster und ersetzt keine manuelle Inhaltsprüfung.',flush=True)
 if not args.publish:
  dist=ROOT/'dist'
  if dist.is_symlink() or (dist.exists() and not dist.is_dir()):fail('dist ist kein regulärer Ausgabeordner.')
  dist.mkdir(exist_ok=True)
  # A new directory for each run preserves all existing prepared data.
  stage=Path(tempfile.mkdtemp(prefix=f'showipmac-github-{version}-',dir=dist))
  for p,data in candidates.items():
   dest=stage/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
   dest.chmod(0o755 if os.access(ROOT/p,os.X_OK) else 0o644)
  for p,data in candidates.items():
   if (stage/p).read_bytes()!=data:fail(f'Kopierprüfung fehlgeschlagen: {p}; Ausgabe bleibt unter {stage} erhalten.')
  print(f'\nGeprüfter Quellstand: {stage}\nBereit für GitHub-Veröffentlichung. Kein Commit, Tag oder Push ausgeführt.')
  if not repo or not branch or not url:print('Vor einer Veröffentlichung Git-Repository, Branch und Remote einrichten.')
  return
 if not repo:fail('Für --publish muss im Projektordner ein Git-Repository vorhanden sein.')
 if not branch:fail('Für --publish muss ein aktueller Branch feststellbar sein; kein detached HEAD.')
 if not url:fail(f'Remote {args.remote} ist nicht konfiguriert.')
 if tag_exists:fail(f'Tag {tag} existiert bereits. Keine Überschreibung und kein Push.')
 head=text_git('rev-parse','--verify','HEAD',check=False)
 if not text_git('var','GIT_AUTHOR_IDENT',check=False):fail('Git-Autor ist nicht konfiguriert.')
 message=f'Release showipmac {version}'
 confirmation=f'VERÖFFENTLICHEN {version}'
 print(f'\nVorgesehen: Commit „{message}“, Tag {tag}, Push von {branch} und diesem Tag nach {url}.',flush=True)
 print(f'Zur Bestätigung exakt eingeben: {confirmation}',flush=True)
 try:answer=input().strip()
 except EOFError:answer=''
 if answer!=confirmation:fail('Keine ausdrückliche Bestätigung. Kein Commit, Tag oder Push ausgeführt.')
 if candidates!=inventory() or (repo,branch,url)!=repo_info(args.remote) or head!=text_git('rev-parse','--verify','HEAD',check=False):fail('Projekt oder Git-Zustand hat sich während der Bestätigung geändert; erneut prüfen.')
 validate_index(candidates)
 validate_history()
 if git('show-ref','--verify','--quiet','refs/tags/'+tag,check=False).returncode==0:fail(f'Tag {tag} wurde inzwischen angelegt; Abbruch.')
 if text_git('ls-remote',url,'refs/tags/'+tag):fail(f'Tag {tag} existiert bereits auf dem Remote. Kein Commit oder Push.')
 # Limit git add to the exact reviewed paths, including displayed deletions.
 paths=sorted(str(p) for p in set(candidates)|set(removed))
 for i in range(0,len(paths),100):git('add','--',*paths[i:i+100])
 validate_index(candidates)
 validate_history()
 if git('diff','--cached','--quiet',check=False).returncode:
  git('commit','-m',message)
 else:
  if not head:fail('Keine Dateien für einen ersten Commit vorhanden.')
  print('Keine neuen Änderungen zu committen; vorhandener Commit wird getaggt.')
 git('tag','-a',tag,'-m',message)
 # Atomic, explicit refs; never force, never all tags or all branches.
 git('push','--atomic',url,'HEAD:refs/heads/'+branch,'refs/tags/'+tag+':refs/tags/'+tag)
 print(f'\nshowipmac {version} erfolgreich veröffentlicht: {url}\nBranch: {branch}\nTag: {tag}')

try:main()
except (Refused,OSError,UnicodeError) as exc:
 print('FEHLER: '+str(exc),file=sys.stderr)
 sys.exit(1)
except KeyboardInterrupt:
 print('Abgebrochen. Bereits vorbereitete Dateien und lokale Git-Daten bleiben erhalten.',file=sys.stderr)
 sys.exit(130)
PY
