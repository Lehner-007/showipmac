"""Pure formatting/sorting functions, independent of GTK. GPL-3.0-only."""
from datetime import datetime
import ipaddress


def local_time(value, language='de'):
    if not value:
        return ''
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            return ''
        return stamp.astimezone().strftime('%d.%m.%Y %H:%M:%S')
    except ValueError:
        return ''


def cell_value(device, key, text, language):
    value = device.get(key, '')
    if key == 'status':
        value = text(value)
        if device.get('conflicts'):value+=' · '+text('conflict_hint')
        if device.get('changed'):value+=' · '+text('changes_hint')
        if device.get('missing_scans'):value+=' · '+str(device['missing_scans'])+' '+text('missing_scans')
    elif key == 'last_seen':
        value = local_time(value, language)
    elif key == 'ipv6' and len(value) > 1:
        value = text('ipv6_count', count=len(value))
    if isinstance(value, list):
        value = '; '.join(value)
    if key == 'hostname' and device.get('is_local'):
        value = text('local_device') + ((' · ' + value) if value else '')
    return value or text('unknown')


def device_sort_key(device, column, text, language):
    if column in ('ipv4', 'ipv6'):
        values = tuple(sorted(int(ipaddress.ip_address(ip.split('%')[0])) for ip in device.get(column, [])))
        if column == 'ipv6':
            return (not values, len(values), values)
        return (not values, values)
    if column == 'last_seen':
        try:
            return (False, datetime.fromisoformat(device[column]).timestamp())
        except (ValueError, KeyError):
            return (True, 0)
    return (not bool(device.get(column)), cell_value(device, column, text, language).casefold())


def scan_summary(devices):
    return {'found': sum(d['status'] != 'missing' for d in devices),
            'new': sum(d['status'] == 'new' for d in devices),
            'known': sum(d['status'] == 'known' for d in devices)}


def display_date(value):
    """Format source dates, including ranges and legacy package labels."""
    import re
    def replace(match):
        try:
            return datetime.strptime(match.group(), '%Y-%m-%d').strftime('%d.%m.%Y')
        except ValueError:
            return match.group()
    return re.sub(r'\b\d{4}-\d{2}-\d{2}\b', replace, value)


def connection_labels(networks, text, sysroot=None):
    from pathlib import Path
    sysroot = Path(sysroot) if sysroot else Path('/sys/class/net')
    kinds = {}
    for net in networks:
        path = sysroot / net.interface
        if net.virtual:
            kind = 'virtual'
        elif (path / 'wireless').is_dir() or (path / 'phy80211').exists():
            kind = 'wlan'
        else:
            try:
                kind = 'lan' if (path / 'device').exists() and (path / 'type').read_text().strip() == '1' else ''
            except OSError:
                kind = ''
        kinds[net.interface] = kind
    lans = sorted(name for name, kind in kinds.items() if kind == 'lan')
    return {name: (text(kind) + (f' {lans.index(name)+1}' if kind == 'lan' and len(lans)>1 else '')) if kind else ''
            for name, kind in kinds.items()}


def selection_label(network, connection, no_ipv4):
    from core import network_label
    return network_label(network, no_ipv4) + ' — ' + ((connection + ' → ') if connection else '') + network.interface
