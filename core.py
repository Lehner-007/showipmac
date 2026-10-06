"""showipmac network discovery and storage. SPDX-License-Identifier: GPL-3.0-only."""
from __future__ import annotations
import csv
import io
import ipaddress
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import time
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from email.utils import parsedate_to_datetime

VERSION = '0.8.2'
ROOT = Path(__file__).resolve().parent
PROJECT_URL = 'https://github.com/Lehner-007/showipmac'
LANGUAGE_SOURCE_URL = 'https://raw.githubusercontent.com/Lehner-007/showipmac/main/github/sprachpakete'
VERSION_INFO_URL = 'https://raw.githubusercontent.com/Lehner-007/showipmac/main/github/version.json'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


class Cancelled(Exception):
    pass


class DiscoveryError(Exception):
    pass


def command(args, cancel=None, timeout=5, allowed=(0,)):
    """No shell, bounded duration, terminate children on cancellation."""
    cancel = cancel or Event()
    if cancel.is_set():
        raise Cancelled()
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise DiscoveryError('missing_tool:' + args[0]) from exc
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancel.is_set():
                raise Cancelled()
            try:
                out, err = proc.communicate(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    raise DiscoveryError('timeout:' + args[0])
        if proc.returncode not in allowed:
            raise DiscoveryError(args[0] + ': ' + err.strip()[:500])
        return out
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.communicate(timeout=.3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()


def valid_mac(value):
    value = (value or '').strip().lower().replace('-', ':')
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', value):
        return ''
    if value == '00:00:00:00:00:00' or int(value[:2], 16) & 1:
        return ''
    return value


@dataclass(frozen=True)
class Network:
    interface: str
    addresses: tuple[str, ...]
    mac: str
    virtual: bool
    selected_ipv4: str = ""

    @property
    def networks(self):
        return tuple(sorted({str(ipaddress.ip_interface(a).network) for a in self.addresses
                             if not self.selected_ipv4 or ':' in a or str(ipaddress.ip_interface(a).network) == self.selected_ipv4}))

    @property
    def scope(self):
        # Includes network prefixes: the same interface in a different network is separate.
        return self.interface + '|' + '|'.join(self.networks)

    def contains(self, address):
        try:
            addr = ipaddress.ip_address(address.split('%')[0])
            return not (addr.is_multicast or addr.is_unspecified or addr.is_loopback) and any(
                addr in ipaddress.ip_network(net) for net in self.networks)
        except ValueError:
            return False


def networks_from_json(rows):
    result = []
    for row in rows:
        if 'LOOPBACK' in row.get('flags', []) or 'UP' not in row.get('flags', []):
            continue
        if row.get('operstate') not in ('UP', 'UNKNOWN'):
            continue
        addresses = []
        for item in row.get('addr_info', []):
            if item.get('family') not in ('inet', 'inet6') or item.get('tentative') or item.get('dadfailed'):
                continue
            try:
                addr = ipaddress.ip_interface(f"{item['local']}/{item['prefixlen']}")
                if not addr.ip.is_loopback and not addr.ip.is_unspecified:
                    addresses.append(str(addr))
            except (KeyError, ValueError):
                continue
        if addresses:
            interface = row['ifname']
            virtual = bool(row.get('linkinfo', {}).get('info_kind')) or not (Path('/sys/class/net') / interface / 'device').exists()
            result.append(Network(interface, tuple(addresses), valid_mac(row.get('address')), virtual))
    return result


def network_options(networks):
    """One choice per IPv4 subnet; retain all local address metadata internally."""
    options = []
    for network in networks:
        prefixes = [p for p in network.networks if ':' not in p]
        if not prefixes:
            continue
        options.extend(replace(network, selected_ipv4=p) for p in prefixes) if len(prefixes) > 1 else options.append(network)
    return options


def network_label(network, no_ipv4=''):
    return next((p for p in network.networks if ':' not in p), no_ipv4)


def valid_hostname(name):
    name = name.rstrip('.')
    if not name or len(name) > 253 or any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,62}', part) for part in name.split('.')):
        return ''
    try:
        ipaddress.ip_address(name)
        return ''
    except ValueError:
        return name


def resolve_hostname(address, interface, cancel, with_source=False):
    """NSS includes hosts/DNS/mDNS as configured; optional Avahi adds an mDNS fallback."""
    ip = ipaddress.ip_address(address.split('%')[0])
    scoped = address + '%' + interface if ip.version == 6 and ip.is_link_local and '%' not in address else address
    attempts = [['getent', 'hosts', scoped]]
    if shutil.which('avahi-resolve-address'):
        attempts.append(['avahi-resolve-address', '-6' if ip.version == 6 else '-4', scoped])
    for args in attempts:
        try:
            output = command(args, cancel, timeout=2, allowed=(0, 1, 2))
        except DiscoveryError:
            continue
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                if ipaddress.ip_address(parts[0].split('%')[0]) != ip:
                    continue
            except ValueError:
                continue
            name = valid_hostname(parts[1])
            if name:
                return (name, 'nss' if args[0]=='getent' else 'mdns') if with_source else name
    return ('', 'unknown') if with_source else ''


def discover_networks(cancel=None):
    return networks_from_json(json.loads(command(['ip', '-j', '-d', 'address', 'show'], cancel)))


def neighbors(network, cancel):
    rows = json.loads(command(['ip', '-j', 'neighbor', 'show', 'dev', network.interface], cancel))
    result = []
    for row in rows:
        mac = valid_mac(row.get('lladdr'))
        states = row.get('state', [])
        if isinstance(states, str):
            states = [states]
        if not mac or set(states) & {'FAILED', 'INCOMPLETE', 'NOARP'}:
            continue
        address = row.get('dst', '')
        if network.contains(address):
            result.append({'mac': mac, 'ip': address, 'interface': network.interface,
                           'hostname': '', 'evidence': ','.join(states),
                           'source': 'cache', 'observed_at': now()})
    return result


def probe(network, address, cancel):
    # Check the actual route as well as the configured CIDR: never follow a gateway.
    route = json.loads(command(['ip', '-j', 'route', 'get', address, 'oif', network.interface], cancel))
    if not route or route[0].get('gateway') or route[0].get('dev') != network.interface:
        return
    command(['ping', '-n', '-c', '1', '-W', '1', '-t', '1', '-I', network.interface, address],
            cancel, timeout=2, allowed=(0, 1))


def scan(network, cancel, progress=lambda *_: None, active=True, max_hosts=4096):
    current = discover_networks(cancel)
    if replace(network, selected_ipv4="") not in current:
        raise DiscoveryError('network_changed')
    warnings = []
    cached = neighbors(network, cancel)
    own = {str(ipaddress.ip_interface(a).ip) for a in network.addresses if network.contains(str(ipaddress.ip_interface(a).ip))}
    targets = {r['ip'] for r in cached} if active else set()
    if active and shutil.which('ping'):
        count = 0
        for prefix in network.networks:
            net = ipaddress.ip_network(prefix)
            if net.version == 4:
                hosts = net.num_addresses - (2 if net.prefixlen < 31 else 0)
                if hosts + count <= max_hosts:
                    targets.update(str(a) for a in net.hosts())
                    count += hosts
                else:
                    warnings.append('large_network')
        targets -= own
        progress('probing', len(targets))
        with ThreadPoolExecutor(max_workers=24) as pool:
            pending = {pool.submit(probe, network, target, cancel): target for target in targets}
            done = 0
            for future in as_completed(pending):
                try:
                    future.result()
                except DiscoveryError:
                    warnings.append('probe_failed')
                done += 1
                progress('progress', (done, len(targets)))
                if cancel.is_set():
                    for task in pending:
                        task.cancel()
                    raise Cancelled()
    elif active:
        warnings.append('no_ping')
    # IPv6 address spaces cannot be enumerated. Only observed local neighbors are used.
    warnings.append('ipv6_observed')
    observations = neighbors(network, cancel)
    if network.mac:
        observations.extend({'mac': network.mac, 'ip': ip, 'interface': network.interface,
                             'hostname': '', 'evidence': 'local'} for ip in own)
    cached_keys={(r['ip'],r['mac']) for r in cached}
    stamp=now()
    for obs in observations:
        obs['source']='local' if obs['evidence']=='local' else ('cache' if (obs['ip'],obs['mac']) in cached_keys else 'scan_neighbor')
        obs['observed_at']=stamp
    names = {}
    def resolve(address):
        if address in own:
            return address, (valid_hostname(socket.gethostname()), 'local')
        return address, resolve_hostname(address, network.interface, cancel, with_source=True)
    progress('resolving', len(observations))
    with ThreadPoolExecutor(max_workers=8) as pool:
        for address, name in pool.map(resolve, sorted({r['ip'] for r in observations})):
            names[address] = name
    if cancel.is_set():
        raise Cancelled()
    for obs in observations:
        obs['hostname'],obs['name_source'] = names.get(obs['ip'], ('', 'unknown'))
    if replace(network, selected_ipv4="") not in discover_networks(cancel):
        raise DiscoveryError('network_changed')
    return observations, sorted(set(warnings))


def recognition_scope(scope):
    """IPv4 LAN identity does not depend on additional/renumbered IPv6 prefixes.

    Preserve interface and actual IPv4 prefixes. IPv6-only scopes remain exact;
    dropping their prefix would incorrectly join unrelated networks.
    """
    parts = scope.split('|')
    prefixes = []
    for prefix in parts[1:]:
        try:
            network = ipaddress.ip_network(prefix)
        except ValueError:
            return scope
        if network.version == 4:
            prefixes.append(str(network))
    return parts[0] + '|' + '|'.join(sorted(set(prefixes))) if prefixes else scope


class Store:
    """Observations stay scoped; identities can be explicitly linked by the user.

    MAC matching uses the global stored MAC identity; network views stay scoped.
    Changed MACs/IP-only matches are not silently merged. All address history is kept.
    """
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS devices (
          id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS device_names (
          device TEXT NOT NULL REFERENCES devices(id), name TEXT NOT NULL,
          PRIMARY KEY(device,name));
        CREATE TABLE IF NOT EXISTS scans (
          id TEXT PRIMARY KEY, scope TEXT NOT NULL, time TEXT NOT NULL, warnings TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations (
          device TEXT NOT NULL REFERENCES devices(id), scope TEXT NOT NULL, mac TEXT NOT NULL,
          ip TEXT NOT NULL, interface TEXT NOT NULL, hostname TEXT NOT NULL, evidence TEXT NOT NULL,
          first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, scan TEXT NOT NULL, first_scan TEXT NOT NULL,
          PRIMARY KEY(scope, mac, ip, interface));
        CREATE TABLE IF NOT EXISTS scan_snapshots (scan TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS observation_device ON observations(device);
        ''')
        columns={row['name'] for row in self.db.execute('PRAGMA table_info(observations)')}
        for column in ('source','observed_at','name_source'):
            if column not in columns:
                self.db.execute(f"ALTER TABLE observations ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        # Fill legacy unnamed devices from their most recent usable hostname.
        with self.db:
            for row in self.db.execute('SELECT id,name FROM devices').fetchall():
                if self._unknown_name(row['name']):
                    for obs in self.db.execute('SELECT hostname FROM observations WHERE device=? ORDER BY last_seen DESC,ip', (row['id'],)):
                        if self._adopt_hostname(row['id'], obs['hostname']):
                            break

    @staticmethod
    def _unknown_name(name):
        return name.strip().casefold() in ('', 'unbekannt', 'unknown')

    def _adopt_hostname(self, device, hostname):
        hostname = valid_hostname(hostname.strip())
        if not hostname or self._unknown_name(hostname):
            return False
        row = self.db.execute('SELECT name FROM devices WHERE id=?', (device,)).fetchone()
        if row and self._unknown_name(row['name']):
            self.db.execute('UPDATE devices SET name=? WHERE id=?', (hostname[:200], device))
            return True
        return False

    def close(self):
        self.db.close()

    def compatible_scopes(self, scope):
        # Read old scopes as-is: no destructive schema/data migration required.
        key = recognition_scope(scope)
        existing = [r[0] for r in self.db.execute('SELECT DISTINCT scope FROM scans')]
        return sorted({scope, *(s for s in existing if recognition_scope(s) == key)})

    def commit_scan(self, network, observations, warnings=()):
        stamp, scan_id = now(), uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO scans VALUES(?,?,?,?)', (scan_id, network.scope, stamp, json.dumps(warnings)))
            for obs in observations:
                mac = valid_mac(obs.get('mac'))
                if not mac or not network.contains(obs['ip']) or obs['interface'] != network.interface:
                    continue
                matches = self.db.execute(
                    "SELECT DISTINCT device FROM observations WHERE lower(replace(trim(mac),'-',':'))=? "
                    'ORDER BY first_seen, device', (mac,)).fetchall()
                old = matches[0] if matches else None
                device = old['device'] if old else uuid.uuid4().hex
                # Repair duplicate identities created by earlier interface-scoped scans.
                for match in matches[1:]:
                    self._merge(device, match['device'])
                if not old:
                    self.db.execute('INSERT INTO devices VALUES(?,?,?,?)', (device, '', stamp, stamp))
                self.db.execute('UPDATE devices SET last_seen=? WHERE id=?', (stamp, device))
                self._adopt_hostname(device, obs.get('hostname', ''))
                self.db.execute('''INSERT INTO observations (device,scope,mac,ip,interface,hostname,evidence,first_seen,last_seen,scan,first_scan,source,observed_at,name_source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(scope,mac,ip,interface) DO UPDATE SET
                  hostname=excluded.hostname,evidence=excluded.evidence,last_seen=excluded.last_seen,scan=excluded.scan,source=excluded.source,observed_at=excluded.observed_at,name_source=excluded.name_source''',
                  (device, network.scope, mac, obs['ip'], obs['interface'], obs.get('hostname', ''),
                   obs.get('evidence', ''), stamp, stamp, scan_id, scan_id, obs.get('source','unknown'),obs.get('observed_at',stamp),obs.get('name_source','unknown')))
            snapshot=[dict(r) for r in self.db.execute('SELECT * FROM observations WHERE scan=?',(scan_id,))]
            self.db.execute('INSERT INTO scan_snapshots VALUES(?,?)',(scan_id,json.dumps(snapshot)))
        return scan_id

    def devices(self, scope):
        scopes = self.compatible_scopes(scope)
        placeholders = ','.join('?' for _ in scopes)
        latest = self.db.execute(f'SELECT id,time FROM scans WHERE scope IN ({placeholders}) ORDER BY rowid DESC LIMIT 1', scopes).fetchone()
        if not latest:
            return []
        scans=[dict(r) for r in self.db.execute(f'SELECT id,time FROM scans WHERE scope IN ({placeholders}) ORDER BY rowid DESC',scopes)]
        previous_id=scans[1]['id'] if len(scans)>1 else None
        saved=self.db.execute('SELECT data FROM scan_snapshots WHERE scan=?',(previous_id,)).fetchone()
        previous_by_mac={}
        previous_by_ip={}
        if saved:
            for obs in json.loads(saved['data']):
                previous_by_mac.setdefault(obs['mac'],[]).append(obs)
                previous_by_ip.setdefault((obs['ip'],obs['interface']),set()).add(obs['mac'])
        current_by_ip={}
        for obs in self.db.execute(f'SELECT ip,mac,interface FROM observations WHERE scan=? AND scope IN ({placeholders})', [latest['id'],*scopes]):
            current_by_ip.setdefault((obs['ip'],obs['interface']),set()).add(obs['mac'])
        result = []
        for row in self.db.execute(f'SELECT DISTINCT d.* FROM devices d JOIN observations o ON o.device=d.id WHERE o.scope IN ({placeholders}) ORDER BY d.first_seen,d.id', scopes):
            device = dict(row)
            device['other_names'] = [r[0] for r in self.db.execute('SELECT name FROM device_names WHERE device=? ORDER BY name', (row['id'],))]
            history = [dict(r) for r in self.db.execute('SELECT * FROM observations WHERE device=? ORDER BY last_seen DESC,ip', (row['id'],))]
            scoped = [o for o in history if o['scope'] in scopes]
            current = [o for o in scoped if o['scan'] == latest['id']]
            device['status'] = 'missing' if not current else ('new' if all(o['first_scan'] == latest['id'] for o in history) else 'known')
            shown = current or scoped
            for key in ('mac', 'hostname', 'interface'):
                device[key] = sorted({o[key] for o in shown if o[key]})
            device['ipv4'] = sorted({o['ip'] for o in shown if ':' not in o['ip']})
            device['ipv6'] = sorted({o['ip'] for o in shown if ':' in o['ip']})
            device['is_local'] = any(o['evidence'] == 'local' for o in shown)
            device['history'] = history
            device['private_mac'] = any(int(m[:2], 16) & 2 for m in device['mac'])
            previous=[o for mac in {h['mac'] for h in history} for o in previous_by_mac.get(mac,[])] if saved else [o for o in scoped if o['scan']==previous_id]
            fields=('ip','mac','hostname')
            device['changes']={k:{'before':sorted({o[k] for o in previous if o[k]}),
                                  'after':sorted({o[k] for o in current if o[k]})}
                               for k in fields if current and previous and {o[k] for o in previous}!={o[k] for o in current}}
            device['assignment_changes']=[]
            for ip,interface in sorted({(o['ip'],o['interface']) for o in shown}):
                before=previous_by_ip.get((ip,interface),set());after=current_by_ip.get((ip,interface),set())
                if before and after and before!=after:
                    device['assignment_changes'].append(dict(ip=ip,interface=interface,before=sorted(before),after=sorted(after),time=latest['time']))
            device['changed']=bool(device['changes'] or device['assignment_changes'])
            device['missing_scans']=0
            for scan_row in scans:
                if scan_row['time'] <= max(o['last_seen'] for o in scoped):break
                device['missing_scans']+=1
            device['conflicts']=[dict(ip=o['ip'],interface=o['interface'],macs=sorted(current_by_ip[(o['ip'],o['interface'])]),time=latest['time'])
                for o in current if len(current_by_ip.get((o['ip'],o['interface']),()))>1]
            device['observations']=shown

            result.append(device)
        return result

    def rename(self, device, name):
        with self.db:
            self.db.execute('UPDATE devices SET name=? WHERE id=?', (name.strip()[:200], device))

    def merge(self, keep, other):
        if keep == other:
            return
        with self.db:
            self._merge(keep, other)

    def _merge(self, keep, other):
        rows = self.db.execute('SELECT * FROM devices WHERE id IN (?,?)', (keep, other)).fetchall()
        if len(rows) != 2:
            raise ValueError('device_missing')
        main = next(r for r in rows if r['id'] == keep)
        secondary = next(r for r in rows if r['id'] == other)
        chosen_name = secondary['name'] if self._unknown_name(main['name']) else main['name']
        names = {r['name'] for r in rows if r['name']}
        names.update(r[0] for r in self.db.execute('SELECT name FROM device_names WHERE device IN (?,?)', (keep, other)))
        self.db.execute('DELETE FROM device_names WHERE device IN (?,?)', (keep, other))
        self.db.executemany('INSERT OR IGNORE INTO device_names VALUES(?,?)', [(keep, name) for name in names if name != chosen_name])
        self.db.execute('UPDATE devices SET name=? WHERE id=?', (chosen_name, keep))
        self.db.execute('UPDATE observations SET device=? WHERE device=?', (keep, other))
        self.db.execute('UPDATE devices SET first_seen=?,last_seen=? WHERE id=?',
                        (min(r['first_seen'] for r in rows), max(r['last_seen'] for r in rows), keep))
        self.db.execute('DELETE FROM devices WHERE id=?', (other,))


OUI_URLS = {'oui': 'https://standards-oui.ieee.org/oui/oui.csv',
            'mam': 'https://standards-oui.ieee.org/oui28/mam.csv',
            'oui36': 'https://standards-oui.ieee.org/oui36/oui36.csv',
            'iab': 'https://standards-oui.ieee.org/iab/iab.csv'}


class VendorUpdateError(Exception):
    def __init__(self, code, status=None):
        super().__init__(code)
        self.code, self.status = code, status


class Vendors:
    def __init__(self, data=None):
        self.data = data or {'date': '', 'prefixes': {}}

    @classmethod
    def parse(cls, sources, date):
        prefixes = {}
        for text in sources:
            reader = csv.DictReader(io.StringIO(text))
            if not {'Assignment', 'Organization Name'} <= set(reader.fieldnames or []):
                raise ValueError('invalid_oui')
            for row in reader:
                prefix = row['Assignment'].strip().upper()
                if re.fullmatch(r'[0-9A-F]{6}|[0-9A-F]{7}|[0-9A-F]{9}', prefix):
                    prefixes[prefix] = row['Organization Name'].strip()
        if not prefixes:
            raise ValueError('empty_oui')
        return cls({'date': date, 'source': OUI_URLS, 'prefixes': prefixes})

    @classmethod
    def load(cls, custom):
        if custom is not None and custom.exists():
            data = json.loads(custom.read_text())
            if not isinstance(data, dict):
                raise ValueError('invalid_oui')
            prefixes, date = data.get('prefixes'), data.get('date')
            if not isinstance(prefixes, dict) or not isinstance(date, str):
                raise ValueError('invalid_oui')
            if date:
                dates = date.removesuffix(' (ieee-data)').split(' – ')
                try:
                    if len(dates) not in (1, 2):
                        raise ValueError('invalid_oui')
                    for value in dates:
                        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                            raise ValueError('invalid_oui')
                        datetime.strptime(value, '%Y-%m-%d')
                except ValueError as exc:
                    raise ValueError('invalid_oui') from exc
            if any(not isinstance(prefix, str) or
                   not re.fullmatch(r'[0-9A-F]{6}|[0-9A-F]{7}|[0-9A-F]{9}', prefix) or
                   not isinstance(vendor, str) or not vendor.strip()
                   for prefix, vendor in prefixes.items()):
                raise ValueError('invalid_oui')
            return cls(data)
        sources = list((ROOT / 'vendor').glob('*.csv'))
        if not sources:
            return cls()
        metadata = ROOT / 'vendor/metadata.json'
        details = json.loads(metadata.read_text()) if metadata.exists() else {}
        instance = cls.parse([p.read_text(encoding='utf-8-sig') for p in sources],
                             details.get('date', '2022-08-27 (ieee-data)'))
        if details:
            instance.data.update(fetched_at=details.get('fetched_at', ''),
                                 source_dates={name: parsedate_to_datetime(value['last_modified']).isoformat()
                                               for name, value in details['sources'].items()})
        return instance

    def lookup(self, mac):
        mac = valid_mac(mac)
        if not mac or int(mac[:2], 16) & 2:
            return ''
        raw = mac.replace(':', '').upper()
        for length in (9, 7, 6):
            if raw[:length] in self.data['prefixes']:
                return self.data['prefixes'][raw[:length]]
        return ''

    @classmethod
    def update(cls, destination, cancel):
        sources, source_dates = [], {}
        try:
            for name, url in OUI_URLS.items():
                if cancel.is_set():
                    raise Cancelled()
                request = Request(url, headers={
                    'User-Agent': f'showipmac/{VERSION} (local OUI database update)',
                    'Accept': 'text/csv, text/plain;q=0.9'})
                with urlopen(request, timeout=8) as response:
                    content = response.read(16_000_001)
                    if len(content) > 16_000_000:
                        raise ValueError('oui_too_large')
                    source = content.decode('utf-8-sig')
                    # Validate each individual list before accepting the whole update.
                    cls.parse([source], '')
                    sources.append(source)
                    modified = getattr(response, 'headers', {}).get('Last-Modified')
                    if modified:
                        try:
                            source_dates[name] = parsedate_to_datetime(modified).isoformat()
                        except (ValueError, TypeError, OverflowError):
                            pass
            fetched = now()
            dates = sorted({value[:10] for value in source_dates.values()})
            date = (dates[0] if len(dates) == 1 else dates[0] + ' – ' + dates[-1]) if len(source_dates) == len(OUI_URLS) else ''
            instance = cls.parse(sources, date)
            instance.data.update(fetched_at=fetched, source_dates=source_dates)
            if cancel.is_set():
                raise Cancelled()
            atomic_json(destination, instance.data)
            return instance
        except HTTPError as exc:
            raise VendorUpdateError('vendor_http', exc.code) from exc
        except (URLError, TimeoutError) as exc:
            raise VendorUpdateError('vendor_network') from exc
        except (ValueError, OSError) as exc:
            raise VendorUpdateError('vendor_invalid') from exc


def atomic_json(path, data):
    """Atomic whole-file snapshots: the last completed replacement wins.

    Independent instances do not merge settings. Each owns its temporary file;
    readers see only complete snapshots, even with concurrent writers.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export(path, devices, translate, kind='csv'):
    keys = ['name', 'hostname', 'ipv4', 'ipv6', 'mac', 'vendor', 'status', 'first_seen', 'last_seen', 'interface']
    def value(device, key):
        item = device.get(key, '')
        if key == 'status':
            return translate(item)
        if key in ('first_seen', 'last_seen'):
            from presentation import local_time
            return local_time(item) or translate('unknown')
        if isinstance(item, list):
            item = '; '.join(item)
        return str(item) if item else translate('unknown')
    with path.open('w', encoding='utf-8-sig' if kind == 'csv' else 'utf-8', newline='') as handle:
        if kind == 'json':
            json.dump(devices, handle, ensure_ascii=False, indent=2)
        else:
            writer = csv.writer(handle)
            writer.writerow([translate(k) for k in keys])
            for device in devices:
                # Avoid spreadsheet formula execution in user names/hostnames.
                row = [value(device, k) for k in keys]
                writer.writerow(["'" + v if v.lstrip().startswith(('=', '+', '-', '@')) else v for v in row])


def network_details(network, cancel=None):
    """Read local route/DNS configuration; do not contact gateways or other LANs."""
    result={'routes':[], 'dns':'', 'dns_source':'unknown', 'errors':[]}
    for version in ('-4','-6'):
        try:
            rows=json.loads(command(['ip',version,'-j','route','show','table','all','dev',network.interface],cancel))
            result['routes'].extend(dict(family=version[1:],destination=r.get('dst','default'),gateway=r.get('gateway',''),table=r.get('table','main')) for r in rows)
        except (DiscoveryError,ValueError) as exc:result['errors'].append(str(exc))
    if shutil.which('resolvectl'):
        try:
            result['dns']=command(['resolvectl','status',network.interface],cancel,timeout=3)[:8000]
            result['dns_source']='resolvectl'
        except DiscoveryError as exc:result['errors'].append(str(exc))
    if not result['dns']:
        try:
            result['dns']=Path('/etc/resolv.conf').read_text()[:8000]
            result['dns_source']='resolv.conf'
        except OSError as exc:result['errors'].append(str(exc))
    return result
