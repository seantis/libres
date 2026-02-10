from __future__ import annotations

import sedate

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import types
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.schema import Index
from sqlalchemy.schema import ForeignKey

from libres.modules.rasterizer import (
    rasterize_start,
    rasterize_end,
)

from libres.db.models.allocation import Allocation
from libres.db.models.base import ORMBase
from libres.db.models.timestamp import TimestampMixin


from typing import Literal
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sedate.types import TzInfoOrName


class ReservedSlot(TimestampMixin, ORMBase):
    """Describes a reserved slot within an allocated timespan."""

    __tablename__ = 'reserved_slots'

    resource: Mapped[UUID] = mapped_column(
        primary_key=True,
        autoincrement=False
    )

    start: Mapped[datetime] = mapped_column(
        primary_key=True,
        autoincrement=False
    )

    end: Mapped[datetime]

    allocation_id: Mapped[int] = mapped_column(ForeignKey('allocations.id'))

    # Reserved_slots are eagerly joined since we usually want both
    # allocation and reserved_slots. There's barely a function which does
    # not need to know about reserved slots when working with allocations.
    allocation: Mapped[Allocation] = relationship(
        primaryjoin=Allocation.id == allocation_id,
        back_populates='reserved_slots',
    )

    source_type: Mapped[Literal['reservation', 'blocker']] = mapped_column(
        types.Enum(
            'reservation', 'blocker',
            name='reserved_slot_source_type'
        )
    )

    reservation_token: Mapped[UUID]

    __table_args__ = (
        Index('reservation_resource_ix', 'reservation_token', 'resource'),
    )

    def __init__(self) -> None:
        # NOTE: Avoid auto-generated __init__, the mypy plugin is
        #       deprecated and cannot be used with newer versions.
        pass

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
