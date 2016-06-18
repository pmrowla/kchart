# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from celery import shared_task

from .chartservice import (
    GenieChartService,
    MelonChartService,
)
from .models import AggregateHourlySongChart


@shared_task
def aggregate_hourly_chart():
    AggregateHourlySongChart.generate(regenerate=True)


@shared_task
def update_genie_hourly_chart():
    genie = GenieChartService()
    genie.fetch_hourly()
    aggregate_hourly_chart.delay()


@shared_task
def update_melon_hourly_chart():
    melon = MelonChartService()
    melon.fetch_hourly()
    update_genie_hourly_chart.delay()
