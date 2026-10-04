"""Adapter: existing showipmac data paths and central version remain authoritative."""
from core import ROOT, VERSION, now
from datetime import datetime, timezone

PROGRAM_ID = 'showipmac'
PROJECT = dict(name='showipmac', image='assets/showipmac.png', settings=[
    dict(key='active', type='boolean', label='active'),
    dict(key='max_hosts', type='number', label='max_hosts_label', min=1, max=65536)])
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
