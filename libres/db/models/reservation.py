from collections import namedtuple
from datetime import timedelta

from sqlalchemy import types
from sqlalchemy.orm import object_session, deferred
from sqlalchemy.schema import Column
from sqlalchemy.schema import Index

from libres.db.models import ORMBase
from libres.db.models.types import GUID, UTCDateTime, JSON
from libres.db.models.other import OtherModels
from libres.db.models.timestamp import TimestampMixin
from libres.modules import calendar


Timespan = namedtuple(
    'Timespan', ('start', 'end')
)

BoundTimespan = namedtuple(
    'BoundTimespan', ('start', 'end', 'token', 'id')
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
        GUID(),
        nullable=False,
    )

    target = Column(
        GUID(),
        nullable=False,
    )

    target_type = Column(
        types.Enum(u'group', u'allocation', name='reservation_target_type'),
        nullable=False
    )

    resource = Column(
        GUID(),
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
        GUID()
    )

    quota = Column(
        types.Integer(),
        nullable=False
    )

    __table_args__ = (
        Index('target_status_ix', 'status', 'target', 'id'),
    )

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

        return query

    def display_start(self, timezone=None):
        """Does nothing but to form a nice pair to display_end."""
        return calendar.to_timezone(self.start, timezone or self.timezone)

    def display_end(self, timezone=None):
        """Returns the end plus one microsecond (nicer display)."""
        end = self.end + timedelta(microseconds=1)
        return calendar.to_timezone(end, timezone or self.timezone)

    def timespans(self):

        if self.target_type == u'allocation':
            return [(self.start, self.end + timedelta(microseconds=1))]
        elif self.target_type == u'group':
            return [
                Timespan(
                    a.display_start(), a.display_end()
                )
                for a in self._target_allocations()
            ]
        else:
            raise NotImplementedError

    def bound_timespans(self):

        return [
            BoundTimespan(
                t[0], t[1], self.token, self.id
            ) for t in self.timespans
        ]

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
