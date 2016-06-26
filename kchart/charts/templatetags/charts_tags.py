# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from django.core.urlresolvers import reverse
from django.template import Library
from django.utils.safestring import mark_safe

from ..utils import KR_TZ


register = Library()


@register.filter
def get_range(value):
    """
    Filter - returns a list containing range made from given value
    Usage (in template):

    <ul>{% for i in 3|get_range %}
      <li>{{ i }}. Do something</li>
    {% endfor %}</ul>

    Results with the HTML:
    <ul>
      <li>0. Do something</li>
      <li>1. Do something</li>
      <li>2. Do something</li>
    </ul>

    Instead of 3 one may use the variable set in the views
    """
    return range(value)


@register.filter
def subtract(value, arg):
    return value - arg


@register.filter
def chart_list(aggregate_chart):
    '''Return a flattened list consisting of this chart plus it's sub charts'''
    return [aggregate_chart] + list(aggregate_chart.charts.all())


def _th_tooltip(text, tooltip):
    return ('<th data-toggle="tooltip" data-container="body" '
            'data-placement="bottom" title="{}">{}</th>'.format(tooltip, text))


def _realtime_row(text, tooltip, fields):
    row = '<tr>{}'.format(_th_tooltip(text, tooltip))
    for field in fields:
        if field:
            row += '<td>{}</td>'.format(field)
        else:
            row += '<td><span class="icon icon-minus"></span></td>'
    row += '</tr>'
    return row


def _realtime_a(timestamp):
    timestamp = timestamp.astimezone(KR_TZ)
    return '<a href="{}?date={}&hour={}">{}:00 KST</a>'.format(
        reverse('charts:hourly-chart-detail'),
        timestamp.strftime('%Y%m%d'),
        timestamp.strftime('%H'),
        timestamp.strftime('%Y.%m.%d %H')
    )


def _realtime_row_timestamp(text, tooltip, fields, timestamp_fields):
    row = '<tr>{}'.format(_th_tooltip(text, tooltip))
    for field, timestamp in zip(fields, timestamp_fields):
        if field:
            row += '<td>{} ({})</td>'.format(field, _realtime_a(timestamp))
        else:
            row += '<td><span class="icon icon-minus"></span></td>'
    row += '</tr>'
    return row


@register.filter
def song_realtime_table(song):
    details = song.get_chart_details(include_service_slugs=['melon', 'genie', 'bugs', 'mnet'])['realtime']
    keys = ['kchart', 'melon', 'genie', 'mnet', 'bugs']
    html = '''
<table class="table table-bordered">
  <thead>
    <tr>
      <th class="col-sm-2"></th>
      <th>kchart.io</th>
      <th>Melon</th>
      <th>Genie</th>
      <th>Mnet</th>
      <th>Bugs!</th>
    </tr>
  </thead>
  <tbody>
    {}
    {}
    {}
    {}
  </tbody>
</table>'''.format(
        _realtime_row(
            'Current position',
            'Current realtime chart position',
            [details[k].get('current_position') for k in keys]
        ),
        _realtime_row_timestamp(
            'Initial position',
            'Initial position and time that this song first entered chart',
            [details[k].get('initial_position') for k in keys],
            [details[k].get('initial_timestamp') for k in keys]
        ),
        _realtime_row_timestamp(
            'Peak position',
            'Peak (best ranked) position and time that this first reached that position',
            [details[k].get('peak_position') for k in keys],
            [details[k].get('peak_timestamp') for k in keys]
        ),
        _realtime_row_timestamp(
            'Final position',
            ('Final position and date that this song last charted '
             '(this is the same as current if the song is still charting)'),
            [details[k].get('final_position') for k in keys],
            [details[k].get('final_timestamp') for k in keys]
        ),
    )
    return mark_safe(html)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
