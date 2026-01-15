from __future__ import annotations

import sedate

from datetime import datetime, timedelta

from sqlalchemy import types
from sqlalchemy.orm import object_session
from sqlalchemy.schema import Column
from sqlalchemy.schema import Index

from libres.db.models.base import ORMBase
from libres.db.models.types import UUID, UTCDateTime
from libres.db.models.other import OtherModels
from libres.db.models.timespan import Timespan
from libres.db.models.timestamp import TimestampMixin


from typing import Literal
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import uuid
    from sedate.types import TzInfoOrName
    from sqlalchemy.orm import Query

    from libres.db.models import Allocation


class ReservationBlocker(TimestampMixin, ORMBase, OtherModels):
    """Describes a reservation blocker.

    Blockers can be used to signify that an allocation will be blocked for
    the specified time span, in order to e.g. perform cleaning duties on
    the relevant resource.

    """

    __tablename__ = 'reservation_blockers'

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
            name='reservation_blocker_target_type'
        ),
        nullable=False
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

    reason: Column[str | None] = Column(
        types.String(),
        nullable=True
    )

    __table_args__ = (
        Index('blocker_target_ix', 'target', 'id'),
    )

    def target_allocations(
        self,
        masters_only: bool = True
    ) -> Query[Allocation]:
        """ Returns the allocations this blocker is targeting.

        """
        Allocation = self.models.Allocation  # noqa: N806
        query = object_session(self).query(Allocation)
        query = query.filter(Allocation.group == self.target)

        if masters_only:
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
        """ Returns the timespans targeted by this blocker.

        The result is a list of :class:`~libres.db.models.timespan.Timespan`
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
                for allocation in self.target_allocations()
            ]
        else:
            raise NotImplementedError

    @property
    def title(self) -> str | None:
        return self.reason
