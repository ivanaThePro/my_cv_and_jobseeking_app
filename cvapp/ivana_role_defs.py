"""Ivana Jovic — timeline, awards, and role-specific CV definitions."""

from __future__ import annotations

from .standalone_cv_builder import (
    ACCENT_BLUE,
    ACCENT_BLUE_LIGHT,
    ACCENT_INDIGO,
    ACCENT_INDIGO_LIGHT,
    ACCENT_PURPLE,
    ACCENT_PURPLE_LIGHT,
    ACCENT_SKY,
    ACCENT_SKY_LIGHT,
    ACCENT_TEAL,
    ACCENT_TEAL_LIGHT,
    RoleCV,
    _role,
)

LANGUAGES = (
    'Serbo-Croatian (native); Norwegian, English, Spanish (proficient); '
    'Russian (intermediate); Macedonian (basic)'
)

IVANA_AWARDS = (
    '<li><strong>Pedagogical authorization (University of Oslo):</strong> '
    'Qualified teacher — pre-school, primary, secondary, and adult level.</li>',
    '<li><strong>Student role model grant (2011):</strong> '
    'Reidar and Gunnar Holst\'s endowment.</li>',
)

IVANA_GRADUATE_AWARDS = (
    '<li><strong>BA International Development (HiOA, 2013):</strong> '
    'Dissertation on migrant worker exploitation in Gulf countries; fieldwork in Mexico.</li>',
    '<li><strong>Multilingual professional:</strong> Teaching, career counseling, '
    'reception, and NGO program experience across Norway and Germany.</li>',
)

_DEFAULT_EDUCATION_FOCUS = (
    'International Development, Practical-Pedagogical Education, Spanish language studies, '
    'Scandinavian languages, and labor law (in progress).'
)

_DEFAULT_RECENT = (
    'Career counseling and Norwegian instruction for foreign-speaking adults at Hero Kompetanse.',
    'Substitute Spanish teaching at Rudolf Steiner School; based in Frankfurt am Main, Germany.',
)

CAREER_TIMELINE = ''  # built dynamically via build_career_timeline()


def build_career_timeline(*, recent_bullets_html: str, education_focus: str, professional_url: str) -> str:
    from html import escape as esc

    from .cv_template import timeline_row, timeline_separator

    sep = timeline_separator
    prof_link = (
        f'<a class="web-link priority-education-link course-record-cta" href="{esc(professional_url)}" '
        f'rel="noopener noreferrer" target="_blank" title="Open detailed education and course record">'
        f'View detailed education and course record</a>'
    )
    ba_bullets = (
        f'<ul class="entry-body"><li><strong>Focus:</strong> {esc(education_focus)}</li>'
        f'<li>Dissertation on migrant worker exploitation in Gulf countries; fieldwork in Mexico.</li>'
        f'<li>{prof_link}</li></ul>'
    )
    spanish_bullets = (
        '<ul class="entry-body"><li>Spanish language and Latin American culture.</li>'
        '<li>Exchange: Costa Rican Language Academy, San José (6 months).</li></ul>'
    )
    parts = [
        timeline_row(
            '09/2020 - present',
            'Career counselor / Teacher',
            'Experience',
            org='Hero Kompetanse',
            location='Norway',
            bullets_html=f'<ul class="entry-body">{recent_bullets_html}</ul>',
        ),
        sep(),
        timeline_row(
            '11/2014 - present',
            'Teacher Substitute (Spanish)',
            'Experience',
            org='Rudolf Steiner School',
            location='Lørenskog, Norway',
            bullets_html='<ul class="entry-body"><li>Spanish instruction for grades 2–10; classroom management and lesson delivery.</li></ul>',
        ),
        sep(),
        timeline_row(
            '01/2020 - 06/2020',
            'Teacher (Spanish)',
            'Experience',
            org='Hersleb High School',
            location='Norway',
            bullets_html='<ul class="entry-body"><li>Spanish language instruction.</li></ul>',
        ),
        sep(),
        timeline_row(
            '02/2017 - 07/2018',
            'Case worker / Trainer',
            'Experience',
            org='Hope for Justice',
            location='Norway',
            bullets_html=(
                '<ul class="entry-body"><li>Networking and course activities on human trafficking.</li>'
                '<li>Support work with victims of human trafficking.</li></ul>'
            ),
        ),
        sep(),
        timeline_row(
            '08/2015 - 11/2016',
            'Teacher (Norwegian, adult level)',
            'Experience',
            org='Caritas',
            location='Norway',
            bullets_html='<ul class="entry-body"><li>Norwegian at intermediate level for foreign-speaking adults.</li></ul>',
        ),
        sep(),
        timeline_row(
            '03/2011 - 01/2017',
            'Receptionist',
            'Experience',
            org='Olympiatoppen Sportshotell',
            location='Oslo, Norway',
            bullets_html=(
                '<ul class="entry-body"><li>Customer care and reception for individuals, groups, and organizations.</li>'
                '<li>Check-in/out, billing, kiosk sales, Protel and Opera booking systems.</li>'
                '<li>Day/night settlement reporting and crisis management.</li></ul>'
            ),
        ),
        sep(),
        timeline_row(
            '08/2020 - present',
            'Labor law studies (one-semester unit)',
            'Education',
            org='University of Oslo',
            location='Norway',
            card_class='education-card',
            bullets_html='<ul class="entry-body"><li>In progress.</li></ul>',
        ),
        sep(),
        timeline_row(
            '08/2014 - 06/2015',
            'Practical-Pedagogical Education',
            'Education',
            org='University of Oslo',
            location='Norway',
            card_class='education-card',
            bullets_html=(
                '<ul class="entry-body"><li>Authorized teacher: pre-school, primary, secondary, and adult level.</li></ul>'
            ),
        ),
        sep(),
        timeline_row(
            '08/2013 - 06/2014',
            'Spanish language and culture in Latin America',
            'Education',
            org='Telemark University College',
            location='Norway',
            card_class='education-card',
            bullets_html=spanish_bullets,
        ),
        sep(),
        timeline_row(
            '08/2010 - 06/2013',
            'BA International Development',
            'Education',
            org='Oslo and Akershus University College',
            location='Norway',
            card_class='education-card',
            bullets_html=ba_bullets,
        ),
        sep(),
        timeline_row(
            '08/2000 - 08/2008',
            'Scandinavian Languages and Literature (Norwegian)',
            'Education',
            org='University of Belgrade',
            location='Serbia',
            card_class='education-card',
            bullets_html='<ul class="entry-body"><li>Norwegian language and Scandinavian literature.</li></ul>',
        ),
    ]
    return '\n'.join(parts)


def build_all_role_cvs() -> dict[str, RoleCV]:
    """Role CVs for Frankfurt-area job search — teaching, counseling, admin, coordination."""
    return {
        cv.slug: cv
        for cv in (
            _role(
                'support-technician',
                'Customer Service & Reception CV',
                'Reception, front desk, customer care, and hospitality service roles.',
                'Customer Service & Reception Specialist',
                'Reception and customer-care professional with six years at Olympiatoppen Sportshotell Oslo. '
                'Experienced with check-in/out, billing, Protel and Opera booking systems, and multilingual guest communication. '
                'Based in Frankfurt am Main, Germany.',
                (
                    ('Customer & Reception', 'Check-in/out, billing, guest communication, crisis handling, group bookings'),
                    ('Systems & Office', 'Protel, Opera, Microsoft Office, settlement reporting, correspondence'),
                    ('Languages', 'Serbo-Croatian (native); Norwegian, English, Spanish; Russian (intermediate)'),
                ),
                skills_heading='PROFESSIONAL SKILLS',
                award_items=IVANA_AWARDS,
                recent_bullets=_DEFAULT_RECENT,
            ),
            _role(
                'it-trainee',
                'Education Trainee CV',
                'Trainee programs in education, social services, and program coordination.',
                'Education & Program Trainee',
                'University graduate with pedagogical authorization, career counseling experience, and NGO program work. '
                'Seeking structured trainee or entry programs in education, social services, or coordination in Frankfurt / Rhine-Main.',
                (
                    ('Education & Pedagogy', 'Authorized teacher, adult education, career counseling, lesson planning'),
                    ('Program & NGO', 'Course facilitation, stakeholder coordination, documentation, victim support'),
                    ('Digital literacy', 'Microsoft Office, Karriere Pro, Ad Opus; Python, Java, JavaScript (foundational)'),
                ),
                profile_highlights=(
                    '<strong>Education:</strong> BA International Development; Practical-Pedagogical Education (UiO).',
                    '<strong>Location:</strong> Frankfurt am Main — open to Rhine-Main and NRW.',
                ),
                award_items=IVANA_GRADUATE_AWARDS,
                recent_bullets=_DEFAULT_RECENT,
                interests='Teaching, languages, hiking, reading, community work.',
            ),
            _role(
                'commerzbank-trainee',
                'Graduate Program CV',
                'Graduate schemes, trainee programs, and Berufseinsteiger roles in Frankfurt.',
                'University Graduate — Trainee Program',
                'University graduate with BA International Development and authorized teacher training. '
                'People-focused professional background in counseling, reception, and multilingual communication. '
                'Seeking structured graduate or trainee programs in Frankfurt.',
                (
                    ('Core strengths', 'Analysis, documentation, stakeholder communication, reliability'),
                    ('Education', 'BA International Development; pedagogical authorization (UiO)'),
                    ('Professional experience', 'Career counseling, reception, teaching, NGO coordination'),
                ),
                accent=ACCENT_BLUE,
                accent_light=ACCENT_BLUE_LIGHT,
                verify_bg='#eff6ff',
                verify_border='#bfdbfe',
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_GRADUATE_AWARDS,
            ),
            _role(
                'python-developer',
                'Career Counselor CV',
                'Career counselor, guidance counselor, and adult education roles.',
                'Career Counselor & Educator',
                'Career counselor and authorized teacher with experience guiding foreign-speaking adults, '
                'designing learning pathways, and delivering Norwegian instruction at Hero Kompetanse and Caritas.',
                (
                    ('Counseling & guidance', 'Career counseling, course facilitation, learner support, Karriere Pro'),
                    ('Teaching', 'Norwegian and Spanish instruction; substitute teaching; adult education'),
                    ('Communication', 'Multilingual advisory, documentation, intercultural sensitivity'),
                ),
                accent=ACCENT_SKY,
                accent_light=ACCENT_SKY_LIGHT,
                verify_bg='#f0f9ff',
                verify_border='#bae6fd',
                skills_heading='PROFESSIONAL SKILLS',
                education_focus=_DEFAULT_EDUCATION_FOCUS,
                award_items=IVANA_AWARDS,
            ),
            _role(
                'fullstack-developer',
                'Language Teacher CV',
                'Spanish teacher, Norwegian teacher, substitute teacher, and Sprachkurs roles.',
                'Language Teacher',
                'Authorized teacher with Spanish substitute experience (grades 2–10) and Norwegian instruction '
                'for adults. Spanish studies with exchange in Costa Rica. Based in Frankfurt am Main.',
                (
                    ('Language teaching', 'Spanish (substitute grades 2–10), Norwegian (adult learners)'),
                    ('Pedagogy', 'Classroom management, lesson planning, authorized teacher (UiO)'),
                    ('Languages', 'Serbo-Croatian (native); Norwegian, English, Spanish (proficient)'),
                ),
                accent=ACCENT_INDIGO,
                accent_light=ACCENT_INDIGO_LIGHT,
                verify_bg='#eef2ff',
                verify_border='#c7d2fe',
                skills_heading='TEACHING & LANGUAGE SKILLS',
                award_items=IVANA_AWARDS,
            ),
            _role(
                'qa-engineer',
                'Training & Facilitation CV',
                'Trainer, workshop facilitator, and course coordinator roles.',
                'Trainer & Course Facilitator',
                'Experienced facilitator of courses on human trafficking awareness and career programs for adults. '
                'Strong documentation and structured delivery for training and NGO program roles.',
                (
                    ('Training delivery', 'Course facilitation, workshop coordination, awareness training'),
                    ('NGO & social programs', 'Hope for Justice — victim support and networking activities'),
                    ('Documentation', 'Reporting, correspondence, stakeholder communication, multilingual delivery'),
                ),
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_AWARDS,
            ),
            _role(
                'data-analyst',
                'Program Coordinator CV',
                'Program coordinator, project assistant, and NGO coordination roles.',
                'Program Coordinator',
                'Program professional with NGO experience coordinating course activities, supporting vulnerable groups, '
                'and managing reception operations. BA International Development with research fieldwork in Mexico.',
                (
                    ('Coordination', 'Course activities, scheduling, stakeholder communication, reporting'),
                    ('NGO & social work', 'Anti-trafficking programs, victim support, networking'),
                    ('Research background', 'International development, fieldwork, analytical writing'),
                ),
                accent=ACCENT_SKY,
                accent_light=ACCENT_SKY_LIGHT,
                verify_bg='#f0f9ff',
                verify_border='#bae6fd',
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_GRADUATE_AWARDS,
            ),
            _role(
                'devops-junior',
                'Office & Systems Support CV',
                'Office support, booking systems, and administrative technology roles.',
                'Office & Systems Support',
                'Reception professional experienced with Protel, Opera, and Microsoft Office in high-volume hospitality. '
                'Reliable with billing, booking workflows, and day/night settlement reporting.',
                (
                    ('Booking & office systems', 'Protel, Opera, Microsoft Office, billing, reporting'),
                    ('Service operations', 'Check-in/out, kiosk sales, guest communication, crisis handling'),
                    ('Reliability', 'Long tenure, shift work, accurate settlement documentation'),
                ),
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_AWARDS,
            ),
            _role(
                'customer-success',
                'Customer Success CV',
                'Customer success, client relations, and multilingual service roles.',
                'Customer Success Associate',
                'Multilingual customer-facing professional with hospitality reception background and career counseling experience. '
                'Strong at onboarding, communication, and resolving guest or client needs calmly.',
                (
                    ('Client relations', 'Guest and client communication, satisfaction focus, issue resolution'),
                    ('Service background', 'Six years reception at Olympiatoppen Sportshotell'),
                    ('Languages', 'Five languages for diverse client communication'),
                ),
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_AWARDS,
            ),
            _role(
                'technical-writer',
                'Documentation & Communication CV',
                'Documentation, correspondence, and knowledge-base roles.',
                'Documentation & Communication Specialist',
                'Clear writer and documenter with experience in advisory work, course materials, reception correspondence, '
                'and multilingual communication. BA International Development with dissertation research.',
                (
                    ('Writing & documentation', 'Reports, correspondence, course materials, professional tone'),
                    ('Communication', 'Multilingual advisory, teaching explanations, stakeholder updates'),
                    ('Office tools', 'Microsoft Office, email workflows, structured filing'),
                ),
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_AWARDS,
            ),
            _role(
                'graduate-trainee',
                'Graduate Trainee CV',
                'General graduate programs, trainee schemes, and Berufseinsteiger roles.',
                'University Graduate — Trainee',
                'Versatile university graduate with BA International Development, pedagogical authorization, and '
                'experience in teaching, counseling, reception, and NGO programs. Seeking trainee or graduate entry '
                'in Frankfurt, Rhine-Main, and NRW.',
                (
                    ('Core strengths', 'Analysis, documentation, intercultural communication, reliability'),
                    ('Education', 'BA International Development; pedagogical authorization (UiO); Spanish studies'),
                    ('Experience', 'Career counseling, teaching, reception, anti-trafficking program work'),
                ),
                accent=ACCENT_PURPLE,
                accent_light=ACCENT_PURPLE_LIGHT,
                verify_bg='#f5f3ff',
                verify_border='#ddd6fe',
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_GRADUATE_AWARDS,
                interests='Learning, languages, hiking, reading, community engagement.',
            ),
            _role(
                'project-coordinator',
                'Project Coordinator CV',
                'Project coordinator, program assistant, and Verwaltung coordination roles.',
                'Project Coordinator',
                'Organized coordinator with NGO program experience, course activity planning, and reception operations background. '
                'Comfortable with documentation, scheduling, and multilingual stakeholder communication.',
                (
                    ('Coordination', 'Planning, scheduling, documentation, meeting support, follow-up'),
                    ('Programs', 'Course activities, NGO networking, career program support'),
                    ('Communication', 'Multilingual, professional correspondence, client and guest relations'),
                ),
                accent=ACCENT_PURPLE,
                accent_light=ACCENT_PURPLE_LIGHT,
                verify_bg='#f5f3ff',
                verify_border='#ddd6fe',
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_GRADUATE_AWARDS,
            ),
            _role(
                'junior-analyst',
                'Junior Analyst CV',
                'Junior analyst, research assistant, and reporting support roles.',
                'Junior Analyst / Research Support',
                'BA International Development graduate with dissertation research on labor migration, fieldwork in Mexico, '
                'and strong documentation skills. Suitable for junior research, reporting, and analysis support roles.',
                (
                    ('Research & analysis', 'Literature review, fieldwork, report writing, data interpretation'),
                    ('Education', 'International development, migration studies, social sciences'),
                    ('Support skills', 'Documentation, multilingual communication, structured reporting'),
                ),
                accent=ACCENT_PURPLE,
                accent_light=ACCENT_PURPLE_LIGHT,
                verify_bg='#f5f3ff',
                verify_border='#ddd6fe',
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_GRADUATE_AWARDS,
            ),
            _role(
                'office-administrator',
                'Office Administrator CV',
                'Sachbearbeiter, office coordinator, administrative assistant, and Verwaltung roles.',
                'Office Administrator / Sachbearbeiter',
                'Organized administrator with reception, billing, booking systems, and documentation experience. '
                'Multilingual and reliable for back-office, coordination, and customer-facing admin in Germany.',
                (
                    ('Office & administration', 'Documentation, scheduling, correspondence, billing, data entry'),
                    ('Customer & service', 'Reception, client support, professional tone, crisis handling'),
                    ('Digital skills', 'Microsoft Office, Protel, Opera, email workflows'),
                ),
                accent=ACCENT_PURPLE,
                accent_light=ACCENT_PURPLE_LIGHT,
                verify_bg='#f5f3ff',
                verify_border='#ddd6fe',
                skills_heading='SKILLS & COMPETENCIES',
                education_focus=_DEFAULT_EDUCATION_FOCUS,
                award_items=IVANA_GRADUATE_AWARDS,
            ),
            _role(
                'sustainability-analyst',
                'Social Program Analyst CV',
                'Social program, NGO, and community program support roles.',
                'Social Program Support',
                'International development graduate with NGO experience in anti-trafficking programs and career counseling '
                'for vulnerable groups. Strong fit for social program, community, and NGO support roles.',
                (
                    ('Social programs', 'Anti-trafficking awareness, victim support, adult education'),
                    ('Development background', 'BA International Development; migration and labor research'),
                    ('Coordination', 'Course activities, documentation, stakeholder communication'),
                ),
                skills_heading='SKILLS & COMPETENCIES',
                education_focus='International Development, pedagogy, languages, and social program work.',
                award_items=IVANA_GRADUATE_AWARDS,
            ),
            _role(
                'werkstudent',
                'Werkstudent CV',
                'Werkstudent and working-student roles in Frankfurt.',
                'Werkstudent',
                'University-educated professional eligible for Werkstudent roles in education support, office admin, '
                'or program coordination. Combines teaching, counseling, and reception experience with flexible availability.',
                (
                    ('Study-compatible skills', 'Documentation, research support, teaching assistance, office tools'),
                    ('Work experience', 'Career counseling, reception, substitute teaching, NGO programs'),
                    ('Availability', 'Based in Frankfurt am Main; flexible for part-time roles'),
                ),
                skills_heading='SKILLS & STUDENT PROFILE',
                award_items=IVANA_GRADUATE_AWARDS,
            ),
            _role(
                'hr-assistant',
                'HR Assistant CV',
                'HR assistant, people operations, recruiting coordinator, and Personal roles.',
                'HR Assistant',
                'Multilingual graduate with people-facing experience in counseling, reception, teaching, and NGO support. '
                'Organized and discreet — suitable for HR coordination and people operations.',
                (
                    ('People & HR support', 'Candidate coordination mindset, scheduling, confidential handling'),
                    ('Communication', 'Multilingual advisory, professional correspondence, stakeholder support'),
                    ('Office skills', 'Documentation, Microsoft Office, process follow-up'),
                ),
                accent=ACCENT_PURPLE,
                accent_light=ACCENT_PURPLE_LIGHT,
                verify_bg='#f5f3ff',
                verify_border='#ddd6fe',
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_GRADUATE_AWARDS,
            ),
            _role(
                'research-assistant',
                'Research Assistant CV',
                'Research assistant, academic project support, and social research roles.',
                'Research Assistant',
                'BA International Development with dissertation research and fieldwork in Mexico. '
                'Teaching and documentation experience — support-oriented profile for university or NGO research teams.',
                (
                    ('Research support', 'Literature organisation, fieldwork, reporting, documentation'),
                    ('Academic background', 'International development, migration studies, social sciences'),
                    ('Communication', 'Multilingual, clear writing, teaching and explanation skills'),
                ),
                accent=ACCENT_PURPLE,
                accent_light=ACCENT_PURPLE_LIGHT,
                verify_bg='#f5f3ff',
                verify_border='#ddd6fe',
                skills_heading='SKILLS & COMPETENCIES',
                award_items=IVANA_GRADUATE_AWARDS,
            ),
        )
    }
