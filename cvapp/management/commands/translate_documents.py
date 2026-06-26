from django.core.management.base import BaseCommand, CommandError

from cvapp.document_translator import refresh_all_translations


class Command(BaseCommand):
    help = 'Generate cached de/no HTML translations for CV and transcript pages via Mistral.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-translate even when cache hash matches source.',
        )
        parser.add_argument(
            '--lang',
            action='append',
            dest='langs',
            choices=['de', 'no'],
            help='Target language(s). Default: de and no.',
        )
        parser.add_argument(
            '--doc',
            action='append',
            dest='doc_kinds',
            help='Document id(s) only, e.g. transcript or professional. Default: all.',
        )

    def handle(self, *args, **options):
        langs = tuple(options['langs'] or ('de', 'no'))
        doc_kinds = tuple(options['doc_kinds']) if options['doc_kinds'] else None
        try:
            lines = refresh_all_translations(
                langs=langs,
                force=options['force'],
                doc_kinds=doc_kinds,
            )
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        for line in lines:
            self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS(f'Done ({len(lines)} steps).'))
