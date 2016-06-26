# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from datetime import datetime

from django.contrib import messages
from django.db.models import Count
from django.views.generic import (
    DetailView,
    TemplateView,
)

from .models import (
    AggregateHourlySongChart,
    HourlySongChart,
    HourlySongChartEntry,
    Song,
)
from .utils import KR_TZ


class HourlySongChartView(DetailView):

    template_name = 'charts/hourlysongchart_detail.html'

    def _get_hour(self, msg=False):
        chart_date = self.request.GET.get('date', None)
        if chart_date:
            try:
                hour = self.request.GET.get('hour', '00')
                return KR_TZ.localize(datetime.strptime('{}{}'.format(chart_date, hour), '%Y%m%d%H'))
            except ValueError:
                if msg:
                    messages.error(self.request, 'Invalid date/hour parameters.')
        return AggregateHourlySongChart.objects.latest('hour').hour.astimezone(KR_TZ)

    def get_context_data(self, **kwargs):
        context = super(HourlySongChartView, self).get_context_data(**kwargs)
        context['hour'] = self._get_hour()
        return context

    def get_object(self):
        hour = self._get_hour(msg=True)
        return AggregateHourlySongChart.get_cached_chart(hour)


class StatsView(TemplateView):

    template_name = 'charts/stats.html'

    def get_context_data(self, **kwargs):
        context = super(StatsView, self).get_context_data(**kwargs)
        for slug in ['melon', 'genie', 'bugs', 'mnet']:
            context['{}_earliest'.format(slug)] = HourlySongChart.objects.filter(
                chart__service__slug=slug).earliest('hour').hour
        context['song_count'] = HourlySongChartEntry.objects.aggregate(
            song_count=Count('song', distinct=True))['song_count']
        context['artist_count'] = HourlySongChartEntry.objects.aggregate(
            artist_count=Count('song__artists', distinct=True))['artist_count']
        context['album_count'] = HourlySongChartEntry.objects.aggregate(
            album_count=Count('song__album', distinct=True))['album_count']
        return context
