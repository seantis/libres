from json import loads, dumps
from sqlalchemy.types import TypeDecorator, TEXT


import typing as _t
if _t.TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

    _Base = TypeDecorator[_t.Any]
else:
    _Base = TypeDecorator


class JSON(_Base):
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

    def process_bind_param(
        self,
        value: _t.Any,
        dialect: 'Dialect'
    ) -> _t.Optional[str]:

        if value is not None:
            value = (dialect._json_serializer or dumps)(value)  # type:ignore

        return value

    def process_result_value(
        self,
        value: _t.Optional[str],
        dialect: 'Dialect'
    ) -> _t.Optional[_t.Any]:

        if value is not None:
            value = (dialect._json_deserializer or loads)(value)  # type:ignore

        return value
