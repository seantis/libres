from libres import registry
from sqlalchemy.types import TypeDecorator, TEXT


class ContextAwareJSON(TypeDecorator):
    """Like the default JSON, but using libres.registry do determine the
    json.dumps/json.loads-like function to use.

    """

    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = registry.get_service('json_dumps')(value)

        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = registry.get_service('json_loads')(value)

        return value
