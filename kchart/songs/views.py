# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.views.generic import (
    DetailView,
)

from ..charts.models import (
    Song,
)


class SongView(DetailView):

    template_name = 'songs/song_detail.html'
    model = Song
