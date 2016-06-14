# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from rest_framework import serializers

from .models import (
    Artist,
    Album,
    Song,
    MusicService,
    Chart,
    HourlySongChart,
    HourlySongChartEntry,
)


class ArtistSerializer(serializers.ModelSerializer):

    class Meta:
        model = Artist
        fields = ('id', 'name', 'debut_date')


class AlbumSerializer(serializers.ModelSerializer):

    class Meta:
        model = Album
        fields = ('id', 'name', 'artist', 'release_date')


class SongSerializer(serializers.ModelSerializer):

    class Meta:
        model = Song
        fields = ('id', 'name', 'artist', 'album', 'release_date')
        depth = 1   # Don't re-serialize album.artist


class MusicServiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = MusicService
        fields = ('name', 'url')


class ChartSerializer(serializers.ModelSerializer):

    class Meta:
        model = Chart
        fields = ('service', 'name', 'url', 'weight')


class HourlySongChartSerializer(serializers.ModelSerializer):

    class Meta:
        model = HourlySongChart
        fields = ('chart', 'hour', 'entries')


class HourlySongChartEntrySerializer(serializers.ModelSerializer):

    class Meta:
        model = HourlySongChartEntry
        fields = ('hourly_chart', 'position', 'song')
