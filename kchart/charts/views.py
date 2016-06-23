# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from datetime import datetime

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.views.generic import ListView

from .models import AggregateHourlySongChart, HourlySongChart
from .utils import KR_TZ


class HourlySongChartView(ListView):

    template_name = 'charts/hourlysongchart_list.html'

    def _get_hour(self, msg=False):
        chart_date = self.request.GET.get('date', None)
        if chart_date:
            try:
                hour = self.request.GET.get('hour', '00')
                return KR_TZ.localize(datetime.strptime('{}{}'.format(chart_date, hour), '%Y%m%d%H'))
            except ValueError:
                if msg:
                    messages.error(self.request, 'Invalid date/hour parameters.')
        return AggregateHourlySongChart.objects.latest('hour').hour

    def get_context_data(self, **kwargs):
        context = super(HourlySongChartView, self).get_context_data(**kwargs)
        context['hour'] = self._get_hour()
        return context

    def get_queryset(self):
        hour = self._get_hour(msg=True)
        try:
            aggregate_q = AggregateHourlySongChart.objects.get(hour=hour)
            service_q = HourlySongChart.objects.filter(hour=aggregate_q.hour).all()
            return [aggregate_q] + list(service_q)
        except ObjectDoesNotExist:
            return []
