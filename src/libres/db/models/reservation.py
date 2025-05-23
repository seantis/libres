from __future__ import annotations

import sedate

from datetime import datetime, timedelta

from sqlalchemy import types
from sqlalchemy.orm import object_session, deferred
from sqlalchemy.schema import Column
from sqlalchemy.schema import Index

from libres.db.models import ORMBase
from libres.db.models.types import UUID, UTCDateTime, JSON
from libres.db.models.other import OtherModels
from libres.db.models.timestamp import TimestampMixin


from typing import Any
from typing import Literal
from typing import NamedTuple
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import uuid
    from sedate.types import TzInfoOrName
    from sqlalchemy.orm import Query

    from libres.db.models import Allocation


class Timespan(NamedTuple):
    start: datetime
    end: datetime


class Reservation(TimestampMixin, ORMBase, OtherModels):
    """Describes a pending or approved reservation.

    """

    __tablename__ = 'reservations'

    id: Column[int] = Column(
        types.Integer(),
        primary_key=True,
        autoincrement=True
    )

    token: Column[uuid.UUID] = Column(
        UUID(),
        nullable=False,
    )

    target: Column[uuid.UUID] = Column(
        UUID(),
        nullable=False,
    )

    target_type: Column[Literal['group', 'allocation']] = Column(
        types.Enum(  # type:ignore[arg-type]
            'group', 'allocation',
            name='reservation_target_type'
        ),
        nullable=False
    )

    type: Column[str | None] = Column(
        types.Text(),
        nullable=True
    )

    resource: Column[uuid.UUID] = Column(
        UUID(),
        nullable=False
    )

    start: Column[datetime | None] = Column(
        UTCDateTime(timezone=False),
        nullable=True
    )

    end: Column[datetime | None] = Column(
        UTCDateTime(timezone=False),
        nullable=True
    )

    timezone: Column[str | None] = Column(
        types.String(),
        nullable=True
    )

    status: Column[Literal['pending', 'approved']] = Column(
        types.Enum(  # type:ignore[arg-type]
            'pending', 'approved',
            name='reservation_status'
        ),
        nullable=False
    )

    data: Column[dict[str, Any] | None] = deferred(
        Column(
            JSON(),
            nullable=True
        )
    )

    email: Column[str] = Column(
        types.Unicode(254),
        nullable=False
    )

    session_id: Column[uuid.UUID | None] = Column(
        UUID()
    )

    quota: Column[int] = Column(
        types.Integer(),
        nullable=False
    )

    __table_args__ = (
        Index('target_status_ix', 'status', 'target', 'id'),
    )

    __mapper_args__ = {
        'polymorphic_identity': None,
        'polymorphic_on': type
    }

    def _target_allocations(self) -> Query[Allocation]:
        """ Returns the allocations this reservation is targeting. This should
        NOT be confused with db.allocations_by_reservation. The method in
        the db module returns the actual allocations belonging to an approved
        reservation.

        This method only returns the master allocations to get information
        about timespans and other properties. If you don't know exactly
        what you're doing you do not want to use this method as misuse might
        be dangerous.

        """
        Allocation = self.models.Allocation  # noqa: N806
        query = object_session(self).query(Allocation)
        query = query.filter(Allocation.group == self.target)

        # master allocations only
        query = query.filter(Allocation.resource == Allocation.mirror_of)

        # order by date
        query = query.order_by(Allocation._start)

        return query  # type: ignore[no-any-return]

    def display_start(
        self,
        timezone: TzInfoOrName | None = None
    ) -> datetime:
        """Does nothing but to form a nice pair to display_end."""
        assert self.start is not None
        if timezone is None:
            assert self.timezone is not None
            timezone = self.timezone
        return sedate.to_timezone(self.start, timezone)

    def display_end(
        self,
        timezone: TzInfoOrName | None = None
    ) -> datetime:
        """Returns the end plus one microsecond (nicer display)."""
        assert self.end is not None
        if timezone is None:
            assert self.timezone is not None
            timezone = self.timezone

        end = self.end + timedelta(microseconds=1)
        return sedate.to_timezone(end, timezone)

    def timespans(self) -> list[Timespan]:
        """ Returns the timespans targeted by this reservation.

        The result is a list of :class:`~libres.db.models.reservation.Timespan`
        timespans. The start and end are the start and end dates of the
        referenced allocations.

        The timespans are ordered by start.

        """

        if self.target_type == 'allocation':
            # we don't need to hit the database in this case
            assert self.start is not None
            assert self.end is not None
            return [
                Timespan(self.start, self.end + timedelta(microseconds=1))
            ]
        elif self.target_type == 'group':
            return [
                Timespan(allocation.start, allocation.end)
                for allocation in self._target_allocations()
            ]
        else:
            raise NotImplementedError

    @property
    def title(self) -> str:
        return self.email

    @property
    def autoapprovable(self) -> bool:
        query = self._target_allocations()
        query = query.filter(self.models.Allocation.approve_manually == True)

        # A reservation is deemed autoapprovable if no allocation
        # requires explicit approval

        return object_session(self).query(~query.exists()).scalar()  # type: ignore[no-any-return]
