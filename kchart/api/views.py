# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from datetime import datetime

from rest_framework.exceptions import NotFound
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.viewsets import GenericViewSet

from ..charts.models import (
    AggregateHourlySongChart,
    HourlySongChart,
    MusicService
)
from ..charts.serializers import (
    HourlySongChartSerializer,
    AggregateHourlySongChartSerializer
)
from ..charts.utils import KR_TZ


class HourlySongChartViewSet(ListModelMixin, GenericViewSet):
    '''Viewset for viewing hourly song charts'''

    serializer_class = HourlySongChartSerializer

    def get_queryset(self):
        q = HourlySongChart.objects
        if 'slug' in self.kwargs:
            try:
                service = MusicService.objects.get(slug=self.kwargs['slug'])
                q = q.filter(chart__service=service)
            except MusicService.DoesNotExist:
                raise NotFound('No such music service')
        else:
            service = MusicService.objects.get(slug='melon')
        hour_str = self.request.query_params.get('hour', None)
        if hour_str:
            try:
                hour = KR_TZ.localize(datetime.strptime(hour_str, '%Y%m%d%H'))
            except ValueError:
                raise NotFound('Invalid hour parameter')
        else:
            hour = HourlySongChart.objects.filter(chart__service=service).first().hour
        q = HourlySongChart.objects.filter(hour=hour)
        return q.all()


class AggregateHourlySongChartViewSet(RetrieveModelMixin, GenericViewSet):
    '''Viewset for viewing hourly song charts'''

    serializer_class = AggregateHourlySongChartSerializer
    lookup_field = 'hour'

    def get_object(self):
        q = AggregateHourlySongChart.objects
        hour_str = self.request.query_params.get('hour', None)
        if hour_str:
            try:
                hour = KR_TZ.localize(datetime.strptime(hour_str, '%Y%m%d%H'))
            except ValueError:
                raise NotFound('Invalid hour parameter')
            q = q.filter(hour=hour)
        return q.first()
