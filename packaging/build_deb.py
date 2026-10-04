"""Allowlisted DEB build; no development database or configuration is shipped."""
import argparse
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def stage_package(stage):
    if stage.exists():
        raise FileExistsError(stage)
    # Read the literal central version without running application code.
    version = re.search(r"^VERSION = '([0-9]+\.[0-9]+\.[0-9]+)'$", (ROOT / 'core.py').read_text(), re.M).group(1)
    app = stage / 'usr/share/showipmac'
    files = ['core.py', 'runtime.py', 'presentation.py', 'showipmac.py', 'languages.py', 'LICENSE', 'THIRD_PARTY.md']
    files += [str(p.relative_to(ROOT)) for folder in ('assets', 'vendor', 'help/assets', 'modules') for p in sorted((ROOT / folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    files += [f'lang/{code}.json' for code in ('de', 'en')]
    files += [f'help/{code}/index.html' for code in ('de', 'en')]
    for name in files:
        source = ROOT / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f'Invalid package source: {source}')
        dest = app / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    doc = stage / 'usr/share/doc/showipmac'
    doc.mkdir(parents=True)
    for source, target in [('LICENSE', 'copyright'), ('README.md', 'README.md'), ('THIRD_PARTY.md', 'THIRD_PARTY.md'), ('CHANGELOG.md', 'CHANGELOG.md')]:
        shutil.copyfile(ROOT / source, doc / target)
    launcher = stage / 'usr/bin/showipmac'
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nunset SHOWIPMAC_DATA_DIR\nexec /usr/bin/python3 -B /usr/share/showipmac/showipmac.py "$@"\n')
    lifecycle = (ROOT / 'packaging/desktop_lifecycle.py').read_text()
    import ast
    desktop = next(ast.literal_eval(node.value) for node in ast.parse(lifecycle).body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'DESKTOP' for t in node.targets))
    desktop_file = stage / 'usr/share/applications/showipmac.desktop'
    desktop_file.parent.mkdir(parents=True)
    desktop_file.write_text(desktop)
    control = stage / 'DEBIAN'
    control.mkdir()
    size = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
    (control / 'control').write_text(f'''Package: showipmac
Version: {version}
Section: net
Priority: optional
Architecture: all
Maintainer: Josef
Installed-Size: {(size + 1023) // 1024}
Depends: python3 (>= 3.10), python3-gi, python3-requests, python3-bs4, gir1.2-gtk-4.0, iproute2, iputils-ping, libc-bin, libx11-6, util-linux
Recommends: avahi-utils
Description: Local network device discovery with GTK 4
 German and English interfaces, offline help and local device storage.
''')
    for hook, condition in [('postinst', "action != 'configure'"), ('prerm', "action not in ('remove', 'purge')")]:
        (control / hook).write_text(lifecycle.replace("action not in ('configure', 'remove', 'purge')", condition))
    (control / 'md5sums').write_text(''.join(f'{hashlib.md5(p.read_bytes()).hexdigest()}  {p.relative_to(stage)}\n' for p in sorted(stage.rglob('*')) if p.is_file() and control not in p.parents))
    for p in stage.rglob('*'):
        p.chmod(0o755 if p.is_dir() else 0o644)
    for p in (launcher, control / 'postinst', control / 'prerm'):
        p.chmod(0o755)
    if shutil.which('desktop-file-validate'):
        subprocess.run(['desktop-file-validate', str(desktop_file)], check=True)
    return version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage-only', type=Path)
    args = parser.parse_args()
    if args.stage_only:
        stage_package(args.stage_only)
        return
    import tempfile
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='deb-', dir=work) as temporary:
        stage = Path(temporary) / 'package'
        version = stage_package(stage)
        output = ROOT / 'dist' / f'showipmac_{version}_all.deb'
        if output.exists():
            raise FileExistsError(output)
        output.parent.mkdir(exist_ok=True)
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(output)], check=True)
        print(output)


if __name__ == '__main__':
    main()
