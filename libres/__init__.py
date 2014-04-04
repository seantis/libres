from libres.context import setup_registry
registry = setup_registry()

from libres.db import new_scheduler
__all__ = ['new_scheduler', 'registry']
