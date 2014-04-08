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

        print(s, e)
        events.append(
            dict(
                start=isodate.datetime_isoformat(s),
                end=isodate.datetime_isoformat(e),
                allDay=allocation.whole_day
            )
        )

    return json.dumps(events)


@app.route('/add')
def allocation_add():
    timezone = request.args.get('timezone')

    start = arrow.get(request.args.get('start'))
    end = arrow.get(request.args.get('end'))

    try:
        scheduler.allocate((start, end), timezone=timezone, whole_day=True)
        scheduler.commit()
    except:
        scheduler.rollback()
        raise

    return u''


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    scheduler.setup_database()
    scheduler.commit()
    app.run(debug=True)
