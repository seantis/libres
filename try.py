from libres import new_scheduler
from libres.modules.events import on_allocations_add


scheduler = new_scheduler(
    'KFC', 'New York Time Square',
    settings={
        'settings.dsn': 'postgresql+psycopg2://dev:dev@localhost:15432/libres'
    }
)


def on_add(context, allocations):
    print("added {} allocations on {}".format(len(allocations), context))

on_allocations_add.append(on_add)

scheduler.allocate(['2013-01-01T13:00', '2013-01-01T15:00'], 'Europe/Zurich')
scheduler.allocate(['2013-01-02T13:00', '2013-01-02T15:00'], 'Europe/Zurich')
scheduler.rollback()

scheduler.allocate(['2013-01-01T13:00', '2013-01-01T15:00'], 'Europe/Zurich')
scheduler.allocate(['2013-01-02T13:00', '2013-01-02T15:00'], 'Europe/Zurich')
scheduler.commit()
