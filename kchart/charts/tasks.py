# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from celery import shared_task, chord

from .chartservice import (
    BugsChartService,
    GenieChartService,
    MelonChartService,
    MnetChartService,
)
from .models import AggregateHourlySongChart
from .utils import utcnow


@shared_task
def aggregate_hourly_chart(hour=utcnow()):
    return AggregateHourlySongChart.generate(hour=hour, regenerate=True)


@shared_task
def update_bugs_hourly_chart(hour=utcnow()):
    bugs = BugsChartService()
    return bugs.fetch_hourly(hour)


@shared_task
def update_mnet_hourly_chart(hour=utcnow()):
    mnet = MnetChartService()
    return mnet.fetch_hourly(hour)


@shared_task
def update_genie_hourly_chart(hour=utcnow()):
    genie = GenieChartService()
    return genie.fetch_hourly(hour)


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
