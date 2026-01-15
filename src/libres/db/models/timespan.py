from __future__ import annotations


from typing import NamedTuple
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from datetime import datetime


class Timespan(NamedTuple):
    start: datetime
    end: datetime
