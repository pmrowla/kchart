# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url

from . import views

urlpatterns = [
    url(
        regex=r'^(?P<pk>\d+)/$',
        view=views.SongView.as_view(),
        name='song-detail'
    ),
]
