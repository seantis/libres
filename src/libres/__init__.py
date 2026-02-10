from __future__ import annotations

from libres.context.registry import create_default_registry
from libres.db import new_scheduler

registry = create_default_registry()  # noqa: RUF067

__version__ = '1.0.0'
__all__ = (
    'new_scheduler',
    'registry'
)
