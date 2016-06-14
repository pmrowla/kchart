# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from test_plus.test import TestCase

from kchart.charts.models import MusicService


class TestMusicService(TestCase):

    def setUp(self):
        MusicService.objects.create(
            name='testservice',
            url='http:///',
            _artist_url='/artists/{artist_id}/',
            _album_url='/albums/{album_id}/',
            _song_url='/songs/{song_id}/'
        )

    def test_get_artist_url(self):
        service = MusicService.objects.get(name='testservice')
        self.assertEqual(
            service.get_artist_url(1),
            '/artists/1/'
        )

    def test_get_album_url(self):
        service = MusicService.objects.get(name='testservice')
        self.assertEqual(
            service.get_album_url(1),
            '/albums/1/'
        )

    def test_get_song_url(self):
        service = MusicService.objects.get(name='testservice')
        self.assertEqual(
            service.get_song_url(1),
            '/songs/1/'
        )
