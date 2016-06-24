# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from datetime import datetime, date
import logging
import re

from lxml.html import fromstring
from fake_useragent import UserAgent
import requests

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db.models import Count, F

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
    AggregateHourlySongChart,
)
from .utils import KR_TZ, strip_to_hour, utcnow, melon_hour


logger = logging.getLogger('django')

ua = UserAgent()
REQUESTS_TIMEOUT = 6.05


def randomized_get(url, headers={}, timeout=REQUESTS_TIMEOUT, **kwargs):
    if settings.REQUESTS_HTTP_PROXY:
        proxies = {'http': settings.REQUESTS_HTTP_PROXY, 'https': settings.REQUESTS_HTTP_PROXY}
        timeout = 10 * timeout
    else:
        proxies = {}
    headers.update({'User-Agent': ua.random})
    return requests.get(url, headers=headers, timeout=timeout, proxies=proxies, **kwargs)


class BaseChartService(object):
    '''Abstract chart service class'''

    NAME = None
    URL = ''
    ARTIST_URL = '{artist_id}'
    ALBUM_URL = '{album_id}'
    SONG_URL = '{song_id}'
    SLUG = ''

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
            'slug': self.SLUG,
        }

        (service, created) = MusicService.objects.get_or_create(name=self.NAME, defaults=defaults)
        if force_update:
            service.update(defaults)
            service.save()
        return service

    def fetch_hourly(self, hour=None, dry_run=False, force_update=False):
        '''Fetch the specified hourly chart for this service and update the relevant table

        :param datetime hour: The specific (tz aware) hour to update. If no hour is specified, the current live chart
            will be fetched.
        :param bool dry_run: True if the chart data should not be written to the database.
        :param bool force_update: True if existing chart data should be overwritten
        '''
        raise NotImplementedError

    def get_incomplete(self):
        return HourlySongChart.objects.filter(
            chart__service=self.service
        ).annotate(
            Count(F('entries'))
        ).filter(
            entries__count__lt=100
        ).all()

    def refetch_incomplete(self, dry_run=False):
        '''Re-fetch any incomplete charts for this service'''
        incomplete = self.get_incomplete()
        logger.info('Refetching {} incomplete {} charts'.format(len(incomplete), self.SLUG))
        for chart in incomplete:
            self.fetch_hourly(hour=chart.hour, dry_run=dry_run, force_update=True)
            if not dry_run:
                AggregateHourlySongChart.generate(hour=chart.hour, regenerate=True)

    @classmethod
    def match_song(cls, alt_service, song, album, artists, try_artist=False, try_album=False):
        '''Attempt to match an alternate service song to a song from this service

        If an exact match is found, the database will be updated accordingly

        :param MusicService alt_service: The alternate service
        :param dict song: A dictionary of the form {'song_name': <name>, 'song_id': <id>}
            containing alternate service's name and ID
        :param dict album: A dictionary of the form {'album_name': <name>, 'album_id': <id>}
            containing alternate service's name and ID
        :param list artists: A list of dictionaries of the form [{'album_name': <name>, 'album_id': <id>}]
            containing alternate service's name and ID
        '''
        raise NotImplementedError

    def match_to_other_service(self, alt_service_cls, song_data, album_data, artists):
        '''Attempt to match a song for this service to another service

        If an exact match is found, the database will be updated accordingly

        :param callable alt_service_cls: The class for the alternate service.
            Matching is done via alt_service_cls.match_song
        :param dict song: A dictionary of the form {'song_name': <name>, 'song_id': <id>}
            containing alternate service's name and ID
        :param dict album: A dictionary of the form {'album_name': <name>, 'album_id': <id>}
            containing alternate service's name and ID
        :param list artists: A list of dictionaries of the form [{'album_name': <name>, 'album_id': <id>}]
            containing alternate service's name and ID
        '''
        search_kwargs = [
            {'try_artist': False, 'try_album': False},
            {'try_artist': True, 'try_album': False},
            {'try_artist': False, 'try_album': True},
            {'try_artist': True, 'try_album': True},
        ]
        song = None
        for kwargs in search_kwargs:
            song = alt_service_cls.match_song(self.service, song_data, album_data, artists, **kwargs)
            if song:
                break
        else:
            drop_parens = False
            for artist in artists:
                if '(' in artist['artist_name']:
                    # if artist_name ends in parentheses it's probably a
                    # translation, try without the translation as a last resort
                    artist['artist_name'] = re.sub('\(.+\)$', '', artist['artist_name'])
                    drop_parens = True
            if drop_parens:
                song = alt_service_cls.match_song(self.service, song_data, album_data,
                                                  artists, try_artist=True, try_album=True)
        if not song:
            logger.warning('no song for {}'.format(song_data['song_name']))
            return None
        MusicServiceSong.objects.get_or_create(
            song=song,
            service=self.service,
            defaults={'service_song_id': song_data['song_id']}
        )
        MusicServiceAlbum.objects.get_or_create(
            album=song.album,
            service=self.service,
            defaults={'service_album_id': album_data['album_id']}
        )
        for artist in artists:
            melon = alt_service_cls()
            if 'melon_id' in artist:
                melon_artist = MusicServiceArtist.objects.get(
                    service=melon.service,
                    service_artist_id=artist['melon_id']
                )
                MusicServiceArtist.objects.get_or_create(
                    artist=melon_artist.artist,
                    service=self.service,
                    defaults={'service_artist_id': artist['artist_id']}
                )
        return song


class MelonChartService(BaseChartService):

    NAME = 'Melon'
    URL = 'http://www.melon.com'
    ARTIST_URL = 'http://www.melon.com/artist/detail.htm?artistId={artist_id}'
    ALBUM_URL = 'http://www.melon.com/album/detail.htm?albumId={album_id}'
    SONG_URL = 'http://www.melon.com/song/detail.htm?songId={song_id}'
    SLUG = 'melon'
    VARIOUS_ARTISTS_ID = 2727

    def __init__(self):
        super(MelonChartService, self).__init__()
        (self.hourly_chart, created) = Chart.objects.get_or_create(
            service=self.service,
            defaults={
                'name': 'Melon realtime top 100',
                'url': 'http://www.melon.com/chart/index.htm',
                'weight': 0.5,  # the instiz weight for melon is 6x (50% of potential points)
            }
        )

    @classmethod
    def api_get_json(cls, url, params=None):
        headers = {'Accept': 'application/json', 'appKey': settings.MELON_APP_KEY}
        r = requests.get(url, params=params, headers=headers, timeout=REQUESTS_TIMEOUT)
        r.raise_for_status()
        return r.json()

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
        r = randomized_get(url)
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

    @classmethod
    def get_or_create_song_from_melon_data(cls, song_data):
        melon = cls()
        try:
            release_date = datetime.strptime(song_data['issueDate'], '%Y%m%d').date()
        except ValueError as exc:
            m = re.match(r'^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})$', song_data['issueDate'])
            if m:
                year = int(m.group('year'))
                month = int(m.group('month'))
                if month == 0:
                    month = 1
                day = int(m.group('day'))
                if day == 0:
                    day = 1
                release_date = date(year, month, day)
            else:
                raise exc
        artists = []
        for artist_data in song_data['artists']['artist']:
            artists.append(melon.get_artist_from_melon(artist_data['artistId']))
        defaults = {
            'name': song_data['albumName'],
            'artists': artists,
            'release_date': release_date,
        }
        album = melon.get_album_from_melon(song_data['albumId'], defaults=defaults)
        defaults['name'] = song_data['songName']
        defaults['album'] = album
        return melon.get_song_from_melon(song_data['songId'], defaults=defaults)

    def fetch_hourly(self, hour=None, dry_run=False, force_update=False):
        if hour:
            raise ValueError(
                'Melon does not allow historical hourly chart data to be retrieved. '
                'Only live hourly Melon chart data can be fetched.'
            )
        hour = strip_to_hour(utcnow())
        if not force_update:
            try:
                chart = HourlySongChart.objects.get(chart=self.hourly_chart, hour=hour)
                if chart and chart.entries.count() and not force_update:
                    logger.info('Skipping fetch for existing melon chart')
                    return chart
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
        melon_data = self.api_get_json(url, params)['melon']
        if melon_data['count'] != 100:
            raise ValueError('Melon returned unexpected number of chart entries: {}'.format(melon_data['count']))
        rank_hour = melon_hour(melon_data['rankDay'], melon_data['rankHour'])
        logger.info('Fetched melon realtime chart for {}'.format(rank_hour))
        if dry_run:
            return melon_data
        (hourly_song_chart, created) = HourlySongChart.objects.get_or_create(chart=self.hourly_chart, hour=rank_hour)
        if not created and hourly_song_chart.entries.count() and not force_update:
            logger.info('Skipping db update for existing melon chart')
            return hourly_song_chart
        for song_data in melon_data['songs']['song']:
            song = self.get_or_create_song_from_melon_data(song_data)
            defaults = {'position': song_data['currentRank']}
            (chart_entry, created) = HourlySongChartEntry.objects.get_or_create(
                hourly_chart=hourly_song_chart,
                song=song,
                defaults=defaults
            )
            if not created and chart_entry.position != song_data['currentRank']:
                chart_entry.position = song_data['currentRank']
                chart_entry.save()
            chart_entry.update_prev_position()
        logger.info('Wrote melon realtime chart for {} to database'.format(rank_hour))
        hourly_song_chart.update_next_chart()
        return hourly_song_chart

    @classmethod
    def search_artist(cls, name, page=1):
        url = 'http://apis.skplanetx.com/melon/artists'
        params = {
            'version': 1,
            'page': page,
            'count': 10,
            'searchKeyword': name.lower()
        }
        data = cls.api_get_json(url, params)['melon']
        if data['count']:
            artists = data['artists']['artist']
        else:
            m = re.match(r'^(.*)\(.*\)$', name.strip())
            if m:
                name = m.group(1).strip()
                return cls.search_artist(name, page)
            logger.info('No artist search results for {}'.format(params['searchKeyword']))
            artists = None
        if data['totalPages'] > data['page']:
            next_page = data['page'] + 1
        else:
            next_page = None
        return (artists, next_page)

    @classmethod
    def melonify_name(cls, name):
        # Melon use U+FFE6 FULLWIDTH WON SIGN
        # Other services use U+20A9 WON SIGN
        name = re.sub('[₩]', '￦', name)
        name = re.sub('[\'"`‘]', '', name)
        return name

    @classmethod
    def search_album(cls, name, page=1, artist_names=[], replace_amp=True):
        url = 'http://apis.skplanetx.com/melon/albums'
        orig_name = name
        replaced_amp = False
        if replace_amp:
            replaced_amp = True
            name = name.replace(' & ', ' and ')
        m = re.match(r'^(.*ost.*)\(.*\)$', name, re.I)
        if m:
            name = m.group(1).strip()
        m = re.match(r'^(.*)\(.*\)(.*ost.*)$', name, re.I)
        if m:
            name = '{} {}'.format(m.group(1), m.group(2)).strip()
        params = {
            'version': 1,
            'page': page,
            'count': 10,
            'searchKeyword': '{} {}'.format(name, ' '.join(artist_names)).lower()
        }
        data = cls.api_get_json(url, params)['melon']
        if data['count']:
            albums = data['albums']['album']
        else:
            if replaced_amp:
                return cls.search_album(orig_name, page, artist_names, replace_amp=False)
            m = re.match(r'^(.*\s)(?:album)(\s.*)?$', name, re.I)
            if m:
                name = m.group(1)
                if m.group(2):
                    name += m.group(2)
                return cls.search_album(name, page, artist_names)
            if artist_names:
                retry_names = []
                retry = False
                for artist_name in artist_names:
                    m = re.match(r'^(.*)\(.*\)$', artist_name.strip())
                    if m:
                        retry = True
                        artist_name = m.group(1).strip()
                    retry_names.append(artist_name)
                if retry:
                    return cls.search_album(name, page, retry_names)
            logger.info('No album search results for {}'.format(params['searchKeyword']))
            albums = None
        if data['totalPages'] > data['page']:
            next_page = data['page'] + 1
        else:
            next_page = None
        return (albums, next_page)

    @classmethod
    def search_song(cls, name, page=1, artist_names=[], album_name=''):
        url = 'http://apis.skplanetx.com/melon/songs'
        # melon prefers and for titles but & in featured artist lists
        m = re.match('^.*\(feat\.?.*\)', name, re.I)
        if not m:
            name = name.replace(' & ', ' and ')
        if album_name:
            m = re.match(r'^(.*ost.*)\(.*\)$', album_name, re.I)
            if m:
                album_name = m.group(1).strip()
        params = {
            'version': 1,
            'page': page,
            'count': 10,
            'searchKeyword': '{} {} {}'.format(name, ' '.join(artist_names), album_name).lower()
        }
        data = cls.api_get_json(url, params)['melon']
        if data['count']:
            songs = data['songs']['song']
        else:
            if artist_names:
                retry_names = []
                retry = False
                for artist_name in artist_names:
                    m = re.match(r'^(.*)\(.*\)$', artist_name.strip())
                    if m:
                        retry = True
                        artist_name = m.group(1).strip()
                    retry_names.append(artist_name)
                if retry:
                    return cls.search_song(name, page, artist_names=retry_names, album_name=album_name)
            logger.info('No song search results for {}'.format(params['searchKeyword']))
            songs = None
        if data['totalPages'] > data['page']:
            next_page = data['page'] + 1
        else:
            next_page = None
        return (songs, next_page)

    @classmethod
    def _compare_artist_sets(cls, left, right_list):
        intersections = []
        for right in right_list:
            i = left & right
            if i and len(i) == 1:
                intersections.append(i)
        if intersections and (len(intersections) == 1 or not set.intersection(*intersections)):
            return intersections
        return None

    @classmethod
    def match_song(cls, alt_service, song, album, artists, try_artist=False, try_album=False):
        melon = cls()
        try:
            # If we've already matched this song just return it
            alt_song = MusicServiceSong.objects.get(service=alt_service, service_song_id=song['song_id'])
            return alt_song.song
        except MusicServiceSong.DoesNotExist:
            pass
        for artist in artists:
            try:
                # Check for existing matched artists
                a = MusicServiceArtist.objects.get(service=alt_service, service_artist_id=artist['artist_id'])
                melon_artist = MusicServiceArtist.objects.get(service=melon.service, artist=a.artist)
                artist['melon_id'] = melon_artist.service_artist_id
                # replace service name with melon name for search purposes
                artist['artist_name'] = a.artist.name
            except MusicServiceArtist.DoesNotExist:
                (results, next_page) = cls.search_artist(artist['artist_name'])
                if not results:
                    return None
                artist['search_results'] = (results, next_page)
        try:
            # Check for existing matched albums
            a = MusicServiceAlbum.objects.get(service=alt_service, service_album_id=album['album_id'])
            melon_album = MusicServiceAlbum.objects.get(service=melon.service, album=a.album)
            album['melon_id'] = melon_album.service_album_id
            # replace service name with melon name for search purposes
            album['album_name'] = a.album.name
        except MusicServiceAlbum.DoesNotExist:
            search_kwargs = {}
            if try_artist:
                artist_names = []
                for artist in artists:
                    artist_names.append(artist['artist_name'])
                search_kwargs['artist_names'] = artist_names
            (results, next_page) = cls.search_album(album['album_name'], **search_kwargs)
            if not results:
                return None
            album['search_results'] = (results, next_page)
        search_kwargs = {}
        if try_artist:
            artist_names = []
            for artist in artists:
                artist_names.append(artist['artist_name'])
            search_kwargs['artist_names'] = artist_names
        if try_album:
            search_kwargs['album_name'] = album['album_name']
        (results, next_page) = cls.search_song(song['song_name'], **search_kwargs)
        if not results:
            return None
        song['search_results'] = (results, next_page)
        inst = bool(re.search('inst', song['song_name'], re.I))
        matched_song = None
        for potential_song in song['search_results'][0]:
            if matched_song:
                break

            # hack to make sure we don't match instrumentals to
            # non-instrumentals
            if inst != bool(re.search('inst', potential_song['songName'], re.I)):
                continue
            if 'melon_id' in album:
                if potential_song['albumId'] == album['melon_id']:
                    matched_song = potential_song
                    break
            else:
                for potential_album in album['search_results'][0]:
                    if potential_song['albumId'] != potential_album['albumId']:
                        continue
                    song_artist_set = set()
                    for a in potential_song['artists']['artist']:
                        song_artist_set.add(a['artistId'])
                    artist_set_list = []
                    for artist in artists:
                        if 'melon_id' in artist:
                            artist_set_list.append(set([artist['melon_id']]))
                        else:
                            artist_set = set()
                            for potential_artist in artist['search_results'][0]:
                                artist_set.add(potential_artist['artistId'])
                            artist_set_list.append(artist_set)
                    intersections = cls._compare_artist_sets(song_artist_set, artist_set_list)
                    if intersections:
                        matched_song = potential_song
                        song['melon_id'] = matched_song['songId']
                        album['melon_id'] = potential_album['albumId']
                        for i in intersections:
                            melon_id = i.pop()
                            for artist in artists:
                                if 'melon_id' in artist:
                                    continue
                                for potential_artist in artist['search_results'][0]:
                                    if melon_id == potential_artist['artistId']:
                                        artist['melon_id'] = melon_id
                                        break
                        break
        if matched_song:
            logger.debug('Got matched song: {}'.format(matched_song))
            return cls.get_or_create_song_from_melon_data(matched_song)
        else:
            logger.debug('Could not find match for song {}'.format(song))
            return None


class GenieChartService(BaseChartService):

    NAME = 'Genie'
    URL = 'http://www.genie.co.kr'
    ARTIST_URL = 'http://www.genie.co.kr/detail/artistInfo?xxnm={artist_id}'
    ALBUM_URL = 'http://www.genie.co.kr/detail/albumInfo?axnm={album_id}'
    SONG_URL = 'http://www.genie.co.kr/detail/songInfo?xgnm={song_id}'
    SLUG = 'genie'

    def __init__(self):
        super(GenieChartService, self).__init__()
        (self.hourly_chart, created) = Chart.objects.get_or_create(
            service=self.service,
            defaults={
                'name': 'Genie hourly top 100',
                'url': 'http://www.genie.co.kr/chart/top100',
                'weight': 0.25,  # the instiz weight for genie is 3x (20% of potential instiz points)
            }
        )

    def _get_artist_id_from_a(self, a):
        m = re.match(r'fnViewArtist\((?P<artist_id>\d+)\)', a.get('onclick'))
        if not m:
            return None
        return int(m.group('artist_id'))

    def _get_album_id_from_a(self, a):
        m = re.match(r'fnViewAlbumLayer\((?P<album_id>\d+)\)', a.get('onclick'))
        if not m:
            return None
        return int(m.group('album_id'))

    def _split_genie_artist(self, name, artist_id):
        # Genie lists collab'd artists as a group, all other services split
        # them so we determine if we need to split here
        if '&' in name:
            url = self.ARTIST_URL.format(artist_id=artist_id)
            r = randomized_get(url)
            r.raise_for_status()
            html = fromstring(r.text)
            main_infos = html.find_class('artist-main-infos')[0]
            type_span = main_infos.find("./div[@class='info-zone']/ul[@class='info-data']/li")
            if '프로젝트' in type_span.text_content():
                artist_list = html.find_class('artist-member-list')
                if artist_list:
                    # This is a collab artist
                    artists = []
                    for li in artist_list[0].findall('./ul/li'):
                        artist_a = li.find('./a')
                        artist_id = self._get_artist_id_from_a(artist_a)
                        artist_name = MelonChartService.melonify_name(li.text_content().strip())
                        artists.append({'artist_name': artist_name, 'artist_id': artist_id})
                    return artists
        return [{'artist_name': MelonChartService.melonify_name(name), 'artist_id': artist_id}]

    def _scrape_chart_entry(self, entry_element, dry_run=False):
        rank = None
        for cls in entry_element.classes:
            m = re.match('rank-(?P<rank>\d+)', cls)
            if m:
                rank = int(m.group('rank'))
        if not rank:
            raise RuntimeError('Got unexpected genie chart HTML')
        song_id = int(entry_element.get('songid'))
        try:
            # If we've already gotten this song, return it now. Normally this
            # check is performed in MelonChartService.match_song(), but for
            # genie we do this check here to avoid potential unnecessary artist lookup requests
            genie_song = MusicServiceSong.objects.get(service=self.service, service_song_id=song_id)
            return {'song': genie_song.song, 'position': rank}
        except MusicServiceSong.DoesNotExist:
            pass
        music_span = entry_element.find("./span[@class='music-info']/span[@class='music_area']/span[@class='music']")
        artist_a = music_span.find("./span[@class='meta']/a[@class='artist']")
        artist_name = artist_a.text.strip()
        artist_id = self._get_artist_id_from_a(artist_a)
        artists = self._split_genie_artist(artist_name, artist_id)
        album_a = music_span.find("./span[@class='meta']/a[@class='albumtitle']")
        album_id = self._get_album_id_from_a(album_a)
        album_name = album_a.text.strip()
        title_a = music_span.find("./a[@class='title']")
        song_name = title_a.text.strip()
        song_data = {'song_name': MelonChartService.melonify_name(song_name), 'song_id': song_id}
        album = {'album_name': MelonChartService.melonify_name(album_name), 'album_id': album_id}
        if dry_run:
            song_data.update(album)
            song_data['artists'] = artists
            logger.debug(song_data)
            return song_data
        search_kwargs = [
            {'try_artist': False, 'try_album': False},
            {'try_artist': True, 'try_album': False},
            {'try_artist': False, 'try_album': True},
            {'try_artist': True, 'try_album': True},
        ]
        song = None
        for kwargs in search_kwargs:
            song = MelonChartService.match_song(self.service, song_data, album, artists, **kwargs)
            if song:
                break
        if not song:
            logger.error('No match for genie song {}'.format(song_name))
            return None
        MusicServiceSong.objects.get_or_create(
            song=song,
            service=self.service,
            defaults={'service_song_id': song_id}
        )
        MusicServiceAlbum.objects.get_or_create(
            album=song.album,
            service=self.service,
            defaults={'service_album_id': album_id}
        )
        for artist in artists:
            melon = MelonChartService()
            if 'melon_id' in artist:
                melon_artist = MusicServiceArtist.objects.get(
                    service=melon.service,
                    service_artist_id=artist['melon_id']
                )
                MusicServiceArtist.objects.get_or_create(
                    artist=melon_artist.artist,
                    service=self.service,
                    defaults={'service_artist_id': artist['artist_id']}
                )
        return {'song': song, 'position': rank}

    def _scrape_hourly_chart_page(self, hour, page=1, dry_run=False):
        kr_hour = hour.astimezone(KR_TZ)
        url = self.hourly_chart.url
        params = {
            'ditc': 'D',
            'rtm': 'Y',
            'ymd': kr_hour.strftime('%Y%m%d'),
            'hh': kr_hour.strftime('%H'),
            'pg': page,
        }
        r = randomized_get(url, params=params)
        r.raise_for_status()
        html = fromstring(r.text)
        song_list = html.find_class('list-wrap')
        if len(song_list) != 1:
            raise RuntimeError('Got unexpected genie chart HTML')
        entries = []
        for list_entry in song_list[0]:
            entry = self._scrape_chart_entry(list_entry, dry_run=dry_run)
            if entry:
                entries.append(entry)
        return entries

    def _get_hourly_chart(self, hour, dry_run=False):
        pg1_data = self._scrape_hourly_chart_page(hour, page=1, dry_run=dry_run)
        pg2_data = self._scrape_hourly_chart_page(hour, page=2, dry_run=dry_run)
        return pg1_data + pg2_data

    def fetch_hourly(self, hour=None, dry_run=False, force_update=False):
        if hour:
            hour = strip_to_hour(hour)
        else:
            hour = strip_to_hour(utcnow())
        if not force_update:
            try:
                chart = HourlySongChart.objects.get(chart=self.hourly_chart, hour=hour)
                if chart and chart.entries.count() == 100 and not force_update:
                    logger.info('Skipping fetch for existing genie chart')
                    return chart
            except ObjectDoesNotExist:
                pass
            except MultipleObjectsReturned:
                pass
        genie_data = self._get_hourly_chart(hour, dry_run=dry_run)
        if len(genie_data) != 100:
            logger.warning('Genie returned unexpected number of chart entries: {}'.format(len(genie_data)))
        logger.info('Fetched genie realtime chart for {}'.format(hour))
        if dry_run:
            return genie_data
        (hourly_song_chart, created) = HourlySongChart.objects.get_or_create(chart=self.hourly_chart, hour=hour)
        if not created and hourly_song_chart.entries.count() == 100:
            logger.info('Skipping db update for existing genie chart')
            return hourly_song_chart
        for song_data in genie_data:
            defaults = {'position': song_data['position']}
            (chart_entry, created) = HourlySongChartEntry.objects.get_or_create(
                hourly_chart=hourly_song_chart,
                song=song_data['song'],
                defaults=defaults
            )
            if not created and chart_entry.position != song_data['position']:
                chart_entry.position = song_data['position']
                chart_entry.save()
            chart_entry.update_prev_position()
        logger.info('Wrote genie realtime chart for {} to database'.format(hour))
        hourly_song_chart.update_next_chart()
        return hourly_song_chart


class MnetChartService(BaseChartService):

    NAME = 'Mnet'
    URL = 'http://www.mnet.com'
    ARTIST_URL = 'http://www.mnet.com/artist/{artist_id}'
    ALBUM_URL = 'http://www.mnet.com/album/{album_id}'
    SONG_URL = 'http://www.mnet.com/track/{song_id}'
    SLUG = 'mnet'

    def __init__(self):
        super(MnetChartService, self).__init__()
        (self.hourly_chart, created) = Chart.objects.get_or_create(
            service=self.service,
            defaults={
                'name': 'Mnet hourly top 100',
                'url': 'http://www.mnet.com/chart/top100/',
                'weight': 0.125,
            }
        )

    def _get_song_id_from_a(self, a):
        patterns = [
            r"^.*mnetCom\.aodPlay\('(?P<song_id>\d+)'\)",
            r'/track/(?P<song_id>\d+)',
        ]
        for pattern in patterns:
            m = re.match(pattern, a.get('href'))
            if m:
                return int(m.group('song_id'))
        return None

    def _get_artist_id_from_a(self, a):
        m = re.match(r'^.*artist/(?P<artist_id>\d+)', a.get('href'))
        if m:
            return int(m.group('artist_id'))
        return None

    def _get_album_id_from_a(self, a):
        m = re.match(r'^.*/album/(?P<album_id>\d+)', a.get('href'))
        if m:
            return int(m.group('album_id'))
        return None

    def _scrape_chart_row(self, tr, dry_run=False):
        rank = None
        rank_span = tr.find_class('MMLI_RankNum')[0]
        for cls in rank_span.classes:
            m = re.match('^MMLI_RankNum(?:Best)?_(?P<rank>\d+)$', cls.strip())
            if m:
                rank = int(m.group('rank'))
                break
        if not rank:
            raise RuntimeError('Got unexpected mnet chart HTML')
        song_a = tr.find(".//a[@class='MMLI_Song']")
        song_data = {
            'song_id': self._get_song_id_from_a(song_a),
            'song_name': MelonChartService.melonify_name(song_a.text.strip()),
        }
        artists = []
        for artist_a in tr.findall(".//a[@class='MMLIInfo_Artist']"):
            artist_data = {
                'artist_id': self._get_artist_id_from_a(artist_a),
                'artist_name': MelonChartService.melonify_name(artist_a.text.strip()),
            }
            artists.append(artist_data)
        album_a = tr.find(".//a[@class='MMLIInfo_Album']")
        album_data = {
            'album_id': self._get_album_id_from_a(album_a),
            'album_name': MelonChartService.melonify_name(album_a.text.strip()),
        }
        if dry_run:
            song_data.update(album_data)
            song_data['artists'] = artists
            logger.debug(song_data)
            return song_data
        song = self.match_to_other_service(MelonChartService, song_data, album_data, artists)
        if not song:
            logger.error('No match for mnet song {}'.format(song_data['song_name']))
            return None
        else:
            return {'song': song, 'position': rank}

    def _scrape_hourly_chart_page(self, hour, page=1, dry_run=False):
        kr_hour = hour.astimezone(KR_TZ)
        url = '{}{}'.format(self.hourly_chart.url, kr_hour.strftime('%Y%m%d%H'))
        params = {
            'pNum': page,
        }
        r = randomized_get(url, params=params)
        r.raise_for_status()
        html = fromstring(r.text)
        chart_div = html.find_class('MMLTable')
        if len(chart_div) != 1:
            raise RuntimeError('Got unexpected mnet chart HTML')
        entries = []
        for tr in chart_div[0].findall('.//tbody/tr'):
            entry = self._scrape_chart_row(tr, dry_run=dry_run)
            if entry:
                entries.append(entry)
        return entries

    def _get_hourly_chart(self, hour, dry_run=False):
        pg1_data = self._scrape_hourly_chart_page(hour, page=1, dry_run=dry_run)
        pg2_data = self._scrape_hourly_chart_page(hour, page=2, dry_run=dry_run)
        return pg1_data + pg2_data

    def fetch_hourly(self, hour=None, dry_run=False, force_update=False):
        if hour:
            hour = strip_to_hour(hour)
        else:
            hour = strip_to_hour(utcnow())
        if not force_update:
            try:
                chart = HourlySongChart.objects.get(chart=self.hourly_chart, hour=hour)
                if chart and chart.entries.count() == 100 and not force_update:
                    logger.info('Skipping fetch for existing mnet chart')
                    return chart
            except ObjectDoesNotExist:
                pass
            except MultipleObjectsReturned:
                pass
        mnet_data = self._get_hourly_chart(hour, dry_run=dry_run)
        if len(mnet_data) != 100:
            logger.warning('Mnet returned unexpected number of chart entries: {}'.format(len(mnet_data)))
        logger.info('Fetched mnet realtime chart for {}'.format(hour))
        if dry_run:
            return mnet_data
        (hourly_song_chart, created) = HourlySongChart.objects.get_or_create(chart=self.hourly_chart, hour=hour)
        if not created and hourly_song_chart.entries.count() == 100:
            logger.info('Skipping db update for existing mnet chart')
            return hourly_song_chart
        for song_data in mnet_data:
            if song_data['song']:
                defaults = {'position': song_data['position']}
                (chart_entry, created) = HourlySongChartEntry.objects.get_or_create(
                    hourly_chart=hourly_song_chart,
                    song=song_data['song'],
                    defaults=defaults
                )
                if not created and chart_entry.position != song_data['position']:
                    chart_entry.position = song_data['position']
                    chart_entry.save()
                chart_entry.update_prev_position()
        logger.info('Wrote mnet realtime chart for {} to database'.format(hour))
        hourly_song_chart.update_next_chart()
        return hourly_song_chart


class BugsChartService(BaseChartService):

    NAME = 'Bugs!'
    URL = 'http://www.bugs.co.kr/'
    ARTIST_URL = 'http://music.bugs.co.kr/artist/{artist_id}'
    ALBUM_URL = 'http://music.bugs.co.kr/album/{album_id}'
    SONG_URL = 'http://music.bugs.co.kr/track/{song_id}'
    SLUG = 'bugs'

    def __init__(self):
        super(BugsChartService, self).__init__()
        (self.hourly_chart, created) = Chart.objects.get_or_create(
            service=self.service,
            defaults={
                'name': 'Bugs! hourly top 100',
                'url': 'http://music.bugs.co.kr/chart/track/realtime/total',
                'weight': 0.125,
            }
        )

    def _get_song_id_from_a(self, a):
        m = re.match(r"^.*bugs\.music\.listen\('(?P<song_id>\d+)'", a.get('onclick'))
        if m:
            return int(m.group('song_id'))
        return None

    def _get_artist_id_from_a(self, a):
        m = re.match(r'^.*/artist/(?P<artist_id>\d+)', a.get('href'))
        if m:
            return int(m.group('artist_id'))
        return None

    @classmethod
    def _unbugsify_artist_name(cls, name):
        m = re.match(r'^(.*)\[(.+)\]$', name.strip())
        if m:
            member_name = m.group(1)
            group_name = m.group(2)
            # replace square braces with parentheses unless this artist
            # already has an alternate name in parentheses, in which
            # case drop whatever was inside the square braces
            if '(' not in member_name:
                name = '{} ({})'.format(member_name, group_name).strip()
            else:
                name = member_name.strip()
        return name

    def _get_multi_artists_from_a(self, a):
        artists = []
        pattern = r"^(?:.*openMultiArtistSearchResultPopLayer\(.+,\s+')(?P<artist_list>.+\|\|.+\|\|\d+(?:\\n)?)+'"
        m = re.match(pattern, a.get('onclick'))
        if m:
            for artist in m.group('artist_list').split('\\\\n'):
                (short_name, name, artist_id) = artist.split('||')
                artists.append({
                    'artist_name': MelonChartService.melonify_name(self._unbugsify_artist_name(name)),
                    'artist_id': int(artist_id),
                })
        return artists

    def _get_album_id_from_a(self, a):
        m = re.match(r'^.*/album/(?P<album_id>\d+)', a.get('href'))
        if m:
            return int(m.group('album_id'))
        return None

    def _scrape_chart_row(self, tr, dry_run=False):
        rank_span = tr.find("./td/div[@class='ranking']/strong")
        rank = int(rank_span.text.strip())
        song_a = tr.find("./th/p[@class='title']/a")
        song_data = {
            'song_id': self._get_song_id_from_a(song_a),
            'song_name': MelonChartService.melonify_name(song_a.text.strip()),
        }
        if tr.get('multiartist') == 'Y':
            artist_a = tr.find("./td/p[@class='artist']/a[@class='more']")
            artists = self._get_multi_artists_from_a(artist_a)
        else:
            artist_a = tr.find("./td/p[@class='artist']/a")
            artists = [{
                'artist_id': self._get_artist_id_from_a(artist_a),
                'artist_name': MelonChartService.melonify_name(self._unbugsify_artist_name(artist_a.text.strip())),
            }]
        album_a = tr.find("./td/a[@class='album']")
        album_data = {
            'album_id': self._get_album_id_from_a(album_a),
            'album_name': MelonChartService.melonify_name(album_a.text.strip()),
        }
        if dry_run:
            song_data.update(album_data)
            song_data['artists'] = artists
            song_data['rank'] = rank
            logger.debug(song_data)
            return song_data
        song = self.match_to_other_service(MelonChartService, song_data, album_data, artists)
        if not song:
            logger.error('No match for bugs song {} {} {}'.format(song_data, album_data, artists))
            return None
        else:
            return {'song': song, 'position': rank}

    def _get_hourly_chart(self, hour, dry_run=False):
        kr_hour = hour.astimezone(KR_TZ)
        url = self.hourly_chart.url
        params = {
            'chartdate': kr_hour.strftime('%Y%m%d'),
            'charthour': kr_hour.strftime('%H'),
        }
        r = randomized_get(url, params=params)
        r.raise_for_status()
        html = fromstring(r.text)
        chart_table = html.find_class('byChart')
        if len(chart_table) != 1:
            raise RuntimeError('Got unexpected bugs chart HTML')
        entries = []
        for tr in chart_table[0].findall('.//tbody/tr'):
            entry = self._scrape_chart_row(tr, dry_run=dry_run)
            if entry:
                entries.append(entry)
        return entries

    def fetch_hourly(self, hour=None, dry_run=False, force_update=False):
        if hour:
            hour = strip_to_hour(hour)
        else:
            hour = strip_to_hour(utcnow())
        if not force_update:
            try:
                chart = HourlySongChart.objects.get(chart=self.hourly_chart, hour=hour)
                if chart and chart.entries.count() == 100 and not force_update:
                    logger.info('Skipping fetch for existing bugs chart')
                    return chart
            except ObjectDoesNotExist:
                pass
            except MultipleObjectsReturned:
                pass
        bugs_data = self._get_hourly_chart(hour, dry_run=dry_run)
        if len(bugs_data) != 100:
            logger.warning('Bugs returned unexpected number of chart entries: {}'.format(len(bugs_data)))
        logger.info('Fetched bugs realtime chart for {}'.format(hour))
        if dry_run:
            return bugs_data
        (hourly_song_chart, created) = HourlySongChart.objects.get_or_create(chart=self.hourly_chart, hour=hour)
        if not created and hourly_song_chart.entries.count() == 100:
            logger.info('Skipping db update for existing bugs chart')
            return hourly_song_chart
        for song_data in bugs_data:
            if song_data['song']:
                defaults = {'position': song_data['position']}
                (chart_entry, created) = HourlySongChartEntry.objects.get_or_create(
                    hourly_chart=hourly_song_chart,
                    song=song_data['song'],
                    defaults=defaults
                )
                if not created and chart_entry.position != song_data['position']:
                    chart_entry.position = song_data['position']
                    chart_entry.save()
                chart_entry.update_prev_position()
        logger.info('Wrote bugs realtime chart for {} to database'.format(hour))
        hourly_song_chart.update_next_chart()
        return hourly_song_chart


# Add chart services to process here
CHART_SERVICES = {
    'melon': MelonChartService,
    'genie': GenieChartService,
    'mnet': MnetChartService,
    'bugs': BugsChartService,
}
