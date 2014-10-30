import arrow
import pytest

from datetime import datetime

from libres.modules import calendar
from libres.modules import errors


def test_normalize_naive_date():
    naive_date = datetime(2014, 10, 1, 13, 30)
    normalized = calendar.normalize_date(naive_date, 'Europe/Zurich')

    assert normalized.tzname() == 'UTC'


def test_normalize_aware_date():
    aware_date = datetime(2014, 10, 1, 13, 30)
    normalized = calendar.normalize_date(aware_date, 'Europe/Zurich')

    assert normalized.tzname() == 'UTC'
    assert normalized.replace(tzinfo=None) == datetime(2014, 10, 1, 11, 30)


def test_is_whole_day_summertime():

    start = datetime(2014, 10, 26, 0, 0, 0)
    end = datetime(2014, 10, 26, 23, 59, 59)

    start, end = calendar.normalize_dates((start, end), 'Europe/Zurich')[0]

    assert calendar.is_whole_day(start, end, 'Europe/Zurich')


def test_is_whole_day_wintertime():

    start = datetime(2015, 3, 29, 0, 0, 0)
    end = datetime(2015, 3, 29, 23, 59, 59)

    start, end = calendar.normalize_dates((start, end), 'Europe/Zurich')[0]

    assert calendar.is_whole_day(start, end, 'Europe/Zurich')


def test_require_timezone_awareness():

    naive = datetime(2014, 10, 26, 0, 0, 0)

    with pytest.raises(errors.NotTimezoneAware):
        calendar.to_timezone(naive, 'UTC')

    with pytest.raises(errors.NotTimezoneAware):
        calendar.is_whole_day(naive, naive, 'UTC')

    with pytest.raises(errors.NotTimezoneAware):
        calendar.align_date_to_day(naive, 'UTC', 'up')


def test_overlaps():

    overlaps = [
        [
            datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 0),
            datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 0),
        ],
        [
            datetime(2013, 1, 1, 11, 0), datetime(2013, 1, 1, 12, 0),
            datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 0),
        ]
    ]

    doesnt = [
        [
            datetime(2013, 1, 1, 11, 0), datetime(2013, 1, 1, 11, 59, 59),
            datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 0),
        ]
    ]

    tz = 'Europe/Zurich'

    for dates in overlaps:
        assert calendar.overlaps(*dates)

        timezone_aware = [calendar.normalize_date(d, tz) for d in dates]
        assert calendar.overlaps(*timezone_aware)

    for dates in doesnt:
        assert not calendar.overlaps(*dates)

        timezone_aware = [calendar.normalize_date(d, tz) for d in dates]
        assert not calendar.overlaps(*timezone_aware)


def test_align_date_to_day():

    aligned = calendar.align_date_to_day(
        arrow.get(2012, 1, 24, 10), 'Europe/Zurich', 'down'
    )
    assert aligned == arrow.get(2012, 1, 24, 0, tzinfo='Europe/Zurich')
    assert aligned.tzname() == 'UTC'

    aligned = calendar.align_date_to_day(
        arrow.get(2012, 1, 24, 10), 'Europe/Zurich', 'up'
    )
    assert aligned == arrow.get(
        2012, 1, 24, 23, 59, 59, 999999, tzinfo='Europe/Zurich'
    )
    assert aligned.tzname() == 'UTC'
