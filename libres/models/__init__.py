from sqlalchemy.ext import declarative
ORMBase = declarative.declarative_base()

from libres.models.allocation import Allocation
from libres.models.reserved_slot import ReservedSlot
from libres.models.reservation import Reservation


__all__ = ['ORMBase', 'Allocation', 'ReservedSlot', 'Reservation']
