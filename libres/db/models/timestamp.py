import sedate

from libres.db.models.types import UTCDateTime
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import deferred
from sqlalchemy.schema import Column


class TimestampMixin(object):
    """ Mixin providing created/modified timestamps for all records. Pretty
    much relies on the database being Postgresql but could be made to work
    with others.

    The columns are deferred loaded as this is primarily for logging and future
    forensics.

    """

    @staticmethod
    def timestamp():
        return sedate.utcnow()

    @declared_attr
    def created(cls):
        return deferred(
            Column(
                UTCDateTime(timezone=False),
                default=cls.timestamp
            )
        )

    @declared_attr
    def modified(cls):
        return deferred(
            Column(
                UTCDateTime(timezone=False),
                onupdate=cls.timestamp
            )
        )
