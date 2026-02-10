from __future__ import annotations

import sedate

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import types
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import object_session
from sqlalchemy.orm import Mapped
from sqlalchemy.schema import Index

from libres.db.models.base import ORMBase
from libres.db.models.other import OtherModels
from libres.db.models.timespan import Timespan
from libres.db.models.timestamp import TimestampMixin


from typing import Any
from typing import Literal
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sedate.types import TzInfoOrName
    from sqlalchemy.orm import Query

    from libres.db.models import Allocation


class Reservation(TimestampMixin, ORMBase, OtherModels):
    """Describes a pending or approved reservation.

    """

    __tablename__ = 'reservations'

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    token: Mapped[UUID]

    target: Mapped[UUID]

    target_type: Mapped[Literal['group', 'allocation']] = mapped_column(
        types.Enum(
            'group', 'allocation',
            name='reservation_target_type'
        )
    )

    type: Mapped[str] = mapped_column(types.Text())

    resource: Mapped[UUID]

    start: Mapped[datetime | None]

    end: Mapped[datetime | None]
    timezone: Mapped[str | None]

    status: Mapped[Literal['pending', 'approved']] = mapped_column(
        types.Enum(
            'pending', 'approved',
            name='reservation_status'
        )
    )

    data: Mapped[dict[str, Any] | None] = mapped_column(deferred=True)

    email: Mapped[str] = mapped_column(types.Unicode(254))

    session_id: Mapped[UUID | None]

    quota: Mapped[int]

    __table_args__ = (
        Index('target_status_ix', 'status', 'target', 'id'),
    )

    __mapper_args__ = {
        'polymorphic_identity': 'generic',
        'polymorphic_on': type
    }

    def __init__(self) -> None:
        # NOTE: Avoid auto-generated __init__, the mypy plugin is
        #       deprecated and cannot be used with newer versions.
        pass

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
        session = object_session(self)
        assert session, (
            "Don't call if the reservation is detached"
        )
        Allocation = self.models.Allocation  # noqa: N806
        query = session.query(Allocation)
        query = query.filter(Allocation.group == self.target)

        # master allocations only
        query = query.filter(Allocation.resource == Allocation.mirror_of)

        # order by date
        query = query.order_by(Allocation._start)

        return query

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
        session = object_session(self)
        assert session, (
            "Don't call if the reservation is detached"
        )

        query = self._target_allocations()
        query = query.filter(self.models.Allocation.approve_manually == True)

        # A reservation is deemed autoapprovable if no allocation
        # requires explicit approval

        return session.query(~query.exists()).scalar()  # type: ignore[no-any-return]
