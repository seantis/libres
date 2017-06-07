import sedate

from collections import namedtuple
from datetime import timedelta

from sqlalchemy import types
from sqlalchemy.orm import object_session, deferred
from sqlalchemy.schema import Column
from sqlalchemy.schema import Index

from libres.db.models import ORMBase
from libres.db.models.types import UUID, UTCDateTime, JSON
from libres.db.models.other import OtherModels
from libres.db.models.timestamp import TimestampMixin


Timespan = namedtuple(
    'Timespan', ('start', 'end')
)


class Reservation(TimestampMixin, ORMBase, OtherModels):
    """Describes a pending or approved reservation.

    """

    __tablename__ = 'reservations'

    id = Column(
        types.Integer(),
        primary_key=True,
        autoincrement=True
    )

    token = Column(
        UUID(),
        nullable=False,
    )

    target = Column(
        UUID(),
        nullable=False,
    )

    target_type = Column(
        types.Enum(u'group', u'allocation', name='reservation_target_type'),
        nullable=False
    )

    type = Column(
        types.Text(),
        nullable=True
    )

    resource = Column(
        UUID(),
        nullable=False
    )

    start = Column(
        UTCDateTime(timezone=False),
        nullable=True
    )

    end = Column(
        UTCDateTime(timezone=False),
        nullable=True
    )

    timezone = Column(
        types.String(),
        nullable=True
    )

    status = Column(
        types.Enum(u'pending', u'approved', name="reservation_status"),
        nullable=False
    )

    data = deferred(
        Column(
            JSON(),
            nullable=True
        )
    )

    email = Column(
        types.Unicode(254),
        nullable=False
    )

    session_id = Column(
        UUID()
    )

    quota = Column(
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

    def _target_allocations(self):
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

    def display_start(self, timezone=None):
        """Does nothing but to form a nice pair to display_end."""
        return sedate.to_timezone(self.start, timezone or self.timezone)

    def display_end(self, timezone=None):
        """Returns the end plus one microsecond (nicer display)."""
        end = self.end + timedelta(microseconds=1)
        return sedate.to_timezone(end, timezone or self.timezone)

    def timespans(self):
        """ Returns the timespans targeted by this reservation.

        The result is a list of :class:`~libres.db.models.reservation.Timespan`
        timespans. The start and end are the start and end dates of the
        referenced allocations.

        The timespans are ordered by start.

        """

        if self.target_type == u'allocation':
            # we don't need to hit the database in this case
            return [
                Timespan(self.start, self.end + timedelta(microseconds=1))
            ]
        elif self.target_type == u'group':
            return [
                Timespan(a.start, a.end) for a in self._target_allocations()
            ]
        else:
            raise NotImplementedError

    @property
    def title(self):
        return self.email

    @property
    def autoapprovable(self):
        query = self._target_allocations()
        query = query.filter(self.models.Allocation.approve_manually == True)

        # A reservation is deemed autoapprovable if no allocation
        # requires explicit approval

        return query.first() is None
