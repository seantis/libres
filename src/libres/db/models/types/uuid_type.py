import uuid

from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects import postgresql


import typing as _t
if _t.TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

    _Base = TypeDecorator['SoftUUID']
else:
    _Base = TypeDecorator


class SoftUUID(uuid.UUID):
    """ Behaves just like the UUID class, but allows strings to be compared
    with it, so that SoftUUID('my-uuid') == 'my-uuid' equals True.

    """

    def __eq__(self, other: object) -> bool:

        if isinstance(other, str):
            return self.hex == other.replace('-', '').strip()

        if isinstance(other, uuid.UUID):
            return self.int == other.int

        return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.int)


class UUID(_Base):
    """ Same as the Postgres UUID type, but returning SoftUUIDs instead
    of UUIDs on bind.

    """
    impl = postgresql.UUID
    cache_ok = True

    def process_bind_param(
        self,
        value: _t.Optional[uuid.UUID],
        dialect: 'Dialect'
    ) -> _t.Optional[str]:

        if value is not None:
            return str(value)
        return None

    def process_result_value(
        self,
        value: _t.Optional[str],
        dialect: 'Dialect'
    ) -> _t.Optional[SoftUUID]:
        if value is not None:
            # Postgres always returns the uuid in the same format, so we
            # can turn it into an int immediately, avoiding some checks
            # and extra code run by UUID
            return SoftUUID(int=int(value.replace('-', ''), 16))
        return None
