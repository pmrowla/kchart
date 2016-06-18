# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from datetime import timedelta

from django.db import models
from django.db.models import (
    ExpressionWrapper,
    F,
    Sum,
)
from django.utils.translation import ugettext_lazy as _

from .utils import utcnow, strip_to_hour


class Artist(models.Model):

    name = models.CharField(_('Artist name'), blank=True, max_length=255)
    debut_date = models.DateField(_('Artist debut date'), null=True)

    def __str__(self):
        return self.name


class Album(models.Model):

    name = models.CharField(_('Album name'), blank=True, max_length=255)
    artists = models.ManyToManyField(Artist, related_name='albums')
    release_date = models.DateField(_('Album release date'))

    def __str__(self):
        artist_names = []
        for artist in self.artists.all():
            artist_names.append(str(artist))
        return '{} - {}'.format(', '.join(artist_names), self.name)


class Song(models.Model):

    name = models.CharField(_('Song name'), blank=True, max_length=255)
    artists = models.ManyToManyField(Artist, related_name='songs')
    album = models.ForeignKey(Album, on_delete=models.PROTECT, related_name='songs')
    release_date = models.DateField(_('Song release date'))

    def __str__(self):
        artist_names = []
        for artist in self.artists.all():
            artist_names.append(str(artist))
        return '{} - {}'.format(', '.join(artist_names), self.name)


class MusicService(models.Model):
    '''A Korean digital music service'''

    name = models.CharField(_('Music service name'), blank=True, max_length=255)
    url = models.URLField(_('Music service URL'), blank=True)
    _artist_url = models.URLField(_('Base artist URL'), blank=True)
    _album_url = models.URLField(_('Base album URL'), blank=True)
    _song_url = models.URLField(_('Base song URL'), blank=True)
    slug = models.SlugField(_('Slug name'), blank=True)

    def __str__(self):
        return self.name

    def get_artist_url(self, artist_id):
        '''Return the URL for the specified artist page

        :param artist_id: The service-specific artist id
        :rtype: str
        '''
        return self._artist_url.format(artist_id=artist_id)

    def get_album_url(self, album_id):
        '''Return the URL for the specified album page

        :param album_id: The service-specific album id
        :rtype: str
        '''
        return self._album_url.format(album_id=album_id)

    def get_song_url(self, song_id):
        '''Return the URL for the specified album page

        :param album_id: The service-specific album id
        :rtype: str
        '''
        return self._song_url.format(song_id=song_id)


class MusicServiceArtist(models.Model):
    '''Table for mapping Artist ID to a MusicService artist ID'''
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE)
    service = models.ForeignKey(MusicService, on_delete=models.CASCADE)
    service_artist_id = models.IntegerField()

    class Meta:
        unique_together = (('service', 'artist'), ('service', 'service_artist_id'))


class MusicServiceAlbum(models.Model):
    '''Table for mapping Album ID to a MusicService artist ID'''
    album = models.ForeignKey(Album, on_delete=models.CASCADE)
    service = models.ForeignKey(MusicService, on_delete=models.CASCADE)
    service_album_id = models.IntegerField()

    class Meta:
        unique_together = (('service', 'album'), ('service', 'service_album_id'))


class MusicServiceSong(models.Model):
    '''Table for mapping Song ID to a MusicService song ID'''
    song = models.ForeignKey(Song, on_delete=models.CASCADE)
    service = models.ForeignKey(MusicService, on_delete=models.CASCADE)
    service_song_id = models.IntegerField()

    class Meta:
        unique_together = (('service', 'song'), ('service', 'service_song_id'))


class Chart(models.Model):

    service = models.ForeignKey(MusicService, on_delete=models.PROTECT)
    name = models.CharField(_('Chart name'), blank=True, max_length=255)
    url = models.URLField(_('Chart URL'), blank=True)
    weight = models.FloatField(_('Chart aggregation weight'), default=1.0)

    def __str__(self):
        return self.name

    @property
    def slug(self):
        return self.service.slug


class HourlySongChart(models.Model):

    chart = models.ForeignKey(Chart, on_delete=models.CASCADE)
    hour = models.DateTimeField(_('Chart start hour'))

    class Meta:
        unique_together = ('chart', 'hour')
        ordering = ['-hour', 'chart']


class BaseHourlySongChartEntry(models.Model):

    song = models.ForeignKey(Song, on_delete=models.CASCADE)
    position = models.SmallIntegerField(_('Chart position'))

    class Meta:
        abstract = True


class HourlySongChartEntry(BaseHourlySongChartEntry):

    hourly_chart = models.ForeignKey(HourlySongChart, on_delete=models.CASCADE, related_name='entries')

    class Meta:
        unique_together = (('hourly_chart', 'song'), ('hourly_chart', 'position'))
        ordering = ['hourly_chart', 'position']

    @property
    def prev_position(self):
        try:
            prev_entry = HourlySongChartEntry.objects.get(
                hourly_chart__chart=self.hourly_chart.chart,
                hourly_chart__hour=self.hourly_chart.hour - timedelta(hours=1),
                song=self.song
            )
            return prev_entry.position
        except HourlySongChartEntry.DoesNotExist:
            return None


class AggregateHourlySongChartEntry(BaseHourlySongChartEntry):

    hourly_chart = models.ForeignKey('AggregateHourlySongChart', on_delete=models.CASCADE, related_name='entries')
    score = models.FloatField(_('Aggregated song score'), default=0.0)

    class Meta:
        unique_together = (('hourly_chart', 'song'), ('hourly_chart', 'position'))
        ordering = ['hourly_chart', 'position']

    @property
    def prev_position(self):
        try:
            prev_entry = AggregateHourlySongChartEntry.objects.get(
                hourly_chart__hour=self.hourly_chart.hour - timedelta(hours=1),
                song=self.song
            )
            if prev_entry.position > 100:
                return None
            else:
                return prev_entry.position
        except AggregateHourlySongChartEntry.DoesNotExist:
            return None


class AggregateHourlySongChart(models.Model):

    charts = models.ManyToManyField(HourlySongChart)
    hour = models.DateTimeField(_('Chart start hour'), unique=True)

    class Meta:
        ordering = ['-hour']

    @property
    def name(self):
        return _('kchart.io aggregated realtime chart')

    @property
    def component_charts(self):
        component_charts = []
        for c in self.charts.all():
            component_charts.append(c.chart)
        return component_charts

    @classmethod
    def generate(cls, hour=utcnow(), regenerate=False):
        '''Generate an aggregate hourly chart'''
        hour = strip_to_hour(hour)
        aggregate_charts = HourlySongChart.objects.filter(hour=hour)
        (chart, created) = AggregateHourlySongChart.objects.get_or_create(
            hour=hour
        )
        if not created:
            if regenerate:
                for entry in chart.entries.all():
                    entry.delete()
            else:
                return chart
        entries = HourlySongChartEntry.objects.filter(
            hourly_chart__hour=hour
        ).values('song').annotate(
            score=Sum(
                ExpressionWrapper(
                    101 - F('position'),
                    output_field=models.FloatField()
                ) * F('hourly_chart__chart__weight')
            ) / Sum(F('hourly_chart__chart__weight') * 100)
        ).order_by('-score')
        for (i, entry) in enumerate(entries):
            song = Song.objects.get(pk=entry['song'])
            (new_entry, created) = AggregateHourlySongChartEntry.objects.get_or_create(
                hourly_chart=chart,
                song=song,
                defaults={'score': entry['score'], 'position': i + 1},
            )
            if not created:
                new_entry.score = entry['score']
                new_entry.position = i + 1
                new_entry.save()
        chart.charts.clear()
        for c in aggregate_charts.all():
            chart.charts.add(c)
        chart.save()
        return chart
