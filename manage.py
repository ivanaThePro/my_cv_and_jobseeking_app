#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Always run from this project folder (fixes wrong cvsite/cvapp on PYTHONPATH).
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cvsite.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        try:
            import django
            django.setup()
            import cvsite.routing as routing
            from django.conf import settings
            print(f'\n>>> PROJECT_DIR: {PROJECT_DIR}')
            print(f'>>> ROOT_URLCONF: cvsite.routing')
            print(f'>>> routing file: {routing.__file__}')
            print(f'>>> First route: {routing.urlpatterns[0].pattern}')
            gate = 'ON' if getattr(settings, 'CV_ACCESS_PASSWORD', '') else 'OFF'
            print(f'>>> CV password gate: {gate}\n')
        except Exception as exc:
            print(f'>>> Startup check failed: {exc}\n')

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
