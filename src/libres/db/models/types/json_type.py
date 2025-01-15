from __future__ import annotations

from json import loads, dumps
from sqlalchemy.types import TypeDecorator, TEXT


from typing import Any
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

    _Base = TypeDecorator[Any]
else:
    _Base = TypeDecorator


class JSON(_Base):
    """Like the default JSON, but using the json serializer from the dialect
    (postgres) each time the value is read, even if it never left the ORM. The
    default json type will only do it when the record is read from the
    database.

    """

    # FIXME: We should switch to JSONB now, but we will need to
    #        add a database migration to OneGov at the same time
    impl = TEXT

    def process_bind_param(
        self,
        value: Any,
        dialect: Dialect
    ) -> str | None:

        if value is not None:
            value = (dialect._json_serializer or dumps)(value)  # type:ignore

        return value  # type: ignore[no-any-return]

    def process_result_value(
        self,
        value: str | None,
        dialect: Dialect
    ) -> Any | None:

        if value is not None:
            value = (dialect._json_deserializer or loads)(value)  # type:ignore

        return value
