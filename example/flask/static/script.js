$(document).ready(function() {
    $('#calendar').fullCalendar({
        timezone: 'Europe/Zurich',
        events: '/events',
        dayClick: function(date, jsEvent, view) {
            $.get('/add', {
                'start': date.format(),
                'end': date.format(),
                'timezone': 'Europe/Zurich'
            }).success(function() {
                $('#calendar').fullCalendar('refetchEvents');
            });
        }
    });
});