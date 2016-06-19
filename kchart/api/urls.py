# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url

from .views import (
    AggregateHourlySongChartViewSet,
    HourlySongChartViewSet,
    SongViewSet,
)


aggregate_hourly_song_chart_detail = AggregateHourlySongChartViewSet.as_view({'get': 'retrieve'})
hourly_song_chart_detail = HourlySongChartViewSet.as_view({'get': 'retrieve'})
song_detail = SongViewSet.as_view({'get': 'retrieve'})

urlpatterns = [
    url(r'^charts/realtime/$', aggregate_hourly_song_chart_detail, name='realtime'),
    url(r'^charts/realtime/(?P<slug>.+)/$', hourly_song_chart_detail, name='realtime-service'),
    url(r'^songs/(?P<pk>\d+)/$', song_detail, name='song-detail'),
]
