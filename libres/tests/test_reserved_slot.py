import pytest

from datetime import datetime
from libres.db.models import Allocation, ReservedSlot
from pytz import utc
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

    scheduler.serial_session.add(allocation)
    scheduler.serial_session.add(slot)
    scheduler.serial_session.add(another)

    with pytest.raises(IntegrityError):
        scheduler.serial_session.flush()
