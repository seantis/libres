from sqlalchemy.sql import and_, or_

from libres.db.models import Allocation
from libres.context.accessor import ContextAccessor


class Queries(object):
    """ Contains helper methods independent of the resource (as owned by
    :class:`.scheduler.Scheduler`)

    Some contained methods require the current context (for the session).
    Some contained methods do not require any context, they are marked
    as staticmethods.

    """

    def __init__(self, context):
        self.context = ContextAccessor(context, autocreate=False)

    @property
    def session(self):
        return self.context.session

    def all_allocations_in_range(self, start, end):
        return self.allocations_in_range(
            self.session.query(Allocation), start, end
        )

    @staticmethod
    def allocations_in_range(query, start, end):
        """ Takes an allocation query and limits it to the allocations
        overlapping with start and end.

        """
        return query.filter(
            or_(
                and_(
                    Allocation._start <= start,
                    start <= Allocation._end
                ),
                and_(
                    start <= Allocation._start,
                    Allocation._start <= end
                )
            )
        )
