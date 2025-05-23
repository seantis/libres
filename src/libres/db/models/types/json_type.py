from __future__ import annotations

from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB


from typing import Any
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

    _Base = TypeDecorator[dict[str, Any]]
else:
    _Base = TypeDecorator


class JSON(_Base):
    """ A JSONB based type that coerces None's to empty dictionaries.

    That is, this JSONB column cannot be `'null'::jsonb`. It could
    still be `NULL` though, if it's nullable and never explicitly
    set. But on the Python end you should always see a dictionary.

    """

    impl = JSONB

    def process_bind_param(  # type:ignore[override]
        self,
        value: dict[str, Any] | None,
        dialect: Dialect
    ) -> dict[str, Any]:

        return {} if value is None else value

    def process_result_value(
        self,
        value: dict[str, Any] | None,
        dialect: Dialect
    ) -> dict[str, Any]:

        return {} if value is None else value


MutableDict.associate_with(JSON)  # type:ignore[no-untyped-call]
