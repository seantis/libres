from __future__ import unicode_literals

from libres.context.registry import create_default_registry
from libres.db import new_scheduler

registry = create_default_registry()

__all__ = ['new_scheduler', 'registry']
