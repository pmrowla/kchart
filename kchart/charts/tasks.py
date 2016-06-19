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
from .models import AggregateHourlySongChart
from .utils import utcnow, strip_to_hour


@shared_task
def aggregate_hourly_chart(hour=utcnow()):
    return AggregateHourlySongChart.generate(hour=hour, regenerate=True)


@shared_task
def update_bugs_hourly_chart(hour=utcnow(), **kwargs):
    bugs = BugsChartService()
    try:
        return bugs.fetch_hourly(hour)
    except (ConnectionError, ConnectTimeout) as exc:
        raise update_bugs_hourly_chart.retry(hour=hour, exc=exc, kwargs=kwargs)


@shared_task
def update_mnet_hourly_chart(hour=utcnow(), **kwargs):
    mnet = MnetChartService()
    try:
        return mnet.fetch_hourly(hour)
    except (ConnectionError, ConnectTimeout) as exc:
        raise update_mnet_hourly_chart.retry(hour=hour, exc=exc, kwargs=kwargs)


@shared_task
def update_genie_hourly_chart(hour=utcnow(), **kwargs):
    genie = GenieChartService()
    try:
        return genie.fetch_hourly(hour)
    except (ConnectionError, ConnectTimeout) as exc:
        raise update_genie_hourly_chart.retry(hour=hour, exc=exc, kwargs=kwargs)


@shared_task
def update_dependent_hourly_charts(hour=utcnow()):
    chord([
        update_genie_hourly_chart.s(hour),
        update_mnet_hourly_chart.s(hour),
        update_bugs_hourly_chart.s(hour),
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
