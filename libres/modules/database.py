from libres import registry
from libres.models import ORMBase
from libres.services.db.session import serialized
from libres.modules.utils import context_specific


class Database(object):

    def __init__(self, context):
        self.context = context

    @property
    @context_specific
    def session(self):
        return registry.get_service('session').session()

    @context_specific
    @serialized
    def setup(self):
        ORMBase.metadata.create_all(self.session.bind)
        self.session.commit()
