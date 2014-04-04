from sqlalchemy import types
from dateutil.tz import tzutc
from datetime import datetime


class UTCDateTime(types.TypeDecorator):

    impl = types.DateTime

    def process_bind_param(self, value, engine):
        if value is not None:
            assert value.tzinfo, 'datetimes must be timezone-aware'

            # ..though they are stored internally without timezone in utc
            # the timezone is attached again on date retrieval, see below.
            return value.astimezone(tzutc()).replace(tzinfo=None)

    def process_result_value(self, value, engine):
        if value is not None:
            return datetime(value.year, value.month, value.day,
                            value.hour, value.minute, value.second,
                            value.microsecond, tzinfo=tzutc())
