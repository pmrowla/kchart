# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from celery import shared_task

from .chartservice import MelonChartService


@shared_task
def update_melon_hourly_chart():
    melon = MelonChartService()
    melon.fetch_hourly()
