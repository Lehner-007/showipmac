"""Kompatibler Import aus josef_basis 0.1.0."""
import sys
from josef_basis import menus as _shared
sys.modules[__name__] = _shared
