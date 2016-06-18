# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from django.core.management.base import BaseCommand, CommandError

from kchart.charts.chartservice import CHART_SERVICES


class Command(BaseCommand):

    help = 'Refreshes any incomplete charts'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            help='Fetch data but do not write chart updates to the database')
        parser.add_argument('chart', nargs='*')

    def handle(self, *args, **options):
        for chart in options['chart']:
            if chart not in CHART_SERVICES:
                raise CommandError('Unknown chart: {}'.format(chart))
            if chart == 'melon':
                raise CommandError('historical melon data cannot be retrieved')
            service = CHART_SERVICES[chart.lower()]()
            service.refetch_incomplete(dry_run=options['dry_run'])
