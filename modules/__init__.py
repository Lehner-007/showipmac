"""Gemeinsame Bausteine aus Josefs GTK-Grundvorlage."""

# Lokale, geprüfte Bibliothekskopie; kein Zugriff auf den Entwicklungsordner.
import sys as _basis_sys
from pathlib import Path as _BasisPath
_basis_vendor = str(_BasisPath(__file__).resolve().parent / '_vendor')
if _basis_vendor not in _basis_sys.path:
    _basis_sys.path.insert(0, _basis_vendor)
