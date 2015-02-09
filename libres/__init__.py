from __future__ import unicode_literals

from libres.context import setup_registry
from libres.db import new_scheduler

registry = setup_registry()

__all__ = ['new_scheduler', 'registry']
