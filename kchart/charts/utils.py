# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from datetime import datetime

from pytz import timezone, utc


KR_TZ = timezone('Asia/Seoul')


def utcnow():
    return datetime.now(utc)


def strip_to_hour(time):
    '''Strip minutes/seconds from a datetime object'''
    return datetime(time.year, time.month, time.day, time.hour, tzinfo=time.tzinfo)


def melon_hour(day, hour):
    '''Return a datetime object from the melon formatted day and hour parameters'''
    return KR_TZ.localize(datetime.strptime('{} {}'.format(day, hour), '%Y%m%d %H'))
