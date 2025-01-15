from __future__ import annotations

import sedate

from datetime import datetime, timedelta
from sqlalchemy import types
from sqlalchemy.schema import Column
from sqlalchemy.schema import Index
from sqlalchemy.schema import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import backref

from libres.modules.rasterizer import (
    rasterize_start,
    rasterize_end,
)

from libres.db.models import ORMBase, Allocation
from libres.db.models.types import UUID, UTCDateTime
from libres.db.models.timestamp import TimestampMixin


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import uuid
    from sedate.types import TzInfoOrName


class ReservedSlot(TimestampMixin, ORMBase):
    """Describes a reserved slot within an allocated timespan."""

    __tablename__ = 'reserved_slots'

    resource: Column[uuid.UUID] = Column(
        UUID(),
        primary_key=True,
        nullable=False,
        autoincrement=False
    )

    start: Column[datetime] = Column(
        UTCDateTime(timezone=False),
        primary_key=True,
        nullable=False,
        autoincrement=False
    )

    end: Column[datetime] = Column(
        UTCDateTime(timezone=False),
        nullable=False
    )

    allocation_id: Column[int] = Column(
        types.Integer(),
        ForeignKey(Allocation.id),
        nullable=False
    )

    allocation: relationship[Allocation] = relationship(
        Allocation,
        primaryjoin=Allocation.id == allocation_id,

        # Reserved_slots are eagerly joined since we usually want both
        # allocation and reserved_slots. There's barely a function which does
        # not need to know about reserved slots when working with allocation.
        backref=backref(
            'reserved_slots',
            lazy='joined',
            cascade='all, delete-orphan'
        )
    )

    reservation_token: Column[uuid.UUID] = Column(
        UUID(),
        nullable=False
    )

    __table_args__ = (
        Index('reservation_resource_ix', 'reservation_token', 'resource'),
    )

    def display_start(
        self,
        timezone: TzInfoOrName | None = None
    ) -> datetime:

        if timezone is None:
            assert self.allocation.timezone is not None
            timezone = self.allocation.timezone

        start = rasterize_start(self.start, self.allocation.raster)
        return sedate.to_timezone(start, timezone)

    def display_end(
        self,
        timezone: TzInfoOrName | None = None
    ) -> datetime:

        if timezone is None:
            assert self.allocation.timezone is not None
            timezone = self.allocation.timezone

        end = rasterize_end(self.end, self.allocation.raster)
        end += timedelta(microseconds=1)
        return sedate.to_timezone(end, timezone)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ReservedSlot):
            return False

        return (
            self.start == other.start and
            str(self.resource) == str(other.resource)
        )

    def __hash__(self) -> int:
        return id(self)
