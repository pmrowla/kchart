# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url
from django.views.generic.base import RedirectView

from . import views

urlpatterns = [
    url(r'^$', RedirectView.as_view(url='/charts/realtime/')),
    url(
        regex=r'^realtime/$',
        view=views.HourlySongChartView.as_view(),
        name='hourly-chart-list'
    ),
]