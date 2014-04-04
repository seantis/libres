from datetime import datetime
from libres import new_scheduler


scheduler = new_scheduler(
    'KFC', 'New York Time Square',
    settings={
        'settings.dsn': 'postgresql+psycopg2://dev:dev@localhost:15432/libres'
    }
)

scheduler.setup_database()
scheduler.commit()

start = datetime(2012, 1, 1, 15, 0)
end = datetime(2012, 1, 1, 16, 0)
timezone = 'Europe/Zurich'

scheduler.allocate((start, end), timezone)
scheduler.reserve('test@example.org', (start, end), timezone)

scheduler.commit()
