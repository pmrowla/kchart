# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from rest_framework import generics

from .models import HourlySongChart
from .serializers import HourlySongChartSerializer


class HourlySongChartList(generics.ListAPIView):
    queryset = HourlySongChart.objects.all()
    serializer_class = HourlySongChartSerializer
