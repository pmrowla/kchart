# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from datetime import datetime, date

from lxml.html import fromstring
from pytz import timezone, utc
import requests
import sys

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

from .models import (
    Artist,
    Album,
    Song,
    MusicService,
    MusicServiceArtist,
    MusicServiceAlbum,
    MusicServiceSong,
    Chart,
    HourlySongChart,
    HourlySongChartEntry,
)


KR_TZ = timezone('Asia/Seoul')


def strip_to_hour(time):
    '''Strip minutes/seconds from a datetime object'''
    return datetime(time.year, time.month, time.day, time.hour, tzinfo=time.tzinfo)


def melon_hour(day, hour):
    '''Return a datetime object from the melon formatted day and hour parameters'''
    return KR_TZ.localize(datetime.strptime('{} {}'.format(day, hour), '%Y%m%d %H'))


class BaseChartService(object):
    '''Abstract chart service class'''

    NAME = None
    URL = ''
    ARTIST_URL = '{artist_id}'
    ALBUM_URL = '{album_id}'
    SONG_URL = '{song_id}'

    def __init__(self):
        if not self.NAME:
            raise NotImplementedError('BaseChartService.NAME field must be overridden')
        self.service = self._get_or_create()

    def _get_or_create(self, force_update=False):
        '''Get or create this MusicService object

        :param bool force_update: True if the row for this service should be updated
        :rtype MusicService
        '''
        defaults = {
            'url': self.NAME,
            '_artist_url': self.ARTIST_URL,
            '_album_url': self.ALBUM_URL,
            '_song_url': self.SONG_URL,
        }

        (service, created) = MusicService.objects.get_or_create(name=self.NAME, defaults=defaults)
        if force_update:
            service.update(defaults)
            service.save()
        return service

    def fetch_hourly(self, hour=None, dry_run=False, *args, **kwargs):
        '''Fetch the specified hourly chart for this service and update the relevant table

        :param datetime hour: The specific (tz aware) hour to update. If no hour is specified, the current live chart
            will be fetched.
        :param bool dry_run: True if the chart data should not be written to the database.
        '''
        raise NotImplementedError


class MelonChartService(BaseChartService):

    NAME = 'Melon'
    URL = 'http://www.melon.com'
    ARTIST_URL = 'http://www.melon.com/artist/detail.htm?artistId={artist_id}'
    ALBUM_URL = 'http://www.melon.com/album/detail.htm?albumId={album_id}'
    SONG_URL = 'http://www.melon.com/song/detail.htm?songId={song_id}'

    def __init__(self):
        super(MelonChartService, self).__init__()
        (self.hourly_chart, created) = Chart.objects.get_or_create(
            service=self.service,
            defaults={
                'name': 'Melon realtime top 100',
                'url': 'http://www.melon.com/chart/index.htm',
                'weight': 6.0,  # the instiz weight for melon is 6x (50% of potential points)
            }
        )

    def get_artist_from_melon(self, melon_id, defaults=None):
        try:
            melon_artist = MusicServiceArtist.objects.get(service=self.service, service_artist_id=melon_id)
            return melon_artist.artist
        except ObjectDoesNotExist:
            if defaults:
                artist_info = defaults
            else:
                artist_info = self._scrape_artist_info(melon_id)
            artist = Artist.objects.create(name=artist_info['name'], debut_date=artist_info['debut_date'])
            artist.save()
            melon_artist = MusicServiceArtist.objects.create(
                artist=artist,
                service=self.service,
                service_artist_id=melon_id
            )
            melon_artist.save()
            return artist

    def get_album_from_melon(self, melon_id, defaults=None):
        try:
            melon_album = MusicServiceAlbum.objects.get(service=self.service, service_album_id=melon_id)
            return melon_album.album
        except ObjectDoesNotExist:
            if not defaults:
                raise NotImplementedError('Melon album detail scraper not implemented')
            album = Album.objects.create(
                name=defaults['name'],
                release_date=defaults['release_date']
            )
            for artist in defaults['artists']:
                album.artists.add(artist)
            album.save()
            melon_album = MusicServiceAlbum.objects.create(
                album=album,
                service=self.service,
                service_album_id=melon_id
            )
            melon_album.save()
            return album

    def get_song_from_melon(self, melon_id, defaults=None):
        try:
            melon_song = MusicServiceSong.objects.get(service=self.service, service_song_id=melon_id)
            return melon_song.song
        except ObjectDoesNotExist:
            if not defaults:
                raise NotImplementedError('Melon song detail scraper not implemented')
            song = Song.objects.create(
                name=defaults['name'],
                album=defaults['album'],
                release_date=defaults['release_date']
            )
            for artist in defaults['artists']:
                song.artists.add(artist)
            song.save()
            melon_song = MusicServiceSong.objects.create(
                song=song,
                service=self.service,
                service_song_id=melon_id
            )
            melon_song.save()
            return song

    def _scrape_artist_info(self, melon_id):
        artist_info = {'melon_id': melon_id, 'debut_date': None}
        url = self.ARTIST_URL.format(artist_id=melon_id)
        r = requests.get(url)
        r.raise_for_status()
        html = fromstring(r.text)
        title = html.find_class('title_atist')
        if len(title) != 1:
            raise RuntimeError('Got unexpected melon artist detail HTML')
        artist_info['name'] = title[0][0].tail.strip()
        artist_infos = html.find_class('section_atistinfo03')
        if len(artist_infos) != 1:
            raise RuntimeError('Got unexpected melon artist detail HTML')
        info_list = artist_infos[0].find_class('list_define')[0]
        if info_list[0].text.strip() == '데뷔' and info_list[1].tag == 'dd':
            if 'debut_song' in info_list[1].classes:
                debut_str = info_list[1].text_content().split('|')[0].strip()
            else:
                debut_str = info_list[1].text.strip()
            if debut_str:
                parts = debut_str.split('.')
                year = int(parts[0])
                if len(parts) > 1:
                    month = int(parts[1])
                else:
                    month = 1
                if len(parts) > 2:
                    day = int(parts[2])
                else:
                    day = 1
                artist_info['debut_date'] = date(year, month, day)
        return artist_info

    def fetch_hourly(self, hour=None, dry_run=False, force_update=False, cmd=None, verbosity=1):
        if cmd:
            stdout = cmd.stdout
        else:
            stdout = sys.stdout
        if hour:
            raise ValueError(
                'Melon does not allow historical hourly chart data to be retrieved. '
                'Only live hourly Melon chart data can be fetched.'
            )
        hour = strip_to_hour(datetime.now(utc))
        if not force_update:
            try:
                chart = HourlySongChart.objects.get(chart=self.hourly_chart, hour=hour)
                if chart and chart.entries.count():
                    if cmd:
                        cmd.stdout.write('Already fetched this chart')
                    return
            except ObjectDoesNotExist:
                pass
            except MultipleObjectsReturned:
                pass
        url = 'http://apis.skplanetx.com/melon/charts/realtime'
        params = {
            'version': 1,
            'page': 1,
            'count': 100,
        }
        headers = {'Accept': 'application/json', 'appKey': settings.MELON_APP_KEY}
        r = requests.get(url, params=params, headers=headers)
        r.raise_for_status()
        melon_data = r.json()['melon']
        if melon_data['count'] != 100:
            raise ValueError('Melon returned unexpected number of chart entries: {}'.format(melon_data['count']))
        rank_hour = melon_hour(melon_data['rankDay'], melon_data['rankHour'])
        if verbosity:
            stdout.write('Fetched melon realtime chart for {}'.format(rank_hour))
        if dry_run:
            return
        (hourly_song_chart, created) = HourlySongChart.objects.get_or_create(chart=self.hourly_chart, hour=rank_hour)
        if not created and hourly_song_chart.entries.count():
            if verbosity:
                stdout.write('Already fetched this chart')
            return
        for song_data in melon_data['songs']['song']:
            release_date = datetime.strptime(song_data['issueDate'], '%Y%m%d').date()
            artists = []
            for artist_data in song_data['artists']['artist']:
                artists.append(self.get_artist_from_melon(artist_data['artistId']))
            defaults = {
                'name': song_data['albumName'],
                'artists': artists,
                'release_date': release_date,
            }
            album = self.get_album_from_melon(song_data['albumId'], defaults=defaults)
            defaults['name'] = song_data['songName']
            defaults['album'] = album
            song = self.get_song_from_melon(song_data['songId'], defaults=defaults)
            defaults = {'position': song_data['currentRank']}
            (chart_entry, created) = HourlySongChartEntry.objects.get_or_create(
                hourly_chart=hourly_song_chart,
                song=song,
                defaults=defaults
            )
            if not created and chart_entry.position != song_data['currentRank']:
                chart_entry.position = song_data['currentRank']
                chart_entry.save()
        if verbosity:
            stdout.write('Wrote melon realtime chart for {} to database'.format(rank_hour))


# Add chart services to process here
CHART_SERVICES = {
    'melon': MelonChartService
}
