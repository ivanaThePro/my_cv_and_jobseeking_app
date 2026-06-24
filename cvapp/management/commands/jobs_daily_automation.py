"""Daily job search automation: python manage.py jobs_daily_automation"""

from django.core.management.base import BaseCommand

from cvapp.jobs_automation import run_daily_automation


class Command(BaseCommand):
    help = 'Run scheduled search, auto-score, and optional email digest.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-digest',
            action='store_true',
            help='Skip the email digest step',
        )

    def handle(self, *args, **options):
        result = run_daily_automation(send_digest=not options['no_digest'])
        if result.get('ok'):
            self.stdout.write(self.style.SUCCESS(result.get('message', 'Done')))
        else:
            self.stderr.write(result.get('error', 'Failed'))
            raise SystemExit(1)
