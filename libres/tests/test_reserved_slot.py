import pytest

from datetime import datetime
from libres.db.models import Allocation, ReservedSlot
from pytz import utc, timezone
from sqlalchemy.exc import IntegrityError
from uuid import uuid4 as new_uuid


def test_add_reserved_slot(scheduler):

    allocation = Allocation(raster=15, resource=scheduler.resource)
    allocation.start = datetime(2011, 1, 1, 15, tzinfo=utc)
    allocation.end = datetime(2011, 1, 1, 15, 59, tzinfo=utc)
    allocation.group = new_uuid().hex
    allocation.mirror_of = scheduler.resource

    reservation = new_uuid()

    slot = ReservedSlot(resource=allocation.resource)
    slot.start = allocation.start
    slot.end = allocation.end
    slot.allocation = allocation
    slot.reservation = reservation

    # Ensure that the same slot cannot be doubly used
    another = ReservedSlot(resource=allocation.resource)
    another.start = allocation.start
    another.end = allocation.end
    another.allocation = allocation
    another.reservation = reservation

    scheduler.session.add(allocation)
    scheduler.session.add(slot)
    scheduler.session.add(another)

    with pytest.raises(IntegrityError):
        scheduler.session.flush()


def test_reserved_slot_date_display(scheduler):
    start = datetime(2015, 2, 5, 10, 0, tzinfo=utc)
    end = datetime(2015, 2, 5, 12, 0, tzinfo=utc)

    allocation = Allocation(raster=5)
    allocation.start = start
    allocation.end = end

    slot = ReservedSlot()
    slot.allocation = allocation
    slot.start = start
    slot.end = end

    tz = timezone('Europe/Zurich')

    assert slot.display_start(timezone='Europe/Zurich') == tz.localize(
        datetime(2015, 2, 5, 11, 0)
    )

    assert slot.display_end(timezone='Europe/Zurich') == tz.localize(
        datetime(2015, 2, 5, 13, 0)
    )
