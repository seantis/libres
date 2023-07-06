from datetime import datetime, timedelta
from libres.modules.utils import is_valid_reservation_length


def test_is_valid_reservation_length():
    assert is_valid_reservation_length(
        start=datetime(2017, 1, 1, 0),
        end=datetime(2017, 1, 2, 0) - timedelta(microseconds=1),
        timezone='Europe/Zurich'
    )

    assert is_valid_reservation_length(
        start=datetime(2017, 1, 1, 0),
        end=datetime(2017, 1, 2, 0),
        timezone='Europe/Zurich'
    )

    assert not is_valid_reservation_length(
        start=datetime(2017, 1, 1, 1),
        end=datetime(2017, 1, 2, 1),
        timezone='Europe/Zurich'
    )

    assert is_valid_reservation_length(
        start=datetime(2016, 10, 29, 0),
        end=datetime(2016, 10, 30, 0),
        timezone='Europe/Zurich'
    )

    assert not is_valid_reservation_length(
        start=datetime(2016, 10, 29, 1),
        end=datetime(2016, 10, 30, 1),
        timezone='Europe/Zurich'
    )
