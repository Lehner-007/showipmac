"""Adapter: existing showipmac data paths and central version remain authoritative."""
from core import ROOT, VERSION, now, VERSION_INFO_URL, LANGUAGE_SOURCE_URL
from datetime import datetime, timezone

PROGRAM_ID = 'showipmac'
PROJECT = dict(name='showipmac', image='assets/showipmac.png', settings=[
    dict(key='active', type='boolean', label='active'),
    dict(key='max_hosts', type='number', label='max_hosts_label', min=1, max=65536)])
PROJECT.update(update_url=VERSION_INFO_URL,source_url=LANGUAGE_SOURCE_URL,deb={'package':'showipmac'},tool_info=[
    dict(name='Python',kind='python',apt='python3'),
    dict(name='GTK',kind='gtk',apt='gir1.2-gtk-4.0'),
    dict(name='PyGObject',kind='module',module='gi',distribution='PyGObject',apt='python3-gi'),
    dict(name='requests',kind='module',module='requests',apt='python3-requests'),
    dict(name='Beautiful Soup',kind='module',module='bs4',distribution='beautifulsoup4',apt='python3-bs4'),
    dict(name='ip',kind='command',command='ip',version_args=['-Version'],apt='iproute2'),
    dict(name='ping',kind='command',command='ping',version_args=['-V'],apt='iputils-ping'),
    dict(name='avahi-resolve-address',kind='command',command='avahi-resolve-address',apt='avahi-utils',optional=True)])
_runtime = None


def bind_runtime(runtime):
    global _runtime
    _runtime = runtime


def config_dir():
    if _runtime is None:
        raise RuntimeError('Runtime has not been bound')
    return _runtime.path


def update_due(options):
    if not options['update_check'] or not options['update_url'].strip():
        return False
    try:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(options['last_update_check'])).total_seconds()
    except (ValueError, TypeError):
        return True
    return elapsed >= options['update_interval_value'] * {'days': 1, 'weeks': 7, 'months': 30}[options['update_interval_unit']] * 86400
