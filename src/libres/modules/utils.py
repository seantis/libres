import sedate

from collections.abc import Iterable
from uuid import UUID, uuid5 as new_uuid_mirror


import typing as _t
if _t.TYPE_CHECKING:
    from datetime import datetime
    from sedate.types import TzInfoOrName
    from typing_extensions import TypeAlias

    _T = _t.TypeVar('_T')
    _NestedIterable: TypeAlias = _t.Iterable[
        _t.Union[_T, '_NestedIterable[_T]']
    ]


def generate_uuids(uuid: UUID, quota: int) -> _t.List[UUID]:
    return [new_uuid_mirror(uuid, str(n)) for n in range(1, quota)]


def flatten(listlike: '_NestedIterable[_T]') -> _t.Iterable['_T']:
    """Generator for flattening irregularly nested lists. 'Borrowed' from here:

    http://stackoverflow.com/questions/2158395/
    flatten-an-irregular-list-of-lists-in-python
    """
    for el in listlike:
        if isinstance(el, Iterable) and not isinstance(el, str):
            yield from flatten(el)
        else:
            yield el  # type:ignore[misc]


def pairs(listlike: '_NestedIterable[_T]') -> '_t.Iterator[_t.Tuple[_T, _T]]':
    """Takes any list and returns pairs:
    ((a,b),(c,d)) => ((a,b),(c,d))
    (a,b,c,d) => ((a,b),(c,d))

    http://opensourcehacker.com/2011/02/23/
    tuplifying-a-list-or-pairs-in-python/
    """
    flat = list(flatten(listlike))
    return zip(flat[0::2], flat[1::2])


def is_valid_reservation_length(
    start: 'datetime',
    end: 'datetime',
    timezone: 'TzInfoOrName'
) -> bool:

    start = sedate.standardize_date(start, timezone)
    end = sedate.standardize_date(end, timezone)

    hours = (end - start).total_seconds() // 3600

    # FIXME: This might not handle 23 hour long days correctly...
    if hours < 24:
        return True

    if sedate.is_whole_day(start, end, timezone) and hours <= 25:
        return True

    return False
