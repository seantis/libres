from __future__ import annotations

from libres.context.registry import create_default_registry
from libres.db import new_scheduler

registry = create_default_registry()

__version__ = '0.9.0'
__all__ = (
    'new_scheduler',
    'registry'
)
