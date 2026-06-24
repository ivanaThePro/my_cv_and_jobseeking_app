"""Score all jobs in cache via: python manage.py score_jobs"""

from django.core.management.base import BaseCommand

from cvapp import pipeline_status as pstatus
from cvapp.views import _run_job_search_pipeline


class Command(BaseCommand):
    help = "Score every job in the cache with Mistral (same as dashboard Score all)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-jobs",
            type=int,
            default=0,
            help="Limit jobs (0 = all in cache, up to WEB_MAX_JOBS)",
        )

    def handle(self, *args, **options):
        if pstatus.is_running():
            self.stderr.write("Another pipeline is already running. Reset it on the dashboard first.")
            return
        max_jobs = options["max_jobs"] or 0
        self.stdout.write("Scoring jobs from cache (this can take 1–2 hours)…")
        waiting, generated, out_dir, scored_n, matches_n = _run_job_search_pipeline(
            use_cache=True,
            max_jobs=max_jobs,
            dry_run=True,
            track_progress=False,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Run {out_dir.name}: scored {scored_n} jobs "
                f"({matches_n} at 50%+ match, {waiting} were waiting). "
                f"Open /jobs/market/ in the browser."
            )
        )
