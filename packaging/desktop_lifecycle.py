#!/usr/bin/python3
"""Manage Showipmac desktop entries and private runtime data, as their owner."""
import os
import configparser
import shlex
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

DESKTOP = '''[Desktop Entry]
Type=Application
Name=Showipmac
GenericName=Local network devices
GenericName[de]=Geräte im lokalen Netzwerk
Comment=Discover local network devices
Comment[de]=Geräte im lokalen Netzwerk erfassen
Exec=showipmac
Icon=/usr/share/showipmac/assets/showipmac.png
Terminal=false
Categories=Network;
Keywords=Network;IP;MAC;
StartupNotify=true
'''
MANAGED = DESKTOP + 'X-Showipmac-Managed=true\n'


def desktop_dir(home):
    config = home / '.config/user-dirs.dirs'
    try:
        for line in config.read_text().splitlines():
            if line.startswith('XDG_DESKTOP_DIR='):
                value = line.split('=', 1)[1].strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
                    if value == '$HOME':
                        return None  # Disabled desktop directory.
                    value = value.replace('${HOME}', str(home)).replace('$HOME', str(home))
                    target = Path(value)
                    if target.is_absolute() and target != home and target.is_dir():
                        return target
    except FileNotFoundError:
        pass
    return next((home / n for n in ('Schreibtisch', 'Desktop') if (home / n).is_dir()), None)


def is_shortcut(path):
    if path.is_symlink():
        return os.readlink(path) == '/usr/share/applications/showipmac.desktop'
    if not path.is_file():
        return False
    try:
        cfg = configparser.ConfigParser(interpolation=None, strict=False)
        cfg.read_string(path.read_text())
        command = shlex.split(cfg.get('Desktop Entry', 'Exec', fallback=''))
        return bool(command) and command[0] in ('showipmac', '/usr/bin/showipmac')
    except (OSError, UnicodeError, ValueError, configparser.Error):
        return False


def remove_tree(path):
    # Never follow a directory symlink into unrelated user files.
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def user_action(action, home):
    desktop = desktop_dir(home)
    if action == 'configure':
        if desktop is None:
            return
        target = desktop / 'showipmac.desktop'
        if (target.exists() or target.is_symlink()) and not is_shortcut(target):
            print('Showipmac: eigene Desktop-Datei bleibt erhalten:', target, file=sys.stderr)
            return
        if target.is_symlink():
            target.unlink()
        # Run as user, never as root; no privilege escalation via user paths.
        target.write_text(MANAGED)
        target.chmod(0o755)
        if shutil.which('gio'):
            subprocess.run(['gio', 'set', str(target), 'metadata::trusted', 'true'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return
    if action not in ('remove', 'purge'):
        return
    for folder in filter(None, [desktop, home / '.local/share/applications', home / '.config/autostart']):
        if folder.is_dir():
            for target in folder.glob('*.desktop'):
                if is_shortcut(target):
                    target.unlink()
    trash = home / '.local/share/Trash'
    if (trash / 'files').is_dir():
        for target in (trash / 'files').glob('*.desktop'):
            if is_shortcut(target):
                target.unlink()
                (trash / 'info' / (target.name + '.trashinfo')).unlink(missing_ok=True)
    # App-owned XDG directories only; never the development project or arbitrary reports.
    locations = [home / '.config', home / '.cache', home / '.local/share', home / '.local/state']
    for var in ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME'):
        value = os.environ.get(var)
        if value and Path(value).is_absolute():
            locations.append(Path(value))
    for base in set(locations):
        remove_tree(base / 'showipmac')


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--user':
        if os.geteuid() == 0:
            raise SystemExit('Benutzerbereinigung darf nicht als root laufen.')
        user_action(sys.argv[2], Path(pwd.getpwuid(os.geteuid()).pw_dir))
        return
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action not in ('configure', 'remove', 'purge'):
        return  # No deletion on upgrade, failed upgrade, or deconfigure.
    if os.geteuid() != 0:
        raise SystemExit('Paketverwaltung benötigt root.')
    failed = []
    for user in pwd.getpwall():
        if not 1000 <= user.pw_uid < 65534 or user.pw_shell.endswith(('/nologin', '/false')):
            continue
        if not Path(user.pw_dir).is_dir():
            continue
        result = subprocess.run(['/usr/sbin/runuser', '-u', user.pw_name, '--',
                                 '/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--user', action])
        if result.returncode:
            failed.append(user.pw_name)
    if failed:
        raise SystemExit('Showipmac-Benutzerdateien nicht vollständig bearbeitet: ' + ', '.join(failed))


if __name__ == '__main__':
    main()
