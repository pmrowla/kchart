# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from datetime import datetime

from django.contrib import messages
from django.views.generic import DetailView

from .models import AggregateHourlySongChart
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
