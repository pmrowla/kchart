# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url

from .views import (
    AggregateHourlySongChartViewSet,
    HourlySongChartViewSet,
)


hourly_song_chart_list = HourlySongChartViewSet.as_view({
    'get': 'list',
})

aggregate_hourly_song_chart_detail = AggregateHourlySongChartViewSet.as_view({
    'get': 'retrieve',
})

urlpatterns = [
    url(r'^charts/realtime/$', aggregate_hourly_song_chart_detail, name='realtime'),
    url(r'^charts/realtime/(?P<slug>\w+)/$', hourly_song_chart_list, name='realtime-service'),
]
