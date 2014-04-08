from flask import Flask, render_template, request

import json
import arrow
import libres
import isodate


app = Flask(__name__)
dsn = open('example.dsn').read()

context = 'example.app'
scheduler = libres.new_scheduler(
    context, 'Test Scheduler', settings={'settings.dsn': dsn}
)


@app.route('/events')
def events():

    timezone = request.args.get('timezone')
    start = arrow.get(request.args.get('start')).replace(tzinfo=timezone)
    end = arrow.get(request.args.get('end')).replace(tzinfo=timezone)

    events = []  # fullcalendar compatible events

    start = start.datetime
    end = end.datetime
    for allocation in scheduler.allocations_in_range(start, end):
        s = arrow.get(allocation.display_start).to(timezone)
        e = arrow.get(allocation.display_end).to(timezone)

        classes = ['allocation']
        availability = scheduler.queries.availability_by_allocations(
            [allocation]
        )

        if availability == 0:
            classes.append('unavailable')
        elif availability >= 80:
            classes.append('available')
        elif availability >= 40:
            classes.append('partly-available')

        quota_left = scheduler.free_allocations_count(
            allocation, allocation.start, allocation.end
        )

        events.append(
            dict(
                id=allocation.id,
                className=' '.join(classes),
                start=isodate.datetime_isoformat(s),
                end=isodate.datetime_isoformat(e),
                allDay=allocation.whole_day,
                title='{} Tickets left'.format(quota_left)
            )
        )

    return json.dumps(events)


@app.route('/add')
def allocation_add():
    quota = request.args.get('quota')
    timezone = request.args.get('timezone')

    start = arrow.get(request.args.get('start'))
    end = arrow.get(request.args.get('end'))

    try:
        scheduler.allocate(
            (start, end), timezone=timezone, whole_day=True, quota=int(quota)
        )
        scheduler.commit()
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
            dates=(
                arrow.get(allocation.start).to(allocation.timezone),
                arrow.get(allocation.end).to(allocation.timezone)
            ),
            timezone=allocation.timezone
        )
        scheduler.approve_reservation(token)
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
    scheduler.setup_database()
    scheduler.commit()
    app.run(debug=True)
