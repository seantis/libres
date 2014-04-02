from libres.services import setup_registry
registry = setup_registry()

from libres.context_specific import new_hostess
__all__ = ['new_hostess', 'registry']
