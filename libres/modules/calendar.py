from datetime import timedelta, datetime
from dateutil.tz import tzutc

import arrow

from libres.modules import utils


def utcnow():
    """ Returns datetime.utcnow with the timezone set to UTC (it's naive by
    default).

    """
    return datetime.utcnow().replace(tzinfo=tzutc())


def normalize_dates(dates, timezone):
    dates = list(utils.pairs(dates))

    # the dates are expected to be given local to the timezone, but
    # they are converted to utc for storage
    for ix, (start, end) in enumerate(dates):
        dates[ix] = [normalize_date(d, timezone) for d in ((start, end))]

    return dates


def normalize_date(date, timezone):
    return arrow.get(date).replace(tzinfo=timezone).to('UTC').datetime


def to_timezone(date, timezone):
    assert date.tzinfo, "the date must be timezone aware"
    return arrow.get(date).to(timezone).datetime


def is_whole_day(start, end, timezone):
    """Returns true if the given start, end range should be considered
    a whole-day range. This is so if the start time is 0:00:00 and the end
    time either 0:59:59 or 0:00:00 and if there is at least a diff
    erence of 23h 59m 59s / 86399 seconds between them.

    This is relevant for the calendar-display for now. This might very well be
    replaced again in the future when we introduce timezones.

    """

    start = arrow.get(start).to(timezone)
    end = arrow.get(end).to(timezone)

    assert start <= end, "The end needs to be equal or greater than the start"

    if (start.hour, start.minute, start.second) != (0, 0, 0):
        return False

    if (end.hour, end.minute, end.second) not in ((0, 0, 0), (23, 59, 59)):
        return False

    if (end - start).total_seconds() < 86399:
        return False

    return True


def overlaps(start, end, otherstart, otherend):
    if otherstart <= start and start <= otherend:
        return True

    if start <= otherstart and otherstart <= end:
        return True

    return False


def count_overlaps(dates, start, end):
    count = 0

    for otherstart, otherend in dates:
        count += overlaps(start, end, otherstart, otherend) and 1 or 0

    return count


def align_date_to_day(date, timezone, direction):
    """ Aligns the given date to the beginning or end of the day, depending on
    the direction. The beginning of the day only makes sense with a timezone
    (as it is a local thing), so the given timezone is used.

    The date however is always returned in the timezone it already is in.
    The time will be adjusted instead

    E.g.
    2012-1-24 10:00 down -> 2012-1-24 00:00
    2012-1-24 10:00 up   -> 2012-1-24 23:59:59'999999

    """
    assert direction in ('up', 'down')

    aligned = (0, 0, 0, 0) if direction == 'down' else (23, 59, 59, 999999)

    local = arrow.get(date).to(timezone)

    if (local.hour, local.minute, local.second, local.microsecond) == aligned:
        return date

    local = local.replace(hour=0, minute=0, second=0, microsecond=0)

    if direction == 'up':
        local = local + timedelta(days=1, microseconds=-1)

    return local.to(date.tzinfo)


def align_range_to_day(start, end, timezone):
    assert start <= end, "{} - {} is an invalid range".format(start, end)

    return (
        align_date_to_day(start, timezone, 'down'),
        align_date_to_day(end, timezone, 'up')
    )
