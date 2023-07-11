import sedate

from libres.db.models.types import UTCDateTime
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import deferred
from sqlalchemy.schema import Column


import typing as _t
if _t.TYPE_CHECKING:
    from datetime import datetime


class TimestampMixin:
    """ Mixin providing created/modified timestamps for all records. Pretty
    much relies on the database being Postgresql but could be made to work
    with others.

    The columns are deferred loaded as this is primarily for logging and future
    forensics.

    """

    @staticmethod
    def timestamp() -> 'datetime':
        return sedate.utcnow()

    if _t.TYPE_CHECKING:
        created: Column[datetime]
        modified: Column[_t.Optional[datetime]]

    else:
        @declared_attr
        def created(cls) -> 'Column[datetime]':
            return deferred(
                Column(
                    UTCDateTime(timezone=False),
                    default=cls.timestamp
                )
            )

        @declared_attr
        def modified(cls) -> 'Column[_t.Optional[datetime]]':
            return deferred(
                Column(
                    UTCDateTime(timezone=False),
                    onupdate=cls.timestamp
                )
            )
