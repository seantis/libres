from libres.services import setup_registry
registry = setup_registry()

from libres.modules import new_hostess
hostess = new_hostess('master')
