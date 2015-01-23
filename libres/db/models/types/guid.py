import uuid

from libres.modules.compat import string_types

from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID


class StringEqualUUID(uuid.UUID):
    """ Behaves just like the UUID class, but allows strings to be compared
    with it, so that UUID('my-uuid') == 'my-uuid' equals True.

    """

    def __eq__(self, other):

        if isinstance(other, string_types):
            return self.hex == other.replace('-', '').strip()

        if isinstance(other, uuid.UUID):
            return self.__dict__ == other.__dict__

        return False

    def __ne__(self, other):
        return not self.__eq__(other)


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgresql's UUID type, otherwise uses
    CHAR(32), storing as stringified hex values.

    """
    impl = CHAR

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID())
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, StringEqualUUID):
                return "%.32x" % StringEqualUUID(value)
            else:
                # hexstring
                return "%.32x" % value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            return StringEqualUUID(value)
