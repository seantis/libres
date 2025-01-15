from __future__ import annotations

import sedate

from sqlalchemy import types


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from datetime import datetime
    from sqlalchemy.engine import Dialect

    _Base = types.TypeDecorator[datetime]
else:
    _Base = types.TypeDecorator


class UTCDateTime(_Base):
    """ Stores dates as UTC.

    Internally, they are stored as timezone naive, because Postgres takes
    the local timezone into account when working with timezones. We really
    want to have those dates in UTC at all times, though for convenience we
    make the dates timezone aware when retrieving the values and we make sure
    that timezone aware dates are converted to UTC before storing.

    """

    impl = types.DateTime
    cache_ok = True

    def process_bind_param(  # type:ignore[override]
        self,
        value: datetime | None,
        dialect: Dialect
    ) -> datetime | None:

        if value is not None:
            return sedate.to_timezone(value, 'UTC').replace(tzinfo=None)
        return None

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Dialect
    ) -> datetime | None:

        if value is not None:
            return sedate.replace_timezone(value, 'UTC')
        return None
