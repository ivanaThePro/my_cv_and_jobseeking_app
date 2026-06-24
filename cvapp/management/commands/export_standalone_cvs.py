from django.core.management.base import BaseCommand

from cvapp.standalone_cv import write_standalone_cv_files


class Command(BaseCommand):
    help = 'Export all role-based standalone CV HTML files to the project root.'

    def handle(self, *args, **options):
        paths = write_standalone_cv_files()
        for path in paths:
            self.stdout.write(self.style.SUCCESS(f'Wrote {path.name}'))
        self.stdout.write(self.style.SUCCESS(f'Exported {len(paths)} CV files.'))
