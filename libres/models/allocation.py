from sqlalchemy import types
from sqlalchemy.schema import Column

from libres.models import ORMBase


class Allocation(ORMBase):
    """Describes a timespan within which one or many timeslots can be
    reserved.

    There's an important concept to understand before working with allocations.
    The resource uuid of an alloction is not always pointing to the actual
    resource.

    A resource may in fact be a real resource, or an imaginary resource with
    a uuid derived from the real resource. This is a somewhat historical
    artifact.

    If you need to know which allocations belong to a real resource, the
    mirror_of field is what's relevant. The originally created allocation
    with the real_resource is also called the master-allocation and it is
    the one allocation with mirror_of and resource being equal.

    When in doubt look at the managed_* functions of seantis.reservation.db's
    Scheduler class.

    """

    __tablename__ = 'allocations'

    id = Column(types.Integer(), primary_key=True, autoincrement=True)
