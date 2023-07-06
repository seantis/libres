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


import typing as _t
if _t.TYPE_CHECKING:
    import uuid
    from sedate.types import TzInfoOrName
    from sqlalchemy.orm import Query

    from libres.db.models import Allocation


class Timespan(_t.NamedTuple):
    start: datetime
    end: datetime


class Reservation(TimestampMixin, ORMBase, OtherModels):
    """Describes a pending or approved reservation.

    """

    __tablename__ = 'reservations'

    id: 'Column[int]' = Column(
        types.Integer(),
        primary_key=True,
        autoincrement=True
    )

    token: 'Column[uuid.UUID]' = Column(
        UUID(),
        nullable=False,
    )

    target: 'Column[uuid.UUID]' = Column(
        UUID(),
        nullable=False,
    )

    target_type: 'Column[_t.Literal["group", "allocation"]]' = Column(
        types.Enum(  # type:ignore[arg-type]
            'group', 'allocation',
            name='reservation_target_type'
        ),
        nullable=False
    )

    type: 'Column[_t.Optional[str]]' = Column(
        types.Text(),
        nullable=True
    )

    resource: 'Column[uuid.UUID]' = Column(
        UUID(),
        nullable=False
    )

    start: 'Column[_t.Optional[datetime]]' = Column(
        UTCDateTime(timezone=False),
        nullable=True
    )

    end: 'Column[_t.Optional[datetime]]' = Column(
        UTCDateTime(timezone=False),
        nullable=True
    )

    timezone: 'Column[_t.Optional[str]]' = Column(
        types.String(),
        nullable=True
    )

    status: 'Column[_t.Literal["pending", "approved"]]' = Column(
        types.Enum(  # type:ignore[arg-type]
            'pending', 'approved',
            name="reservation_status"
        ),
        nullable=False
    )

    data: 'Column[_t.Optional[_t.Any]]' = deferred(
        Column(
            JSON(),
            nullable=True
        )
    )

    email: 'Column[str]' = Column(
        types.Unicode(254),
        nullable=False
    )

    session_id: 'Column[_t.Optional[uuid.UUID]]' = Column(
        UUID()
    )

    quota: 'Column[int]' = Column(
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

    def _target_allocations(self) -> 'Query[Allocation]':
        """ Returns the allocations this reservation is targeting. This should
        NOT be confused with db.allocations_by_reservation. The method in
        the db module returns the actual allocations belonging to an approved
        reservation.

        This method only returns the master allocations to get information
        about timespans and other properties. If you don't know exactly
        what you're doing you do not want to use this method as misuse might
        be dangerous.

        """
        Allocation = self.models.Allocation
        query = object_session(self).query(Allocation)
        query = query.filter(Allocation.group == self.target)

        # master allocations only
        query = query.filter(Allocation.resource == Allocation.mirror_of)

        # order by date
        query = query.order_by(Allocation._start)

        return query

    def display_start(
        self,
        timezone: _t.Optional['TzInfoOrName'] = None
    ) -> datetime:
        """Does nothing but to form a nice pair to display_end."""
        assert self.start is not None
        if timezone is None:
            assert self.timezone is not None
            timezone = self.timezone
        return sedate.to_timezone(self.start, timezone)

    def display_end(
        self,
        timezone: _t.Optional['TzInfoOrName'] = None
    ) -> datetime:
        """Returns the end plus one microsecond (nicer display)."""
        assert self.end is not None
        if timezone is None:
            assert self.timezone is not None
            timezone = self.timezone

        end = self.end + timedelta(microseconds=1)
        return sedate.to_timezone(end, timezone)

    def timespans(self) -> _t.List[Timespan]:
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

        return object_session(self).query(~query.exists()).scalar()
