import sedate
import sys

from collections import Iterable
from uuid import uuid5 as new_uuid_mirror


if sys.version_info.major >= 3:
    basestring = str


def generate_uuids(uuid, quota):
    return [new_uuid_mirror(uuid, str(n)) for n in range(1, quota)]


def flatten(l):
    """Generator for flattening irregularly nested lists. 'Borrowed' from here:

    http://stackoverflow.com/questions/2158395/
    flatten-an-irregular-list-of-lists-in-python
    """
    for el in l:
        if isinstance(el, Iterable) and not isinstance(el, basestring):
            for sub in flatten(el):
                yield sub
        else:
            yield el


def pairs(l):
    """Takes any list and returns pairs:
    ((a,b),(c,d)) => ((a,b),(c,d))
    (a,b,c,d) => ((a,b),(c,d))

    http://opensourcehacker.com/2011/02/23/
    tuplifying-a-list-or-pairs-in-python/
    """
    l = list(flatten(l))
    return zip(*[l[x::2] for x in (0, 1)])


def is_valid_reservation_length(start, end, timezone):
    start = sedate.standardize_date(start, timezone)
    end = sedate.standardize_date(end, timezone)

    hours = (end - start).total_seconds() // 3600

    if hours < 24:
        return True

    if sedate.is_whole_day(start, end, timezone) and hours <= 25:
        return True

    return False
