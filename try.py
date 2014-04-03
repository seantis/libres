from libres import new_scheduler
from libres.models import Reservation


scheduler = new_scheduler(
    'KFC', 'New York Time Square',
    settings={
        'settings.dsn': 'postgresql+psycopg2://dev:dev@localhost:15432/libres'
    }
)

scheduler.setup_database()
scheduler.commit()

res = Reservation()
res.data = {'test': 1234}
scheduler.context.serial_session.add(res)
scheduler.commit()
