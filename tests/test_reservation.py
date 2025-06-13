from __future__ import annotations

import pytest

from datetime import datetime, timedelta
from libres.db.models import Reservation
from libres.modules.errors import OverlappingReservationError
from sedate import standardize_date
from uuid import uuid4


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from libres.db.scheduler import Scheduler


def test_reservation_title() -> None:
    assert Reservation(email='test@example.org').title == 'test@example.org'


def test_unknown_target_type() -> None:
    with pytest.raises(NotImplementedError):
        Reservation(target_type='foo').timespans()  # type: ignore[misc]


def test_reservation_timespans(scheduler: Scheduler) -> None:
    start = datetime(2015, 2, 5, 15)
    end = datetime(2015, 2, 5, 16)

    scheduler.allocate(dates=(start, end))
    token = scheduler.reserve('test@example.org', dates=(start, end))
    scheduler.commit()

    reservation = scheduler.reservations_by_token(token)[0]

    timespans = reservation.timespans()
    assert len(timespans) == 1

    assert timespans[0].start == reservation.start
    assert timespans[0].end == reservation.end + timedelta(microseconds=1)


def test_group_reservation_timespans(scheduler: Scheduler) -> None:
    dates = [
        (datetime(2015, 2, 5, 15), datetime(2015, 2, 5, 16)),
        (datetime(2015, 2, 6, 15), datetime(2015, 2, 6, 16))
    ]

    group = scheduler.allocate(dates=dates, grouped=True)[0].group
    token = scheduler.reserve('test@example.org', group=group)
    scheduler.commit()

    reservation = scheduler.reservations_by_token(token)[0]

    timespans = reservation.timespans()
    assert len(timespans) == 2

    assert timespans[0].start == standardize_date(dates[0][0], 'Europe/Zurich')
    assert timespans[0].end == standardize_date(dates[0][1], 'Europe/Zurich')\
        - timedelta(microseconds=1)

    assert timespans[1].start == standardize_date(dates[1][0], 'Europe/Zurich')
    assert timespans[1].end == standardize_date(dates[1][1], 'Europe/Zurich')\
        - timedelta(microseconds=1)


def test_overlapping_reservations(scheduler: Scheduler) -> None:
    start = datetime(2015, 2, 5, 15)
    end = datetime(2015, 2, 5, 16)

    scheduler.allocate(dates=(start, end))

    # overlapping reservations are only prohibited on a per-session base
    scheduler.reserve(
        email='test@example.org',
        dates=(start, end),
        session_id=uuid4()
    )
    scheduler.reserve(
        email='test@example.org',
        dates=(start, end),
        session_id=uuid4()
    )

    session_id = uuid4()
    scheduler.reserve(
        email='test@example.org',
        dates=(start, end),
        session_id=session_id
    )

    with pytest.raises(OverlappingReservationError):
        scheduler.reserve(
            email='test@example.org',
            dates=(start, end),
            session_id=session_id
        )
