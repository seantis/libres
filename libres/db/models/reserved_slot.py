import sedate

from datetime import timedelta
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


class ReservedSlot(TimestampMixin, ORMBase):
    """Describes a reserved slot within an allocated timespan."""

    __tablename__ = 'reserved_slots'

    resource = Column(
        UUID(),
        primary_key=True,
        nullable=False,
        autoincrement=False
    )

    start = Column(
        UTCDateTime(timezone=False),
        primary_key=True,
        nullable=False,
        autoincrement=False
    )

    end = Column(
        UTCDateTime(timezone=False),
        nullable=False
    )

    allocation_id = Column(
        types.Integer(),
        ForeignKey(Allocation.id),
        nullable=False
    )

    allocation = relationship(
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

    reservation_token = Column(
        UUID(),
        nullable=False
    )

    __table_args__ = (
        Index('reservation_resource_ix', 'reservation_token', 'resource'),
    )

    def display_start(self, timezone=None):
        start = rasterize_start(self.start, self.allocation.raster)
        return sedate.to_timezone(
            start, timezone or self.allocation.timezone
        )

    def display_end(self, timezone=None):
        end = rasterize_end(self.end, self.allocation.raster)
        end += timedelta(microseconds=1)

        return sedate.to_timezone(
            end, timezone or self.allocation.timezone
        )

    def __eq__(self, other):
        return self.start == other.start and \
            str(self.resource) == str(other.resource)

    def __hash__(self):
        return id(self)
