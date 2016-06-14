# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from django.core.management.base import BaseCommand, CommandError

from kchart.charts.utils import CHART_SERVICES


class Command(BaseCommand):

    help = 'Updates the specified chart'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            help='Do not write chart updates to the database')
        parser.add_argument('chart', choices=CHART_SERVICES.keys())

    def handle(self, *args, **options):
        chart = options['chart']
        if chart not in CHART_SERVICES:
            raise CommandError('Unknown chart: {}'.format(chart))
        service = CHART_SERVICES[chart.lower()]()
        service.fetch_hourly(dry_run=options['dry_run'], cmd=self, verbosity=options['verbosity'])
