from __future__ import annotations


from typing import Literal
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from libres.db.models import Allocation


class Exposure:
    @staticmethod
    def is_allocation_exposed(allocation: Allocation) -> Literal[True]:
        return True
