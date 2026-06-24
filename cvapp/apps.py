import os
from pathlib import Path

from django.apps import AppConfig


class CvappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cvapp'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                from django.urls import get_resolver
                patterns = [str(p.pattern) for p in get_resolver().url_patterns[:4]]
                if not any('assets' in p for p in patterns):
                    print(
                        'WARNING: /assets/ route missing — restart from the project root. '
                        'Styling uses inline CSS fallback.'
                    )
            except Exception:
                pass
        base = Path(__file__).resolve().parents[1]
        env_path = base / '.env'
        if not env_path.exists():
            return
        try:
            import jobsearch_lib as lib
            lib.load_env_files()
        except ImportError:
            for line in env_path.read_text(encoding='utf-8-sig').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and value:
                    os.environ[key] = value
