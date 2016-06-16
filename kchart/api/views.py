# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from datetime import datetime

from rest_framework.exceptions import NotFound
from rest_framework.mixins import ListModelMixin
from rest_framework.viewsets import GenericViewSet

from ..charts.models import HourlySongChart, MusicService
from ..charts.serializers import HourlySongChartSerializer
from ..charts.utils import KR_TZ, utcnow, strip_to_hour


class HourlySongChartViewSet(ListModelMixin, GenericViewSet):
    '''Viewset for viewing hourly song charts'''

    serializer_class = HourlySongChartSerializer

    def get_queryset(self):
        if 'slug' in self.kwargs:
            service = MusicService.objects.filter(slug=self.kwargs['slug']).first()
            if not service:
                raise NotFound('No such music service')
        else:
            service = None
        hour_str = self.request.query_params.get('hour', None)
        if hour_str:
            try:
                hour = KR_TZ.localize(datetime.strptime(hour_str, '%Y%m%d%H'))
            except ValueError:
                raise NotFound('Invalid hour parameter')
        else:
            hour = strip_to_hour(utcnow())
        q = HourlySongChart.objects.filter(hour=hour)
        if service:
            q = q.filter(chart__service=service)
        return q.all()
