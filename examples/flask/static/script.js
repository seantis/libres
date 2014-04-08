/* jshint -W100 */
$(document).ready(function() {

    var add_whole_day_allocation = function(date) {
        var quota = window.prompt('How many tickets should be available?', '1');

        var request = $.get('/add', {
            'quota': quota,
            'start': date.format(),
            'end': date.format(),
            'timezone': 'Europe/Zurich'
        });

        request.success(on_successful_request);
    };

    var menu_html = function(items) {
        var entries = [];

        _.each(items, function(i) {
            entries.push('<li><a href="#" id="' + i['id'] + '">' + i['title'] + '</a></li>');
        });

        return entries.join('\n');
    };

    var menu = function(selector, items) {
        var content = menu_html(items);

        var on_ready = function(origin, tooltip) {
            _.each(items, function(i) {
                $(tooltip).find('#' + i['id']).click(function() {
                    i['action'](origin);
                });
            });
        };

        $(selector).tooltipster({
            'content': $(content),
            'trigger': 'click',
            'interactive': true,
            'functionReady': on_ready
        });
    };

    var reserve_allocation = function(allocation_id) {
        var request = $.get('/reserve', {
            'id': allocation_id
        });

        request.success(on_successful_request);
    };

    var on_successful_request = function(response) {
        var r = JSON.parse(response);
        var note = '<div class="note ' + r['status'] + '">' + r['message'] + '</div>';
        $('.notes').html(note);
        $('#calendar').fullCalendar('refetchEvents');
    };

    var on_day_click = function(date) {
        add_whole_day_allocation(date);
    };

    var on_event_render = function(event, element, view) {
        $(element).data('id', event.id);
    };

    var on_all_events_rendered = function() {
        menu('.allocation', [
            {
                'id': 'reserve',
                'title': '☎&nbsp;Reserve',
                'action': function(origin) {
                    reserve_allocation($(origin).data('id'));
                }
            }
        ]);
    };

    $('#calendar').fullCalendar({
        timezone: 'Europe/Zurich',
        events: '/events',
        dayClick: on_day_click,
        eventAfterAllRender: on_all_events_rendered,
        eventRender: on_event_render
    });
});