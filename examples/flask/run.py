from flask import Flask, render_template, request

import json
import arrow
import libres
import isodate

from testing.postgresql import Postgresql


app = Flask(__name__)
scheduler = None


@app.route('/events')
def events():

    timezone = request.args.get('timezone')
    start = arrow.get(request.args.get('start')).replace(tzinfo=timezone)
    end = arrow.get(request.args.get('end')).replace(tzinfo=timezone)

    events = []  # fullcalendar compatible events

    start = start.datetime
    end = end.datetime

    for allocation in scheduler.allocations_in_range(start, end):

        classes = ['allocation']
        availability = scheduler.availability(allocation.start, allocation.end)

        if 80 <= availability and availability <= 100:
            classes.append('available')
        elif 0 < availability and availability <= 80:
            classes.append('partly-available')
        else:
            classes.append('unavailable')

        events.append(
            dict(
                id=allocation.id,
                className=' '.join(classes),
                start=isodate.datetime_isoformat(allocation.display_start()),
                end=isodate.datetime_isoformat(allocation.display_end()),
                allDay=allocation.whole_day,
                title='{} Tickets left'.format(allocation.quota_left)
            )
        )

    return json.dumps(events)


@app.route('/add')
def allocation_add():
    quota = request.args.get('quota')
    timezone = request.args.get('timezone')
    start = arrow.get(request.args.get('start')).replace(tzinfo=timezone)
    end = arrow.get(request.args.get('end')).replace(tzinfo=timezone)

    try:
        scheduler.allocate((start, end), whole_day=True, quota=int(quota))
        scheduler.commit()
    except libres.modules.errors.OverlappingAllocationError:
        return json.dumps(
            {
                'status': 'fail',
                'message': 'This day is already fully allocated.'
            }
        )
    except:
        scheduler.rollback()
        raise

    return json.dumps(
        {'status': 'success', 'message': 'An allocation has been added.'}
    )


@app.route('/reserve')
def allocation_reserve():

    try:
        allocation = scheduler.allocation_by_id(request.args.get('id'))

        token = scheduler.reserve(
            email='user@example.org',
            dates=(allocation.start, allocation.end)
        )
        scheduler.approve_reservations(token)
        scheduler.commit()
    except libres.modules.errors.AlreadyReservedError:
        scheduler.rollback()
        return json.dumps(
            {
                'status': 'fail',
                'message': 'The given allocation is allready fully reserved.'
            }
        )
    except:
        scheduler.rollback()
        raise

    return json.dumps(
        {'status': 'success', 'message': 'A reservation has been made'}
    )


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':

    postgresql = Postgresql()

    try:
        context = libres.registry.register_context('flask-exmaple')
        context.set_setting('dsn', postgresql.url())
        scheduler = libres.new_scheduler(
            context, 'Test Scheduler', timezone='Europe/Zurich'
        )
        scheduler.setup_database()
        scheduler.commit()

        app.run(debug=True, host='0.0.0.0')

    finally:
        postgresql.stop()
