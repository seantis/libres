from json import loads, dumps
from sqlalchemy.types import TypeDecorator, TEXT


class JSON(TypeDecorator):
    """Like the default JSON, but using the json serializer from the dialect
    (postgres) each time the value is read, even if it never left the ORM. The
    default json type will only do it when the record is read from the
    database.

    """

    # Use TEXT for now to stay compatible with Postgres 9.1. In the future
    # this will be replaced by JSON (or JSONB) though that requires that we
    # require a later Postgres release. For now we stay backwards compatible
    # with a version that's still widely used (9.1).
    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = (dialect._json_serializer or dumps)(value)

        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = (dialect._json_deserializer or loads)(value)

        return value
