""" The calendar module provides methods that deal with dates and timezones.

There are projects like `Arrow <https://github.com/crsmithdev/arrow>`_ or
`Delorean <https://github.com/crsmithdev/arrow>`_ which provide ways to work
with timezones without having to think about it too much.

Libres doesn't use them because its author *wants* to think about these things,
to ensure they are correct, and partly because of self-loathing.

Adding another layer makes these things harder.

That being said, further up the stacks - in the web application for example -
it might very well make sense to use a datetime wrapper library.

"""

import pytz

from datetime import datetime, timedelta
from libres.modules import compat, errors

mindatetime = pytz.utc.localize(datetime.min)
maxdatetime = pytz.utc.localize(datetime.max)


def ensure_timezone(timezone):
    """ Make sure the given timezone is a pytz timezone, not just a string. """

    if isinstance(timezone, compat.string_types):
        return pytz.timezone(timezone)

    return timezone


def standardize_date(date, timezone):
    """ Takes the given date and converts it to UTC.

    The given timezone is set on timezone-naive dates and converted to
    on timezone-aware dates. That essentially means that you should pass
    the timezone that you know the date to be, even if the date is in another
    timezone (like UTC) or if the date does not have a timezone set.

    """

    assert timezone, "The timezone may *not* be empty!"

    if date.tzinfo is None:
        date = replace_timezone(date, timezone)

    return to_timezone(date, 'UTC')


def replace_timezone(date, timezone):
    """ Takes the given date and replaces the timezone with the given timezone.

    No conversion is done in this method, it's simply a safe way to do the
    following (which is problematic with timzones that have daylight saving
    times)::

        # don't do this:
        date.replace(tzinfo=timezone('Europe/Zurich'))

        # do this:
        calendar.replace_timezone(date, 'Europe/Zurich')

    """

    timezone = ensure_timezone(timezone)

    return timezone.normalize(timezone.localize(date.replace(tzinfo=None)))


def to_timezone(date, timezone):
    """ Takes the given date and converts it to the given timezone.

    The given date must already be timezone aware for this to work.

    """

    if not date.tzinfo:
        raise errors.NotTimezoneAware()

    timezone = ensure_timezone(timezone)
    return timezone.normalize(date.astimezone(timezone))


def utcnow():
    """ Returns a timezone-aware datetime.utcnow(). """
    return replace_timezone(datetime.utcnow(), 'UTC')


def is_whole_day(start, end, timezone):
    """Returns true if the given start, end range should be considered
    a whole-day range. This is so if the start time is 0:00:00 and the end
    time either 0:59:59 or 0:00:00 and if there is at least a diff
    erence of 23h 59m 59s / 86399 seconds between them.

    This is relevant for the calendar-display for now. This might very well be
    replaced again in the future when we introduce timezones.

    """

    # without replacing the tzinfo, the total seconds count later will return
    # the wrong number - it is correct, because the total seconds do not
    # constitute a whole day, but we are not interested in the actual time
    # but we need to know that the day starts at 0:00 and ends at 24:00,
    # between which we need 24 hours (just looking at the time)
    start = to_timezone(start, timezone).replace(tzinfo=None)
    end = to_timezone(end, timezone).replace(tzinfo=None)

    assert start <= end, "The end needs to be equal or greater than the start"

    if (start.hour, start.minute, start.second) != (0, 0, 0):
        return False

    if (end.hour, end.minute, end.second) not in ((0, 0, 0), (23, 59, 59)):
        return False

    if (end - start).total_seconds() < 86399:
        return False

    return True


def overlaps(start, end, otherstart, otherend):
    """ Returns True if the given dates overlap in any way. """

    if otherstart <= start and start <= otherend:
        return True

    if start <= otherstart and otherstart <= end:
        return True

    return False


def count_overlaps(dates, start, end):
    """ Goes through the list of start/end tuples in 'dates' and returns the
    number of times start/end overlaps with any of the dates.

    """
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

    local = to_timezone(date, timezone)

    if (local.hour, local.minute, local.second, local.microsecond) == aligned:
        return date

    local = local.replace(hour=0, minute=0, second=0, microsecond=0)

    if direction == 'up':
        local = local + timedelta(days=1, microseconds=-1)

    return to_timezone(local, date.tzname())


def align_range_to_day(start, end, timezone):
    assert start <= end, "{} - {} is an invalid range".format(start, end)

    return (
        align_date_to_day(start, timezone, 'down'),
        align_date_to_day(end, timezone, 'up')
    )


def get_date_range(day, start_time, end_time):
    """Returns the date-range of a date a start and an end time."""

    start = datetime.combine(day.date(), start_time).replace(tzinfo=day.tzinfo)
    end = datetime.combine(day.date(), end_time).replace(tzinfo=day.tzinfo)

    # since the user can only one date with separate times it is assumed
    # that an end before a start is meant for the following day
    if end < start:
        end += timedelta(days=1)

    return start, end
