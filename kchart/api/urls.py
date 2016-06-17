# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url

from .views import HourlySongChartViewSet


hourly_song_chart_list = HourlySongChartViewSet.as_view({
    'get': 'list',
})

urlpatterns = [
    url(r'^charts/realtime/$', hourly_song_chart_list, name='realtime'),
    url(r'^charts/realtime/(?P<slug>\w+)/$', hourly_song_chart_list, name='realtime-service'),
]
