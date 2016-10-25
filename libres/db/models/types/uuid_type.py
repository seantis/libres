import uuid

from libres.modules.compat import string_types

from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects import postgresql


class SoftUUID(uuid.UUID):
    """ Behaves just like the UUID class, but allows strings to be compared
    with it, so that SoftUUID('my-uuid') == 'my-uuid' equals True.

    """

    def __eq__(self, other):

        if isinstance(other, string_types):
            return self.hex == other.replace('-', '').strip()

        if isinstance(other, uuid.UUID):
            return self.__dict__ == other.__dict__

        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        # this function is not inherited in python 2
        return hash(self.int)


class UUID(TypeDecorator):
    """ Same as the Postgres UUID type, but returning SoftUUIDs instead
    of UUIDs on bind.

    """
    impl = postgresql.UUID

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)

    def process_result_value(self, value, dialect):
        if value is not None:
            # Postgres always returns the uuid in the same format, so we
            # can turn it into an int immediately, avoiding some checks
            # and extra code run by UUID
            return SoftUUID(int=int(value.replace('-', ''), 16))
