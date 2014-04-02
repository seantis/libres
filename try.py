from libres import new_scheduler
scheduler = new_scheduler(
    'KFC', settings={
        'settings.dsn': 'postgresql+psycopg2://dev:dev@localhost:15432/libres'
    }
)

scheduler.begin()
scheduler.allocate(['2013-01-01T13:00', '2013-01-01T15:00'], 'Europe/Zurich')
scheduler.rollback()

scheduler.begin()
scheduler.allocate(['2013-01-01T13:00', '2013-01-01T15:00'], 'Europe/Zurich')
scheduler.commit()
