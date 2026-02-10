from __future__ import annotations

import sedate

from datetime import datetime
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Mapped


class TimestampMixin:
    """ Mixin providing created/modified timestamps for all records. Pretty
    much relies on the database being Postgresql but could be made to work
    with others.

    The columns are deferred loaded as this is primarily for logging and future
    forensics.

    """

    @staticmethod
    def timestamp() -> datetime:
        return sedate.utcnow()

    created: Mapped[datetime] = mapped_column(
        default=timestamp,
        deferred=True
    )
    modified: Mapped[datetime | None] = mapped_column(
        onupdate=timestamp,
        deferred=True
    )
