# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from datetime import timedelta

from celery import shared_task, chord
from requests.exceptions import ConnectionError, ConnectTimeout

from .chartservice import (
    BugsChartService,
    GenieChartService,
    MelonChartService,
    MnetChartService,
)
from .models import AggregateHourlySongChart, HourlySongChart
from .utils import utcnow, strip_to_hour


@shared_task
def aggregate_hourly_chart(hour=utcnow()):
    return AggregateHourlySongChart.generate(hour=hour, regenerate=True)


@shared_task
def aggregate_all_hourly_charts():
    '''Re-aggregate everything

    This task should only be run when the aggregation algorithm changes
    '''
    start = HourlySongChart.objects.latest('hour').hour
    end = HourlySongChart.objects.earliest('hour').hour
    h = start
    while h >= end:
        aggregate_hourly_chart.delay(h)
        h = h - timedelta(hours=1)


@shared_task
def update_hourly_chart(chart_service, hour=utcnow(), **kwargs):
    svc = chart_service()
    try:
        return svc.fetch_hourly(hour)
    except (ConnectionError, ConnectTimeout) as exc:
        raise update_hourly_chart.retry(args=[chart_service], hour=hour, exc=exc, kwargs=kwargs)


@shared_task
def update_dependent_hourly_charts(hour=utcnow()):
    chord([
        update_hourly_chart.s(GenieChartService, hour=hour),
        update_hourly_chart.s(MnetChartService, hour=hour),
        update_hourly_chart.s(BugsChartService, hour=hour),
    ])(aggregate_hourly_chart.si(hour))


@shared_task
def update_melon_hourly_chart():
    melon = MelonChartService()
    result = melon.fetch_hourly()
    update_dependent_hourly_charts.delay(result.hour)
    return result


@shared_task
def backlog_hourly_range(start_hour=utcnow(), delta=timedelta(hours=23)):
    '''Fill hourly chart backlog, working backwards from [start_hour, (start_hour - delta)]

    :param datetime start_hour: timestamp from which to begin the backlog operation
    :param timedelta delta: the amount of time to backlog

    Chart updates will be spaced at least 30 seconds apart to avoid spamming requests
    '''
    hour = strip_to_hour(start_hour)
    end_hour = start_hour - delta
    countdown = 30
    while hour >= end_hour:
        update_dependent_hourly_charts.apply_async((hour,), countdown=countdown)
        countdown += 30
        hour = hour - timedelta(hours=1)


@shared_task
def refetch_incomplete():
    for chart_service in [
        BugsChartService,
        GenieChartService,
        MnetChartService,
    ]:
        svc = chart_service()
        countdown = 0
        for chart in svc.get_incomplete():
            (
                update_hourly_chart.s(chart_service, chart.hour) |
                aggregate_hourly_chart.si(chart.hour)
            ).apply_async(countdown=countdown)
            countdown += 30
