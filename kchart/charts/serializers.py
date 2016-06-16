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

    artists = ArtistSerializer(many=True)

    class Meta:
        model = Album
        fields = ('id', 'name', 'artists', 'release_date')


class AlbumTitleSerializer(serializers.ModelSerializer):

    class Meta:
        model = Album
        fields = ('id', 'name')


class SongSerializer(serializers.ModelSerializer):

    artists = ArtistSerializer(many=True)
    album = AlbumTitleSerializer()

    class Meta:
        model = Song
        fields = ('id', 'name', 'artists', 'album', 'release_date')
        depth = 1


class MusicServiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = MusicService
        fields = ('name', 'url')


class ChartSerializer(serializers.ModelSerializer):

    class Meta:
        model = Chart
        fields = ('name', 'url')


class HourlySongChartEntrySerializer(serializers.ModelSerializer):

    song = SongSerializer()

    class Meta:
        model = HourlySongChartEntry
        fields = ('position', 'song')
        depth = 1


class AggregateChartEntrySerializer(serializers.Serializer):

    song = SongSerializer()
    total_score = serializers.FloatField()


class HourlySongChartSerializer(serializers.ModelSerializer):

    chart = ChartSerializer()
    entries = HourlySongChartEntrySerializer(many=True)

    class Meta:
        model = HourlySongChart
        fields = ('chart', 'hour', 'entries')
