import typing as _t
if _t.TYPE_CHECKING:
    from libres.db.models import Allocation


class Exposure:
    @staticmethod
    def is_allocation_exposed(allocation: 'Allocation') -> _t.Literal[True]:
        return True
