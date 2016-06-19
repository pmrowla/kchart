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
    AggregateHourlySongChart,
    AggregateHourlySongChartEntry,
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


class SongDetailSerializer(serializers.ModelSerializer):

    artists = ArtistSerializer(many=True)
    album = AlbumTitleSerializer()
    chart_details = serializers.SerializerMethodField()

    class Meta:
        model = Song
        fields = ('id', 'name', 'artists', 'album', 'release_date', 'chart_details')

    def get_chart_details(self, song):
        include_service_slugs = self.context.get('include_service_slugs', [])
        return song.get_chart_details(include_service_slugs)


class MusicServiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = MusicService
        fields = ('name', 'url')


class ChartSerializer(serializers.ModelSerializer):

    class Meta:
        model = Chart
        fields = ('name', 'url')


class AggregateChartSerializer(serializers.ModelSerializer):

    weight = serializers.FloatField()

    class Meta:
        model = Chart
        fields = ('name', 'url', 'weight')


class HourlySongChartEntrySerializer(serializers.ModelSerializer):

    song = SongSerializer()
    prev_position = serializers.IntegerField()

    class Meta:
        model = HourlySongChartEntry
        fields = ('song', 'position', 'prev_position')


class AggregateChartEntrySerializer(serializers.ModelSerializer):

    song = SongSerializer()
    prev_position = serializers.IntegerField()

    class Meta:
        model = AggregateHourlySongChartEntry
        fields = ('song', 'score', 'position', 'prev_position')


class HourlySongChartSerializer(serializers.ModelSerializer):

    chart = ChartSerializer()
    entries = HourlySongChartEntrySerializer(many=True)

    class Meta:
        model = HourlySongChart
        fields = ('chart', 'hour', 'entries')


class AggregateHourlySongChartSerializer(serializers.ModelSerializer):

    component_charts = AggregateChartSerializer(many=True)
    entries = serializers.SerializerMethodField()

    class Meta:
        model = AggregateHourlySongChart
        fields = ('name', 'component_charts', 'hour', 'entries')

    def get_entries(self, hourly_chart):
        entries = AggregateHourlySongChartEntry.objects.filter(hourly_chart=hourly_chart)[:100]
        serializer = AggregateChartEntrySerializer(instance=entries, many=True)
        return serializer.data
