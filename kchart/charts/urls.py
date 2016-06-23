# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url
from django.views.decorators.cache import cache_page
from django.views.generic.base import RedirectView

from . import views

urlpatterns = [
    url(r'^$', RedirectView.as_view(url='/charts/realtime/')),
    url(
        regex=r'^realtime/$',
        view=cache_page(60 * 5)(views.HourlySongChartView.as_view()),
        name='hourly-chart-list'
    ),
]
