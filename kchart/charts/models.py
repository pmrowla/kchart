# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from datetime import timedelta
import pickle

from django.core.cache import cache
from django.db import models
from django.db.models import (
    ExpressionWrapper,
    F,
    Min,
    Sum,
)
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _

from .utils import utcnow, strip_to_hour, KR_TZ


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
        return '{} - {}'.format(self.artist_names, self.name)

    @property
    def artist_names(self):
        artists = self.artists.all()
        if len(artists) <= 2:
            sep = '& '
        else:
            sep = ', '
        return sep.join(str(artist) for artist in artists)

    def get_peak_realtime_position(self, service=None):
        if service:
            q = HourlySongChartEntry.objects.filter(hourly_chart__chart__service=service)
        else:
            q = AggregateHourlySongChartEntry.objects
        q = q.filter(song=self, position__lte=100)
        position = q.aggregate(Min('position'))['position__min']
        if position:
            timestamp = q.filter(position=position).aggregate(
                Min('hourly_chart__hour')
            )['hourly_chart__hour__min']
            return (position, timestamp)
        else:
            raise Song.HasNotCharted()

    def get_current_realtime_position(self, service=None):
        if service:
            q = HourlySongChartEntry.objects.filter(hourly_chart__chart__service=service)
        else:
            q = AggregateHourlySongChartEntry.objects
        try:
            entry = q.get(song=self, hourly_chart__hour=strip_to_hour(utcnow()))
            if entry.position > 100:
                return None
            else:
                return entry.position
        except ObjectDoesNotExist:
            return None

    def get_initial_realtime_position(self, service=None):
        if service:
            q = HourlySongChartEntry.objects.filter(hourly_chart__chart__service=service)
        else:
            q = AggregateHourlySongChartEntry.objects
        try:
            entry = q.filter(song=self, position__lte=100).earliest('hourly_chart__hour')
            return (entry.position, entry.hourly_chart.hour)
        except ObjectDoesNotExist:
            raise Song.HasNotCharted()

    def get_final_realtime_position(self, service=None):
        if service:
            q = HourlySongChartEntry.objects.filter(hourly_chart__chart__service=service)
        else:
            q = AggregateHourlySongChartEntry.objects
        try:
            entry = q.filter(song=self, position__lte=100).latest('hourly_chart__hour')
            return (entry.position, entry.hourly_chart.hour)
        except ObjectDoesNotExist:
            raise Song.HasNotCharted()

    def get_realtime_details(self, service=None):
        try:
            details = {'has_charted': True}
            (initial_position, initial_timestamp) = self.get_initial_realtime_position(service)
            (peak_position, peak_timestamp) = self.get_peak_realtime_position(service)
            current_position = self.get_current_realtime_position(service)
            details['initial_position'] = initial_position
            details['initial_timestamp'] = initial_timestamp
            details['peak_position'] = peak_position
            details['peak_timestamp'] = peak_timestamp
            details['current_position'] = current_position
            if not current_position:
                (final_position, final_timestamp) = self.get_final_realtime_position(service)
                details['final_position'] = final_position
                details['final_timestamp'] = final_timestamp
            return details
        except Song.HasNotCharted:
            return {'has_charted': False}

    def get_chart_details(self, include_service_slugs=[]):
        realtime_details = {
            'kchart': self.get_realtime_details(),
        }
        for slug in include_service_slugs:
            try:
                service = MusicService.objects.get(slug=slug)
                realtime_details[slug] = self.get_realtime_details(service)
            except MusicService.DoesNotExist:
                # ignore invalid query params
                pass
        return {'realtime': realtime_details}

    class HasNotCharted(Exception):
        pass


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
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='service_songs')
    service = models.ForeignKey(MusicService, on_delete=models.CASCADE)
    service_song_id = models.IntegerField()

    class Meta:
        unique_together = (('service', 'song'), ('service', 'service_song_id'))

    @property
    def url(self):
        return self.service.get_song_url(self.service_song_id)


class UnknownServiceSong(models.Model):
    '''Table for songs that need to be manually added to the db'''
    service = models.ForeignKey(MusicService, on_delete=models.CASCADE)
    service_song_id = models.IntegerField()

    class Meta:
        unique_together = (('service', 'service_song_id'))


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

    def __str__(self):
        return '{} <{}>'.format(self.chart.name, self.hour.astimezone(KR_TZ).strftime('%Y.%m.%d-%H'))

    class Meta:
        unique_together = ('chart', 'hour')
        ordering = ['-hour', 'chart']

    def update_next_chart(self):
        try:
            next_chart = HourlySongChart.objects.get(chart=self.chart, hour=self.hour + timedelta(hours=1))
            for entry in next_chart.entries.all():
                entry.update_prev_position()
        except HourlySongChart.DoesNotExist:
            pass


class HourlySongChartBacklog(models.Model):

    chart = models.OneToOneField(Chart, on_delete=models.CASCADE, related_name='hourly_backlog')
    next_backlog_timestamp = models.DateTimeField(
        _('Time from which to start the next backlog operation'),
        auto_now_add=True
    )
    last_modified = models.DateTimeField(auto_now=True)

    def find_next_hour_to_backlog(self):
        hour = strip_to_hour(self.next_backlog_timestamp)
        try:
            while HourlySongChart.objects.get(chart=self.chart, hour=hour):
                hour = hour - timedelta(hours=1)
        except HourlySongChart.DoesNotExist:
            pass
        if self.next_backlog_timestamp != hour:
            self.next_backlog_timestamp = hour
            self.save()
        return hour


class BaseHourlySongChartEntry(models.Model):

    song = models.ForeignKey(Song, on_delete=models.CASCADE)
    position = models.SmallIntegerField(_('Chart position'))
    prev_position = models.SmallIntegerField(_('Previous chart position'), null=True, default=None)

    class Meta:
        abstract = True

    @classmethod
    def update_all_prev_positions(cls):
        for entry in cls.objects.all():
            entry.update_prev_position()


class HourlySongChartEntry(BaseHourlySongChartEntry):

    hourly_chart = models.ForeignKey(HourlySongChart, on_delete=models.CASCADE, related_name='entries')

    class Meta:
        unique_together = (('hourly_chart', 'song'), ('hourly_chart', 'position'))
        ordering = ['hourly_chart', 'position']

    def update_prev_position(self):
        try:
            prev_entry = HourlySongChartEntry.objects.get(
                hourly_chart__hour=self.hourly_chart.hour - timedelta(hours=1),
                hourly_chart__chart=self.hourly_chart.chart,
                song=self.song
            )
            if prev_entry.position > 100:
                self.prev_position = None
            else:
                self.prev_position = prev_entry.position
        except HourlySongChartEntry.DoesNotExist:
            self.prev_position = None
        self.save()


class AggregateHourlySongChartEntry(BaseHourlySongChartEntry):

    hourly_chart = models.ForeignKey('AggregateHourlySongChart', on_delete=models.CASCADE, related_name='entries')
    score = models.FloatField(_('Aggregated song score'), default=0.0)

    class Meta:
        unique_together = (('hourly_chart', 'song'), ('hourly_chart', 'position'))
        ordering = ['hourly_chart', 'position']

    def update_prev_position(self):
        try:
            prev_entry = AggregateHourlySongChartEntry.objects.get(
                hourly_chart__hour=self.hourly_chart.hour - timedelta(hours=1),
                song=self.song
            )
            if prev_entry.position > 100:
                self.prev_position = None
            else:
                self.prev_position = prev_entry.position
        except AggregateHourlySongChartEntry.DoesNotExist:
            self.prev_position = None
        self.save()


class AggregateHourlySongChart(models.Model):

    charts = models.ManyToManyField(HourlySongChart)
    hour = models.DateTimeField(_('Chart start hour'), unique=True)

    class Meta:
        ordering = ['-hour']

    def __str__(self):
        return '{} <{}>'.format(self.name, self.hour.astimezone(KR_TZ).strftime('%Y.%m.%d-%H'))

    @property
    def name(self):
        return _('kchart.io aggregated realtime chart')

    @property
    def component_charts(self):
        component_charts = []
        for c in self.charts.all():
            component_charts.append(c.chart)
        return component_charts

    def update_next_chart(self):
        try:
            next_chart = AggregateHourlySongChart.objects.get(hour=self.hour + timedelta(hours=1))
            for entry in next_chart.entries.all():
                entry.update_prev_position()
            if cache.get(self.get_cache_key(self.hour)):
                # only bother with caching the next chart if it was already
                # cached to begin with
                self.cache_chart(next_chart.hour)
        except AggregateHourlySongChart.DoesNotExist:
            pass

    @classmethod
    def get_cache_key(cls, hour):
        hour = strip_to_hour(hour)
        return 'charts-realtime-{}'.format(hour.astimezone(KR_TZ).strftime('%Y%m%d%H'))

    @classmethod
    def cache_chart(cls, hour):
        '''Caches the chart for the specified hour and then returns it'''
        hour = strip_to_hour(hour)
        key = cls.get_cache_key(hour)
        try:
            chart = AggregateHourlySongChart.objects.prefetch_related(
                'entries__song__album',
                'entries__song__artists',
                'charts__entries__song__album',
                'charts__entries__song__artists',
                'charts__chart__service',
            ).order_by('entries__position').get(
                hour=hour
            )
        except AggregateHourlySongChart.DoesNotExist:
            cache.delete(key)
            return None
        pickle_str = pickle.dumps(chart)
        cache.set(key, pickle_str, None)
        return chart

    @classmethod
    def get_cached_chart(cls, hour):
        hour = strip_to_hour(hour)
        key = cls.get_cache_key(hour)
        pickle_str = cache.get(key)
        if pickle_str:
            return pickle.loads(pickle_str)
        else:
            return cls.cache_chart(hour)

    @classmethod
    def generate(cls, hour=utcnow(), regenerate=False, cache_result=True):
        '''Generate an aggregate hourly chart'''
        hour = strip_to_hour(hour)
        if regenerate:
            cache.delete(cls.get_cache_key(hour))
        aggregate_charts = HourlySongChart.objects.filter(hour=hour)
        (chart, created) = AggregateHourlySongChart.objects.get_or_create(
            hour=hour
        )
        if not created:
            if regenerate:
                for entry in chart.entries.all():
                    entry.delete()
            else:
                cls.cache_chart(hour)
                return chart
        total_weight = HourlySongChart.objects.filter(
            hour=hour
        ).aggregate(Sum('chart__weight'))['chart__weight__sum']
        if not total_weight:
            # No charts to aggregate
            return None
        entries = HourlySongChartEntry.objects.filter(
            hourly_chart__hour=hour
        ).values('song').annotate(
            score=Sum(
                ExpressionWrapper(
                    101 - F('position'),
                    output_field=models.FloatField()
                ) * F('hourly_chart__chart__weight')
            ) / (100.0 * total_weight)
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
            new_entry.update_prev_position()
        chart.charts.clear()
        for c in aggregate_charts.all():
            chart.charts.add(c)
        chart.save()
        chart.update_next_chart()
        if cache_result:
            cls.cache_chart(hour)
        else:
            # if we aren't going to cache it make sure we invalidate any
            # existing cache entry
            cache.delete(cls.get_cache_key(hour))
        return chart
