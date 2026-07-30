from __future__ import annotations

from libres.context.registry import create_default_registry
from libres.db import new_scheduler

registry = create_default_registry()  # ruff: ignore[non-empty-init-module]

__version__ = '1.1.2'
__all__ = (
    'new_scheduler',
    'registry'
)
