import json
import os
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

import jobsearch_lib as lib
from cvapp import applied_jobs, views


class CVAppTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _unlock_site(self, password='secret', next_url='/jobs/market/'):
        return self.client.post(
            '/cv/unlock/',
            {'password': password, 'next': next_url},
        )

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_homepage_redirects_to_jobs_market(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/jobs/market/', response.url)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_jobs_market_status_code(self):
        response = self.client.get('/jobs/market/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jobs')
        self.assertContains(response, 'Search')

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_standalone_cvs_require_unlock_when_protected(self):
        for slug in ('support-technician', 'python-developer'):
            with self.subTest(slug=slug):
                blocked = self.client.get(f'/cv/html/{slug}/')
                self.assertEqual(blocked.status_code, 302, slug)
                self.assertIn('/cv/unlock/', blocked.url)
        self._unlock_site()
        for slug in ('support-technician', 'python-developer', 'it-trainee', 'graduate-trainee', 'project-coordinator', 'data-analyst'):
            with self.subTest(slug=slug):
                response = self.client.get(f'/cv/html/{slug}/')
                self.assertEqual(response.status_code, 200, slug)
                self.assertContains(response, 'Ivana Jovic')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_support_technician_standalone_cv(self):
        response = self.client.get('/cv/html/support-technician/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Customer Service')
        self.assertContains(response, 'Pedagogical authorization')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_it_trainee_standalone_cv(self):
        response = self.client.get('/cv/html/python-developer/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Career Counselor')
        self.assertContains(response, 'Hero Kompetanse')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_commerzbank_standalone_cv(self):
        response = self.client.get('/cv/html/support-technician/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Customer Service')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_professional_page_is_courses_and_skills_record(self):
        response = self.client.get('/cv/html/professional/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Courses & Skills Record')
        self.assertContains(response, 'Higher Education')
        self.assertContains(response, 'Practical-Pedagogical Education')
        self.assertContains(response, 'BA International Development')
        self.assertNotContains(response, 'PROFESSIONAL EXPERIENCE')
        self.assertContains(response, 'QUTV2ÅR1')
        self.assertContains(response, 'KRIM2920')
        self.assertContains(response, 'Official Transcript')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_academic_transcript_page(self):
        response = self.client.get('/transcript/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'University of Oslo')
        self.assertContains(response, 'International Development')
        self.assertContains(response, 'QUTV2ÅR1')
        self.assertContains(response, 'UTVB3300')
        self.assertContains(response, 'KRIM2920')
        self.assertContains(response, 'Compulsory subjects')
        self.assertNotContains(response, '199.0 ECTS')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_standalone_cv_links_use_same_origin_paths(self):
        response = self.client.get('/cv/html/python-developer/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/transcript/"')
        self.assertContains(response, 'href="/cv/html/professional/"')
        self.assertNotContains(response, 'cv-website-1-t8oi.onrender.com')
        self.assertNotContains(response, 'cv-9eq5.onrender.com')

    @override_settings(CV_ACCESS_PASSWORD='', CV_PUBLIC_BASE_URL='https://ivana-cv.onrender.com')
    def test_standalone_cv_links_use_configured_public_base(self):
        response = self.client.get('/cv/html/python-developer/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://ivana-cv.onrender.com/transcript/')
        self.assertContains(response, 'https://ivana-cv.onrender.com/cv/html/professional/')

    def test_arbeitsagentur_refnr_wins_over_bad_marketing_url(self):
        job = {
            'title': 'Dev',
            'company': 'Acme',
            'applyUrl': 'https://www.arbeitsagentur.de/karriere/',
            'refnr': '10001-1234567890-S',
        }
        resolved = lib.resolve_apply_url(job)
        self.assertIn('jobdetail/10001-1234567890-S', resolved)

    def test_eures_jvid_resolves_to_arbeitsagentur_jobdetail(self):
        eures = (
            'https://europa.eu/eures/portal/jv-detail/jv?'
            'jvId=MTAwMDEtMTAwMzA3NTY3My1TIDE'
        )
        resolved = lib.resolve_apply_url({'applyUrl': eures})
        self.assertEqual(
            resolved,
            'https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1003075673-S',
        )

    def test_arbeitsagentur_two_segment_jobdetail_preserved(self):
        url = 'https://www.arbeitsagentur.de/jobsuche/jobdetail/13319-879327/1_612791LS-S'
        self.assertEqual(lib.normalize_apply_url(url), url)
        self.assertTrue(lib.is_job_listing_url(url))

    def test_arbeitsagentur_search_rows_skips_non_dict_payload(self):
        rows = lib._arbeitsagentur_search_rows({'stellenangebote': 'temporary error'})
        self.assertEqual(rows, [])
        rows = lib._arbeitsagentur_search_rows({
            'stellenangebote': [
                {'refnr': '1', 'titel': 'Admin', 'arbeitsort': 'Frankfurt am Main', 'arbeitgeber': 'ACME'},
            ]
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(lib._arbeitsort_parts(rows[0].get('arbeitsort'))[0], 'Frankfurt am Main')

    def test_arbeitsagentur_string_arbeitsort_does_not_crash(self):
        ort, plz = lib._arbeitsort_parts('Wiesbaden', fallback='Frankfurt')
        self.assertEqual(ort, 'Wiesbaden')
        self.assertEqual(plz, '')
        company = lib._arbeitgeber_label({'name': 'Leonardo GmbH'})
        self.assertEqual(company, 'Leonardo GmbH')

    def test_full_match_detects_all_requirements_met(self):
        match = {'must_have_total': 5, 'must_have_met_count': 5, 'match_score': 88}
        self.assertTrue(lib.is_full_requirement_match(match))

    def test_full_match_row_requires_fifty_percent_score(self):
        from cvapp.views import _is_full_match_row

        low = {
            'scored': True,
            'match_score': 45,
            'match': {'must_have_total': 5, 'must_have_met_count': 5, 'match_score': 45},
        }
        self.assertFalse(_is_full_match_row(low))
        high = {
            'scored': True,
            'match_score': 60,
            'match': {'must_have_total': 5, 'must_have_met_count': 5, 'match_score': 60},
        }
        self.assertTrue(_is_full_match_row(high))

    def test_degree_ready_detects_education_met(self):
        match = {
            'requirements_analysis': [
                {'requirement': 'Bachelor degree in any field', 'section': 'education', 'status': 'met'},
                {'requirement': 'Python', 'section': 'must-have', 'status': 'partial'},
            ],
        }
        blob = 'We need a university degree and Python skills'
        self.assertTrue(lib.is_degree_requirement_met(match, blob=blob, title='Junior Analyst'))

    def test_course_syllabus_urls_verified(self):
        from cvapp.course_links import course_syllabus_backup_path, course_syllabus_url

        self.assertEqual(
            course_syllabus_url('PED'),
            'https://www.uio.no/english/studies/programmes/ppu/',
        )
        self.assertEqual(
            course_syllabus_url('1DV502'),
            'https://kursplan.lnu.se/kursplaner/syllabus-1DV502-2.000.pdf',
        )
        self.assertEqual(
            course_syllabus_url('D0017D'),
            'https://www.ltu.se/en/education/syllabuses/course-syllabus?id=D0017D',
        )
        self.assertEqual(
            course_syllabus_url('IN1000'),
            'https://www.uio.no/studier/emner/matnat/ifi/IN1000/index-eng.html',
        )
        self.assertEqual(
            course_syllabus_url('1DT110'),
            'https://www.uu.se/en/study/syllabus?query=50973',
        )
        self.assertEqual(
            course_syllabus_url('BA'),
            'https://student.oslomet.no/en/bachelor-utviklingsstudier',
        )
        self.assertEqual(course_syllabus_backup_path('1DV535'), '/course-syllabus/syllabus-1DV535-1.pdf')
        self.assertEqual(course_syllabus_url(''), '')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_cv_download_pdf_endpoint(self):
        response = self.client.get('/cv/backend/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('Counselor_CV.pdf', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))
        from pypdf import PdfReader
        page_count = len(PdfReader(BytesIO(response.content)).pages)
        self.assertLessEqual(page_count, 4, f'PDF should stay compact (got {page_count} pages)')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_cv_print_page_renders(self):
        response = self.client.get('/cv/backend/print/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ivana Jovic')
        self.assertContains(response, 'Hero Kompetanse')
        self.assertContains(response, 'Career Counselor')
        self.assertContains(response, 'International Development')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_cv_select_lists_multiple_profiles(self):
        response = self.client.get('/cv/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Career Counselor CV')
        self.assertContains(response, 'Customer Service')
        self.assertContains(response, 'Professional CV (detailed courses)')
        self.assertContains(response, 'Consolidated academic record')
        self.assertContains(response, 'Graduate Trainee CV')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_cv_select_alias_redirects(self):
        response = self.client.get('/cv/select/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/cv/')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_technical_support_cv_highlights_education(self):
        response = self.client.get('/cv/technical-support/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'University of Oslo')
        self.assertContains(response, 'Career counseling')
        self.assertContains(response, 'Customer Service')
        self.assertContains(response, 'entry-header')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_cv_variant_fullstack_differs_from_backend(self):
        backend = self.client.get('/cv/backend/')
        fullstack = self.client.get('/cv/fullstack/')
        self.assertEqual(backend.status_code, 200)
        self.assertEqual(fullstack.status_code, 200)
        self.assertContains(backend, 'Career Counselor')
        self.assertContains(backend, 'cv-job-title')
        self.assertContains(fullstack, 'Language Teacher')
        self.assertContains(fullstack, 'Spanish')

    def test_cv_password_enabled_by_default(self):
        with self.settings(CV_ACCESS_PASSWORD='Ivana Jovic2026'):
            for path in ('/cv/enter/', '/cv/', '/cv/backend/', '/cv/manual/'):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302, msg=path)
                self.assertIn('/cv/unlock/', response.url, msg=path)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_manual_cv_renders_general_layout(self):
        response = self.client.get('/cv/manual/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hero Kompetanse')
        self.assertContains(response, 'Olympiatoppen')
        self.assertContains(response, 'References')
        self.assertContains(response, 'Upon request')
        self.assertNotContains(response, '90 78 79 41')
        self.assertNotContains(response, 'Sel Statlig Mottak')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_key_pages_have_no_legacy_earmyas_content(self):
        markers = ('earmyas', 'dell', 'addis ababa', 'measho', 'gebre', '199 ects', 'cv-website-1-t8oi.onrender.com')
        paths = (
            '/cv/general/',
            '/cv/manual/',
            '/transcript/',
            '/cv/html/support-technician/',
            '/cv/html/professional/',
        )
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=path)
            body = response.content.decode('utf-8').lower()
            for marker in markers:
                self.assertNotIn(marker, body, msg=f'{path} still contains {marker!r}')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_technical_support_pdf_has_no_blank_pages(self):
        from cvapp.cv_pdf import build_cv_pdf_bytes
        from cvapp.cv_profiles import get_cv_profile
        from pypdf import PdfReader

        pdf = build_cv_pdf_bytes(profile=get_cv_profile('technical-support'))
        reader = PdfReader(BytesIO(pdf))
        self.assertLessEqual(len(reader.pages), 3, msg='IT Support CV should fit in 3 pages')
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or '').strip()
            self.assertGreater(len(text), 120, msg=f'page {index} is nearly empty')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_manual_cv_pdf_download(self):
        response = self.client.get('/cv/manual/download/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('General_CV.pdf', response['Content-Disposition'])
        from pypdf import PdfReader
        text = '\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(response.content)).pages)
        self.assertIn('Upon request', text)
        self.assertNotIn('90 78 79 41', text)
        self.assertLessEqual(len(PdfReader(BytesIO(response.content)).pages), 2)

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_cv_requires_password_when_configured(self):
        response = self.client.get('/cv/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/cv/unlock/', response.url)

        unlock = self.client.post('/cv/unlock/', {'password': 'wrong', 'next': '/cv/'})
        self.assertEqual(unlock.status_code, 200)
        self.assertContains(unlock, 'Incorrect password')

        unlock = self.client.post('/cv/unlock/', {'password': 'secret', 'next': '/cv/'})
        self.assertEqual(unlock.status_code, 302)
        self.assertEqual(self.client.get('/cv/').status_code, 200)
        self.assertEqual(self.client.get('/cv/').status_code, 200)

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_transcript_and_professional_require_password(self):
        for path in ('/transcript/', '/cv/html/professional/'):
            with self.subTest(path=path):
                blocked = self.client.get(path)
                self.assertEqual(blocked.status_code, 302)
                self.assertIn('/cv/unlock/', blocked.url)
        self._unlock_site()
        self.assertEqual(self.client.get('/transcript/').status_code, 200)
        self.assertEqual(self.client.get('/cv/html/professional/').status_code, 200)

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_robots_txt_blocks_crawlers(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('Disallow: /', body)
        self.assertIn('GPTBot', body)
        self.assertIn('PerplexityBot', body)

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_unlock_lockout_after_failures(self):
        for _ in range(8):
            self.client.post('/cv/unlock/', {'password': 'wrong', 'next': '/jobs/market/'})
        locked = self.client.post('/cv/unlock/', {'password': 'wrong', 'next': '/jobs/market/'})
        self.assertEqual(locked.status_code, 200)
        self.assertContains(locked, 'Too many failed attempts')

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_protected_pages_send_noindex_headers(self):
        self._unlock_site()
        response = self.client.get('/jobs/market/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('noindex', response.headers.get('X-Robots-Tag', ''))
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_jobs_market_requires_password(self):
        response = self.client.get('/jobs/market/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/cv/unlock/', response.url)

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_cv_unlock_rejects_external_next_url(self):
        response = self.client.post(
            '/cv/unlock/?next=https://evil.example/phish',
            {'password': 'secret'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('evil.example', response.url)
        self.assertTrue(response.url.endswith('/cv/') or '/cv/' in response.url)

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_logout_clears_session_and_shows_unlock(self):
        self._unlock_site()
        self.assertEqual(self.client.get('/jobs/market/').status_code, 200)
        logout = self.client.get('/cv/logout/')
        self.assertEqual(logout.status_code, 302)
        self.assertIn('/cv/unlock/', logout.url)
        self.assertIn('signed_out=1', logout.url)
        unlock_page = self.client.get(logout.url)
        self.assertEqual(unlock_page.status_code, 200)
        self.assertContains(unlock_page, 'signed out', status_code=200)
        blocked = self.client.get('/jobs/market/')
        self.assertEqual(blocked.status_code, 302)
        self.assertIn('/cv/unlock/', blocked.url)

    @override_settings(CV_ACCESS_PASSWORD='secret')
    def test_cv_select_translates_to_german(self):
        self._unlock_site(next_url='/cv/')
        response = self.client.get('/cv/?lang=de')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lebenslauf &amp; akademische Nachweise')
        self.assertContains(response, 'Basis-Lebenslauf-Vorlagen')
        self.assertContains(response, 'Karriereberaterin CV')

    @override_settings(DEBUG=False, CV_ACCESS_REQUIRED=False, CV_ACCESS_PUBLIC=True, CV_ACCESS_PASSWORD='')
    def test_production_open_when_password_not_required(self):
        """Pre-deploy / Render without CV_ACCESS_REQUIRED stays open."""
        response = self.client.get('/jobs/market/')
        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False, CV_ACCESS_REQUIRED=True, CV_ACCESS_PUBLIC=False, CV_ACCESS_PASSWORD='secret')
    def test_production_lock_when_password_required(self):
        response = self.client.get('/jobs/market/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/cv/unlock/', response.url)

    @override_settings(DEBUG=False, CV_ACCESS_PASSWORD='')
    def test_system_check_hidden_in_production(self):
        self.assertEqual(self.client.get('/_sys/check/').status_code, 404)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_jobs_market_defaults_to_all_view(self):
        response = self.client.get('/jobs/market/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Browse: All jobs')
        self.assertContains(response, 'browse-menu')
        self.assertContains(response, 'browse-chip-list')
        self.assertContains(response, 'data-tip=')
        self.assertContains(response, 'Score')
        self.assertContains(response, 'jobs-market-banner')
        self.assertContains(response, 'data-stat-jobs')
        self.assertContains(response, 'stat-chip-link')
        self.assertContains(response, 'Import URL')
        self.assertContains(response, 'Find jobs')
        self.assertContains(response, 'My CVs')
        self.assertContains(response, 'Grades &amp; courses')
        self.assertContains(response, 'topbar-stats-hint')
        self.assertNotContains(response, 'Top picks')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_jobs_reset_pipeline_ajax(self):
        from cvapp import pipeline_status as pstatus

        pstatus.write_status(state='running', phase='score', progress=1, total=10)
        response = self.client.post(
            '/jobs/reset/',
            {},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertFalse(pstatus.is_running())

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_jobs_clear_scores_endpoint(self):
        response = self.client.post(
            '/jobs/clear-scores/',
            {},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))

    def test_legacy_match_payload_rejected(self):
        legacy = {
            'match': {
                'reasoning': 'Good fit via ~199 ECTS bachelor-equivalent and Dell awards.',
                'requirements_analysis': [],
            }
        }
        self.assertTrue(lib.is_legacy_match_payload(legacy))
        current = {
            'candidate_profile_id': lib.CANDIDATE_PROFILE_ID,
            'match': {
                'reasoning': 'BA International Development and teaching experience fit admin role.',
                'requirements_analysis': [],
            },
        }
        self.assertFalse(lib.is_legacy_match_payload(current))

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_stale_running_search_recovers_when_cache_has_jobs(self):
        from datetime import datetime, timedelta

        from cvapp import pipeline_status as pstatus

        pstatus.clear_cancel()
        stale_at = (datetime.now() - timedelta(minutes=10)).isoformat(timespec='seconds')
        pstatus.STATUS_PATH.write_text(
            json.dumps({
                'state': 'running',
                'phase': 'search',
                'message': 'Starting search…',
                'progress': 0,
                'total': 6,
                'live_count': 12,
                'updated_at': stale_at,
            }),
            encoding='utf-8',
        )
        with patch.object(pstatus, '_cache_job_count', return_value=12):
            status = pstatus.read_status()
        self.assertEqual(status.get('state'), 'completed')
        self.assertFalse(pstatus.is_running())

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_jobs_market_live_returns_jobs_fast(self):
        response = self.client.get('/jobs/market/live/?view=all')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertIn('jobs', data)
        self.assertGreater(len(data.get('jobs') or []), 0)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_jobs_market_embeds_slim_job_list(self):
        response = self.client.get('/jobs/market/?view=all')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="jobs-data"')
        self.assertNotContains(response, '<script id="jobs-data" type="application/json">[]</script>')
        self.assertContains(response, 'scoreOneUrl:')
        data = self.client.get('/jobs/market/data/?view=all').json()
        self.assertTrue(data.get('ok'))
        self.assertGreater(len(data.get('jobs') or []), 0)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_jobs_market_data_includes_ui_diagnostics(self):
        response = self.client.get('/jobs/market/data/?view=all')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertIn('source_issues', data)
        self.assertIsInstance(data['source_issues'], list)
        self.assertIn('view_label', data)
        self.assertIn('cache_raw_total', data)

    def test_source_issues_for_ui_lists_empty_sources(self):
        from cvapp.views import _source_issues_for_ui
        issues = _source_issues_for_ui({
            'sources': [
                {'source': 'Arbeitnow API', 'status': 'ok', 'count': 12},
                {'source': 'Indeed RSS (DE)', 'status': 'empty', 'count': 0},
                {'source': 'Arbeitsagentur API', 'status': 'error', 'count': 0, 'error': 'timeout'},
            ],
        })
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['source'], 'Arbeitsagentur API')
        self.assertEqual(issues[0]['status'], 'error')

    def test_source_issues_for_ui_shows_empty_primary_sources(self):
        from cvapp.views import _source_issues_for_ui
        issues = _source_issues_for_ui({
            'sources': [
                {'source': 'EURES EU job portal (free)', 'status': 'empty', 'count': 0},
            ],
        })
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['status'], 'empty')

    def test_scoring_queue_prioritizes_it_jobs(self):
        from cvapp.views import _scoring_priority
        it_job = {'title': 'Python Developer', 'description': 'Django backend'}
        office_job = {'title': 'Project Coordinator', 'description': 'Bachelor degree office role'}
        self.assertLess(_scoring_priority(it_job), _scoring_priority(office_job))

    def test_market_tab_stats_role_counts_fit_total(self):
        from cvapp.views import _market_tab_stats, _build_unified_job_rows, _merged_scored_lookup
        rows = _build_unified_job_rows([], _merged_scored_lookup(None), hide_low_scores=False)
        stats = _market_tab_stats(rows)
        role_sum = stats['it_total'] + stats['non_it_total'] + stats['other_total']
        self.assertEqual(role_sum, stats['cache_raw_total'])
        self.assertLessEqual(stats['it_good_total'], stats['it_total'])
        self.assertLessEqual(stats['good_fits_total'], stats['scored_total'])

    def test_support_technician_classified_as_it_not_non_it(self):
        job = {
            'title': 'Support Technician (m/w/d)',
            'description': 'First-level IT support for enterprise clients.',
        }
        self.assertTrue(lib.is_it_focused_job(job))
        self.assertFalse(lib.is_non_it_degree_job(job))

    def test_desktop_support_classified_as_it(self):
        job = {'title': 'Desktop Support Specialist', 'description': 'Windows and Office support.'}
        self.assertTrue(lib.is_it_focused_job(job))
        self.assertFalse(lib.is_non_it_degree_job(job))

    def test_is_non_it_degree_job_detects_coordinator(self):
        job = {
            'title': 'Project Coordinator (m/w/d)',
            'description': 'University graduate welcome. Bachelor degree required.',
        }
        self.assertTrue(lib.is_non_it_degree_job(job))
        self.assertFalse(lib.is_it_focused_job(job))

    def test_is_it_focused_job_detects_developer(self):
        job = {
            'title': 'Python Developer (m/w/d)',
            'description': 'Django REST API backend development.',
        }
        self.assertTrue(lib.is_it_focused_job(job))
        self.assertFalse(lib.is_non_it_degree_job(job))

    def test_suggest_cv_profile_maps_roles(self):
        self.assertEqual(
            views._suggest_cv_profile('Python Developer (m/w/d)')['slug'],
            'python-developer',
        )
        self.assertEqual(
            views._suggest_cv_profile('Project Coordinator Sustainability')['slug'],
            'python-developer',
        )
        self.assertTrue(views._suggest_cv_profile('Python Developer')['standalone'])

    def test_build_ai_tailored_cv_html(self):
        from cvapp.standalone_cv_builder import build_ai_tailored_cv_html

        html = build_ai_tailored_cv_html('project-coordinator', {
            'header_job_title': 'Project Coordinator',
            'profile_intro': 'STEM graduate ready to coordinate sustainability projects.',
            'profile_highlights': ['<strong>Education:</strong> 199 ECTS bachelor-equivalent.'],
            'skill_boxes': [
                {'heading': 'Coordination', 'content': 'Planning, documentation, Jira'},
                {'heading': 'STEM', 'content': 'Environment, mathematics, research'},
                {'heading': 'Communication', 'content': 'English, Norwegian, multilingual advisory'},
            ],
            'interests': 'Sustainability, hiking.',
        })
        self.assertIn('Project Coordinator', html)
        self.assertIn('Complete Career &amp; Education Chronology', html)
        self.assertIn('Serbo-Croatian', html)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_job_tailored_cv_404_when_missing(self):
        response = self.client.get('/jobs/tailored-cv/doesnotexist123/')
        self.assertEqual(response.status_code, 404)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_job_tailored_cover_letter_404_when_missing(self):
        response = self.client.get('/jobs/tailored-cover/doesnotexist123/')
        self.assertEqual(response.status_code, 404)

    def test_build_cover_letter_html(self):
        from cvapp.standalone_cv_builder import build_cover_letter_html

        html = build_cover_letter_html(
            job_title='Junior Analyst',
            company='Commerzbank',
            location='Frankfurt',
            ai_payload={
                'greeting': 'Dear Hiring Manager',
                'paragraphs': [
                    'I am applying for the Junior Analyst role.',
                    'My STEM education and project experience align with your requirements.',
                ],
                'closing': 'Kind regards,',
                'subject_line': 'Application for Junior Analyst',
            },
        )
        self.assertIn('Commerzbank', html)
        self.assertIn('Junior Analyst', html)
        self.assertIn('Dear Hiring Manager', html)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_jobs_hub_urls_in_market_context(self):
        response = self.client.get('/jobs/market/?view=it')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'generateMaterialsUrl', response.content)
        self.assertIn(b'/jobs/generate-materials/', response.content)
        self.assertIn(b'importJobUrl', response.content)

    @override_settings(CV_ACCESS_PASSWORD='')
    @patch('cvapp.views._score_single_imported_job')
    @patch('cvapp.views.lib.import_job_from_url')
    def test_jobs_import_url_adds_job(self, mock_import, mock_score):
        mock_import.return_value = {
            'title': 'Analyst',
            'company': 'Acme GmbH',
            'location': 'Frankfurt, Germany',
            'description': 'Analyze data and write reports for the team.',
            'applyUrl': 'https://example.com/jobs/analyst',
            'url': 'https://example.com/jobs/analyst',
            'source': 'Imported link',
        }
        mock_score.return_value = {
            'match_score': 62,
            'recommendation': 'review',
            'reasoning': 'Good fit for analyst role.',
            'must_have_met_count': 4,
            'must_have_total': 7,
        }
        response = self.client.post(
            '/jobs/import-url/',
            data=json.dumps({'url': 'https://example.com/jobs/analyst', 'score': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['job']['title'], 'Analyst')
        self.assertTrue(data.get('scored'))

    def test_parse_role_company_from_imported_page_title(self):
        role, company = lib._parse_role_company_from_page_title(
            'Software Engineer | Acme GmbH | LinkedIn'
        )
        self.assertEqual(role, 'Software Engineer')
        self.assertEqual(company, 'Acme GmbH')
        role2, company2 = lib._parse_role_company_from_page_title(
            'Data Analyst at Commerzbank AG'
        )
        self.assertEqual(role2, 'Data Analyst')
        self.assertEqual(company2, 'Commerzbank AG')

    def test_non_it_rejects_hinduism_teacher(self):
        job = {
            'title': 'Hinduism Teacher (m/w/d)',
            'description': 'Teach religious studies at our community center.',
        }
        self.assertFalse(lib.is_non_it_degree_job(job))
        job = {
            'title': 'Hinduism Teacher (m/w/d)',
            'description': 'Teach religious studies at our community center.',
        }
        self.assertFalse(lib.is_non_it_degree_job(job))

    def test_non_it_accepts_course_relevant_sustainability_role(self):
        job = {
            'title': 'Junior Specialist Energy & Climate (m/w/d)',
            'description': (
                'Support sustainability reporting and environmental data analysis. '
                'University degree welcome. Entry level. English team. ' * 4
            ),
        }
        self.assertTrue(lib.is_non_it_degree_job(job))
        self.assertFalse(lib.is_it_focused_job(job))

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_cv_experience_includes_gap_periods(self):
        response = self.client.get('/cv/backend/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hope for Justice')
        self.assertContains(response, '02/2017 - 07/2018')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_cv_education_uses_vitnemal_periods(self):
        response = self.client.get('/cv/backend/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '08/2014 - 06/2015')
        self.assertContains(response, 'University of Oslo')
        self.assertContains(response, '08/2010 - 06/2013')

    def test_localize_match_translates_german_status(self):
        match = {
            'match_score': 55,
            'reasoning': 'Kandidat erfüllt mehrere Voraussetzungen.',
            'requirements_analysis': [
                {'requirement': 'Abgeschlossenes Studium', 'status': 'erfüllt', 'evidence': 'BA degree'},
            ],
        }
        out = lib.localize_match_for_display(match)
        self.assertEqual(out['requirements_analysis'][0]['status'], 'met')
        self.assertIn('university', out['requirements_analysis'][0]['requirement'].lower())

    def test_localize_match_translates_mixed_german_requirements(self):
        reqs = [
            'university degree mit guten Leistungen in (Wirtschafts-) Informatik, Mathematik oder vergleichbare Kenntnisse',
            'Softwareentwicklungskenntnisse in gängigen Programmiersprachen (bspw. Java, Python, Go,...)',
            'Interesse an agilen Projektvorgehensweisen',
            'Fähigkeit im Team, aber auch eigenverantwortlich zu arbeiten',
        ]
        for raw in reqs:
            out = lib._translate_phrase_to_english(raw)
            self.assertFalse(lib._looks_german(out), msg=f'Still German: {out!r} from {raw!r}')

    def test_marketing_landing_page_rejected(self):
        self.assertFalse(lib.is_job_listing_url('https://www.arbeitsagentur.de/karriere/'))

    def test_resolve_apply_url_without_refnr_uses_listing(self):
        job = {
            'title': 'Python Trainer',
            'company': 'Ratbacher',
            'applyUrl': 'https://www.ratbacher.de/job/apply/123',
        }
        resolved = lib.resolve_apply_url(job)
        self.assertIn('ratbacher.de/job/apply/', resolved)

    def test_scored_lookup_matches_cache_by_title_when_apply_url_empty(self):
        meta = {
            'title': 'Python Trainer',
            'company': 'Acme GmbH',
            'apply_url': '',
            'match': {'match_score': 70, 'recommendation': 'apply'},
        }
        keys = views._scored_lookup_keys(meta)
        self.assertIn('acme gmbh|python trainer', keys)

    def test_stepstone_job_url_is_direct(self):
        url = 'https://www.stepstone.de/stellenangebote--software-developer-m-w-d-frankfurt-1234567.html'
        self.assertTrue(lib.is_direct_apply_url(url))

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_applied_page_loads(self):
        response = self.client.get('/jobs/applied/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your applications')
        # Empty state when no tracked applications; table when entries exist.
        self.assertTrue(
            b'applied-hub-table' in response.content or b'applied-hub-empty' in response.content
        )
        response = self.client.get('/jobs/market/?view=applied')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/jobs/applied', response.url)

    def test_english_display_title_strips_german_markers(self):
        import jobsearch_lib as lib
        title = lib.english_display_title('Werkstudent:in IT Support & Data Governance (m/w/d)')
        self.assertNotIn('m/w/d', title.lower())
        self.assertIn('Working Student', title)
        self.assertIn('IT Support', title)

    def test_job_payload_includes_english_card_fields(self):
        row = {
            'job_id': 'abc',
            'title': 'Werkstudent:in IT Support (m/w/d)',
            'company': 'Acme GmbH',
            'location': 'Berlin, Germany',
            'source': 'Arbeitsagentur',
            'apply_url': 'https://example.com/job',
            'remote': False,
            'description': 'Support role',
            'match_score': 62,
            'recommendation': 'apply',
            'ai_summary': 'Strong fit for support and documentation.',
            'scored': True,
            'keyword_hint': '',
            'match': {
                'reasoning': 'Good overlap with Dell support and Python coursework.',
                'recommendation': 'apply',
                'role_category': 'IT Support',
                'required_met': ['Python', 'Customer support'],
                'required_missing': ['German C1'],
            },
        }
        payload = views._row_to_job_payload(row)
        self.assertIn('Working Student', payload['title_en'])
        self.assertNotIn('m/w/d', payload['title_en'].lower())
        self.assertEqual(payload['recommendation_label'], 'Ready to apply')
        self.assertTrue(payload['list_hint'])
        self.assertEqual(payload['career_branch_label'], 'IT & tech')
        self.assertIn('good_match', payload)
        self.assertIn('listable_in_all', payload)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_applied_job_excluded_from_browse_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'applied_jobs.json'
            with patch.object(applied_jobs, 'APPLIED_PATH', path):
                applied_jobs.mark_applied(
                    job_id='hide-me-99',
                    title='Office Coordinator',
                    company='Test GmbH',
                    location='Frankfurt, Germany',
                )
                with patch.object(views, '_build_unified_job_rows') as mock_rows:
                    mock_rows.return_value = [
                        {
                            'job_id': 'hide-me-99',
                            'title': 'Office Coordinator',
                            'company': 'Test GmbH',
                            'location': 'Frankfurt',
                            'source': 'Test',
                            'apply_url': '',
                            'remote': False,
                            'description': '',
                            'description_preview': '',
                            'scored': False,
                            'match': None,
                        },
                        {
                            'job_id': 'keep-me-1',
                            'title': 'Junior Analyst',
                            'company': 'Other GmbH',
                            'location': 'Köln',
                            'source': 'Test',
                            'apply_url': '',
                            'remote': False,
                            'description': '',
                            'description_preview': '',
                            'scored': False,
                            'match': None,
                        },
                    ]
                    with patch.object(views.lib, 'load_cached_jobs', return_value=[]):
                        with patch.object(views, '_list_job_runs', return_value=[]):
                            with patch.object(views, '_merged_scored_lookup', return_value={}):
                                response = self.client.get('/jobs/market/data/?view=all')
                self.assertEqual(response.status_code, 200)
                payload = json.loads(response.content)
                jobs = payload.get('jobs') or payload.get('jobs_view') or []
                job_ids = [row['job_id'] for row in jobs]
                self.assertNotIn('hide-me-99', job_ids)
                self.assertIn('keep-me-1', job_ids)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_applied_tab_shows_tracked_job_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'applied_jobs.json'
            with patch.object(applied_jobs, 'APPLIED_PATH', path):
                applied_jobs.mark_applied(
                    job_id='abc123',
                    title='Junior Analyst (m/w/d)',
                    company='Acme GmbH',
                    location='Frankfurt, Germany',
                )
                response = self.client.get('/jobs/applied/')
                self.assertContains(response, 'Acme GmbH')
                self.assertContains(response, 'applied-hub-table')
                self.assertContains(response, 'Junior Analyst')
                self.assertContains(response, 'Germany')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_mark_and_unmark_applied_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'applied_jobs.json'
            with patch.object(applied_jobs, 'APPLIED_PATH', path):
                applied_jobs.mark_applied(
                    job_id='abc123',
                    title='Support Engineer',
            company='Acme GmbH',
                    location='Frankfurt, Germany',
                )
                self.assertTrue(applied_jobs.is_applied('abc123'))
                entries = applied_jobs.list_applied()
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]['country'], 'Germany')

                response = self.client.post(
                    '/jobs/applied/toggle/',
                    data=json.dumps({'job_id': 'abc123'}),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(applied_jobs.is_applied('abc123'))

    def test_infer_country_from_location(self):
        self.assertEqual(
            applied_jobs.infer_country(location='Frankfurt am Main, Germany'),
            'Germany',
        )
        self.assertEqual(applied_jobs.infer_country(job={'country': 'DE'}), 'Germany')

    def test_prefilter_drops_irrelevant_and_non_it_jobs(self):
        jobs = [
            {
                'title': 'Judo Instructor (m/w/d)',
                'company': 'Sports Club',
                'location': 'Frankfurt, Germany',
                'description': 'Teach judo classes to children. ' * 20,
                'applyUrl': 'https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1111111111-S',
            },
            {
                'title': 'Python Developer (m/w/d)',
                'company': 'Tech GmbH',
                'location': 'Frankfurt, Germany',
                'description': (
                    'We need a Python developer with Django and REST API experience. '
                    'Junior or mid-level software engineer for our team. ' * 8
                ),
                'applyUrl': 'https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-2222222222-S',
            },
        ]
        filtered, stats = lib.prefilter_jobs_for_candidate(jobs)
        titles = [lib.job_text_fields(j)[2] for j in filtered]
        self.assertNotIn('Judo Instructor (m/w/d)', titles)
        self.assertIn('Python Developer (m/w/d)', titles)
        self.assertGreater(stats.get('irrelevant_role', 0) + stats.get('no_cv_overlap', 0), 0)

    def test_prefilter_keeps_bachelor_level_non_it_role(self):
        jobs = [
            {
                'title': 'Project Coordinator (m/w/d)',
                'company': 'Green Energy AG',
                'location': 'Köln, Germany',
                'description': (
                    'We welcome applicants with a bachelor degree or university graduate background. '
                    'Coordinate sustainability and research projects. Entry level welcome. '
                    'Strong project and documentation skills. ' * 6
                ),
                'applyUrl': 'https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-3333333333-S',
            },
        ]
        filtered, _stats = lib.prefilter_jobs_for_candidate(jobs)
        titles = [lib.job_text_fields(j)[2] for j in filtered]
        self.assertIn('Project Coordinator (m/w/d)', titles)

    def test_eures_job_url_counts_as_direct_apply(self):
        url = 'https://europa.eu/eures/portal/jv-detail/jv?jvId=TEST123'
        self.assertTrue(lib.is_job_listing_url(url))

    def test_prefilter_drops_dual_study_student_program(self):
        jobs = [
            {
                'title': 'Bachelor Mechatronik (m/w/d)',
                'company': 'Auto GmbH',
                'location': 'Frankfurt, Germany',
                'description': (
                    'Starte dein duales Studium. Hochschulzugangsberechtigung Abitur erforderlich. '
                    'Wechselst du zwischen deinem Studium an der Hochschule und dem Unternehmen. '
                    '8-Semester Regelstudienzeit. ' * 5
                ),
                'applyUrl': 'https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-4444444444-S',
            },
        ]
        filtered, stats = lib.prefilter_jobs_for_candidate(jobs)
        self.assertEqual(len(filtered), 0)
        self.assertGreater(stats.get('student_program', 0), 0)

    def test_prefilter_keeps_any_bachelor_field_job(self):
        jobs = [
            {
                'title': 'Junior Specialist (m/w/d)',
                'company': 'Services AG',
                'location': 'Bonn, Germany',
                'description': (
                    'We accept a university degree in any field. English-speaking team. '
                    'Entry level office role with training. ' * 8
                ),
                'applyUrl': 'https://europa.eu/eures/portal/jv-detail/jv?jvId=ANYFIELD1',
            },
        ]
        filtered, _stats = lib.prefilter_jobs_for_candidate(jobs)
        self.assertEqual(len(filtered), 1)

    def test_low_score_jobs_hidden_from_list(self):
        rows = [
            {
                'job_id': 'low1',
                'title': 'Dev',
                'company': 'A',
                'location': 'Frankfurt',
                'scored': True,
                'match_score': 35,
                'match': {'match_score': 35},
                'recommendation': 'skip',
            },
            {
                'job_id': 'ok1',
                'title': 'Analyst',
                'company': 'B',
                'location': 'Köln',
                'scored': True,
                'match_score': 62,
                'match': {'match_score': 62},
                'recommendation': 'review',
            },
            {
                'job_id': 'new1',
                'title': 'Trainee',
                'company': 'C',
                'location': 'Bonn',
                'scored': False,
                'match_score': None,
                'match': {},
                'recommendation': '',
            },
        ]
        visible = [r for r in rows if views._is_visible_job_row(r)]
        self.assertEqual(len(visible), 2)
        self.assertEqual(visible[0]['job_id'], 'ok1')
        self.assertEqual(visible[1]['job_id'], 'new1')

    @override_settings(CV_ACCESS_PASSWORD='')
    @patch('cvapp.views.lib.generate_tailored_html_cv')
    @patch('cvapp.views._require_env')
    def test_generate_materials_uses_browser_job_snapshot(self, mock_env, mock_generate):
        mock_env.return_value = 'test-key'
        mock_generate.return_value = {
            'header_job_title': 'Business Analyst',
            'profile_intro': 'Intro',
            'profile_highlights': ['A'],
            'skill_boxes': [{'title': 'Skills', 'items': ['Python']}],
            'interests': 'Tech',
        }
        body = {
            'job_id': 'abc123snapshot01',
            'material': 'cv',
            'job': {
                'job_id': 'abc123snapshot01',
                'title': 'Business Analyst (m/w/d)',
                'company': 'DFB',
                'location': 'Frankfurt am Main',
                'description': 'Wir suchen einen Business Analyst f├╝r Disposition.',
                'apply_url': 'https://example.com/job/123',
            },
        }
        response = self.client.post(
            '/jobs/generate-materials/',
            data=json.dumps(body),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertIn('tailored_cv_url', data)
        mock_generate.assert_called_once()

    @override_settings(CV_ACCESS_PASSWORD='')
    @patch('cvapp.views.lib.generate_role_requested_html_cv')
    @patch('cvapp.views._require_env')
    def test_generate_role_cv_is_not_job_specific(self, mock_env, mock_generate):
        mock_env.return_value = 'test-key'
        mock_generate.return_value = {
            'header_job_title': 'Software Developer',
            'profile_intro': 'Intro',
            'profile_highlights': ['A'],
            'skill_boxes': [{'title': 'Skills', 'items': ['Python']}],
            'interests': 'Tech',
        }
        body = {'role': 'Software Developer'}
        response = self.client.post(
            '/jobs/generate-role-cv/',
            data=json.dumps(body),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertIn('role_cv_url', data)
        self.assertEqual(data.get('target_role'), 'Software Developer')
        slug = views._role_cv_slug('Software Developer')
        role_path = views._role_cv_path(slug)
        posting_path = views._tailored_cv_path('any-job-id')
        self.assertTrue(role_path.is_file())
        self.assertNotEqual(role_path.parent, posting_path.parent)
        self.assertFalse(posting_path.is_file())
        mock_generate.assert_called_once()

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_generate_role_cv_requires_role_text(self):
        response = self.client.post(
            '/jobs/generate-role-cv/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('role', response.json().get('error', '').lower())

    @override_settings(CV_ACCESS_PASSWORD='')
    @patch('cvapp.views.pstatus.is_running', return_value=True)
    @patch('cvapp.views.pstatus.read_status', return_value={'state': 'running', 'phase': 'search'})
    def test_score_one_blocked_while_search_running(self, _mock_status, _mock_running):
        response = self.client.post(
            '/jobs/score-one/',
            data=json.dumps({'job_id': 'x1', 'job': {'job_id': 'x1', 'title': 'Test'}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn('running', response.json().get('error', '').lower())

    @override_settings(CV_ACCESS_PASSWORD='')
    @patch('cvapp.views.pstatus.read_status', return_value={'state': 'idle'})
    @patch('cvapp.views._score_single_imported_job')
    @patch.dict(os.environ, {'MISTRAL_API_KEY': 'test-key'})
    def test_score_one_uses_browser_snapshot_when_cache_misses(self, mock_score, _mock_status):
        mock_score.return_value = {'match_score': 73, 'recommendation': 'review', 'reasoning': 'Good fit'}
        body = {
            'job_id': 'missing-from-cache-1',
            'job': {
                'job_id': 'missing-from-cache-1',
                'title': 'Support Technician',
                'company': 'Acme GmbH',
                'location': 'Bonn',
                'description': 'Helpdesk and endpoint support',
                'apply_url': 'https://example.com/job/42',
            },
        }
        response = self.client.post(
            '/jobs/score-one/',
            data=json.dumps(body),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['job']['match_score'], 73)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_professional_page_translates_skills_to_german(self):
        response = self.client.get('/cv/html/professional/?lang=de')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hochschulbildung')

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_professional_page_translates_to_norwegian(self):
        response = self.client.get('/cv/html/professional/?lang=no')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        # Full translation when cache exists; at minimum section headings switch.
        self.assertTrue(
            'Høyere utdanning' in content or 'Hoeyere utdanning' in content,
            'Norwegian higher-education heading expected',
        )
        self.assertNotIn('Higher Education</div>', content)
        self.assertIn('@media print{.cv-lang-bar{display:none!important}}', content)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_transcript_german_uses_saved_translation_without_live_api(self):
        from cvapp.document_translator import translate_html_document

        path = Path(__file__).resolve().parents[1] / 'academic_transcript_improved.html'
        html = path.read_text(encoding='utf-8')
        with patch.dict(os.environ, {'DOCUMENT_I18N_ALLOW_LIVE': 'false', 'MISTRAL_API_KEY': 'test-key'}):
            with patch('cvapp.document_translator.mistral_translate_html') as live:
                out = translate_html_document(
                    html,
                    lang='de',
                    doc_kind='transcript',
                    allow_live=False,
                )
                live.assert_not_called()
        self.assertIn('QUTV2ÅR1', out)
        self.assertNotIn('Consolidated Academic Record</h1>', out)

    @override_settings(CV_ACCESS_PASSWORD='')
    def test_transcript_page_translates_to_norwegian(self):
        response = self.client.get('/transcript/?lang=no')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Samlet akademisk oversikt', content)
        self.assertIn('QUTV2ÅR1', content)
        self.assertIn('Norsk hoeyere utdanning', content)
        self.assertNotIn('Consolidated Academic Record</h1>', content)

    @patch.dict(os.environ, {'CRON_SECRET': 'cron-test-secret'})
    def test_jobs_cron_daily_rejects_missing_secret(self):
        response = self.client.post('/jobs/cron/daily/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'Unauthorized')

    @patch.dict(os.environ, {'CRON_SECRET': 'cron-test-secret'})
    def test_jobs_cron_daily_post_accepted_with_secret(self):
        with patch('cvapp.jobs_automation.run_daily_automation', return_value={'ok': True, 'steps': ['ok']}):
            response = self.client.post('/jobs/cron/daily/?secret=cron-test-secret')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
