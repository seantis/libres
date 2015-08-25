import sedate

from sqlalchemy import types


class UTCDateTime(types.TypeDecorator):
    """ Stores dates as UTC.

    Internally, they are stored as timezone naive, because Postgres takes
    the local timezone into account when working with timezones. We really
    want to have those dates in UTC at all times, though for convenience we
    make the dates timezone aware when retrieving the values and we make sure
    that timezone aware dates are converted to UTC before storing.

    """

    impl = types.DateTime

    def process_bind_param(self, value, engine):
        if value is not None:
            return sedate.to_timezone(value, 'UTC').replace(tzinfo=None)

    def process_result_value(self, value, engine):
        if value is not None:
            return sedate.replace_timezone(value, 'UTC')
