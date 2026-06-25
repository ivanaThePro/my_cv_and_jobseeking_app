"""CV variants for Ivana Jovic — shared education/experience, role-specific emphasis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from django.http import Http404

PERSON_NAME = 'Ivana Jovic'
PERSON_EMAIL = 'ivanatjovic@gmail.com'
PERSON_PHONE = '+47 47 313 788'
DEFAULT_LOCATION = 'Frankfurt am Main, Germany'
PERSON_LOCATION = DEFAULT_LOCATION

DEFAULT_CV_SLUG = 'general'

_LANGUAGES = (
    'Serbo-Croatian (native), Norwegian, English, Spanish (proficient), '
    'Russian (intermediate), Macedonian (basic)'
)

_AWARDS = (
    'Pedagogical authorization — University of Oslo (pre-school through adult level)',
    'Student role model grant — Reidar and Gunnar Holst\'s endowment (2011)',
    'First Aid Course — Oslo Red Cross (September 2014)',
    'Red Cross history and values — Oslo Red Cross (February 2014)',
    'Basic course in social care — Oslo Red Cross (February 2014)',
    'Course in gender-based violence and human trafficking — Anti-trafficking Centre, Belgrade (2007)',
)


@dataclass(frozen=True)
class SkillCategory:
    title: str
    items: tuple[str, ...]


@dataclass(frozen=True)
class ExperienceEntry:
    role: str
    org: str
    date: str
    bullets: tuple[str, ...] = ()


@dataclass(frozen=True)
class EducationEntry:
    title: str
    org: str
    date: str
    note: str = ''


@dataclass(frozen=True)
class CVProfile:
    slug: str
    label: str
    headline: str
    subtitle: str
    summary: str
    highlights: tuple[str, ...]
    closing: str
    skill_categories: tuple[SkillCategory, ...]
    print_summary: str
    print_summary_points: tuple[str, ...]
    print_skill_categories: tuple[SkillCategory, ...]
    pdf_filename: str
    description: str = ''
    location: str = DEFAULT_LOCATION
    experience: tuple[ExperienceEntry, ...] = ()
    additional_experience: tuple[ExperienceEntry, ...] = ()
    voluntary_work: tuple[ExperienceEntry, ...] = ()
    education_entries: tuple[EducationEntry, ...] = ()
    references: tuple[str, ...] = ()
    references_note: str = 'Upon request'
    hobbies: tuple[str, ...] = ()
    languages: str = _LANGUAGES
    awards: tuple[str, ...] = _AWARDS
    show_full_courses: bool = False
    show_additional_experience: bool = False
    web_template: str = 'cvapp/cv_general.html'
    print_template: str = 'cvapp/cv_print_general.html'


_EXPERIENCE = (
    ExperienceEntry(
        'Career counselor / Teacher',
        'Hero Kompetanse — Norway',
        '09/2020 - present',
        ('Career counseling and teaching Norwegian to foreign-speaking adults',),
    ),
    ExperienceEntry(
        'Teacher Substitute',
        'Rudolf Steiner School — Lørenskog, Norway',
        '11/2014 - present',
        ('Spanish instruction grades 2–10; classroom management',),
    ),
    ExperienceEntry(
        'Teacher',
        'Hersleb High School — Norway',
        '01/2020 - 06/2020',
        ('Taught Spanish language',),
    ),
    ExperienceEntry(
        'Case worker / Trainer',
        'Hope for Justice — Norway',
        '02/2017 - 07/2018',
        (
            'Networking and course activities on human trafficking',
            'Support work with victims of human trafficking',
        ),
    ),
    ExperienceEntry(
        'Receptionist',
        'Olympiatoppen Sportshotell — Oslo, Norway',
        '03/2011 - 01/2017',
        (
            'Customer care and reception for individuals, groups, and organizations',
            'Check-in/out, billing, kiosk sales, guest communication',
            'Online booking system management and day/night settlement reporting',
            'Crisis management (fire, theft, damage)',
        ),
    ),
    ExperienceEntry(
        'Teacher',
        'Caritas — Norway',
        '08/2015 - 11/2016',
        ('Norwegian at intermediate level for foreign-speaking adults',),
    ),
)

_EDUCATION = (
    EducationEntry(
        'Labor law (one-semester unit)',
        'University of Oslo, Norway',
        '08/2020 - present',
    ),
    EducationEntry(
        'Practical-Pedagogical Education (one-year unit)',
        'University of Oslo, Norway',
        '08/2014 - 06/2015',
        'Authorized teacher: pre-school, primary, secondary, and adult level',
    ),
    EducationEntry(
        'Spanish language and culture in Latin America',
        'Telemark University College, Norway',
        '08/2013 - 06/2014',
        'Exchange: Costa Rican Language Academy, San José (6 months)',
    ),
    EducationEntry(
        'BA International Development',
        'Oslo and Akershus University College, Norway',
        '08/2010 - 06/2013',
        'Dissertation on migrant worker exploitation in Gulf countries; fieldwork in Mexico',
    ),
    EducationEntry(
        'Scandinavian Languages and Literature (Norwegian)',
        'University of Belgrade, Serbia',
        '08/2000 - 08/2008',
    ),
)

_SKILLS_CORE = (
    SkillCategory('Languages', (
        'Serbo-Croatian (native)', 'Norwegian, English, Spanish (proficient)',
        'Russian (intermediate)', 'Macedonian (basic)',
    )),
    SkillCategory('Teaching & counseling', (
        'Career guidance', 'Norwegian and Spanish instruction',
        'Adult education', 'Classroom management', 'Substitute teaching',
    )),
    SkillCategory('Professional strengths', (
        'Intercultural communication', 'Customer care', 'Training facilitation',
        'Documentation and reporting', 'Crisis handling',
    )),
    SkillCategory('Computer skills', (
        'Microsoft Office', 'Protel and Opera booking systems',
        'Ad Opus', 'Karriere Pro', 'Python, Java, JavaScript (foundational)', 'Flutter/Dart (intro)',
    )),
)

_SUMMARY_BASE = (
    'Professional with an interdisciplinary educational background and experience in '
    'career counseling, Norwegian and Spanish teaching, reception, and anti-trafficking '
    'support work. Strong intercultural understanding from study, work, and living in '
    'multiple countries. Based in Frankfurt am Main, Germany.'
)

_HIGHLIGHTS_BASE = (
    'Interdisciplinary education across international development, pedagogy, and languages',
    'Five languages with excellent communication skills',
    'Authorized teacher with classroom and adult-education experience',
    'Reception, customer care, and program coordination background',
)


def _profiles() -> dict[str, CVProfile]:
    base_kwargs = dict(
        experience=_EXPERIENCE,
        education_entries=_EDUCATION,
        skill_categories=_SKILLS_CORE,
        print_skill_categories=_SKILLS_CORE,
        languages=_LANGUAGES,
        awards=_AWARDS,
        references_note='Upon request',
    )
    return {
        'general': CVProfile(
            slug='general',
            label='Career Counselor & Teacher',
            headline='Career Counselor & Teacher',
            subtitle='Education · Counseling · Languages',
            description='Career counseling, language teaching, and adult education.',
            summary=_SUMMARY_BASE,
            highlights=_HIGHLIGHTS_BASE,
            closing=(
                'Combines pedagogical training, language expertise, and people-focused '
                'experience for education, counseling, and service roles in the Frankfurt area.'
            ),
            print_summary=(
                'Career counselor and teacher with pedagogical authorization, language '
                'instruction experience, and a strong customer-service background.'
            ),
            print_summary_points=(
                '<strong>Teaching:</strong> Norwegian and Spanish for children and adults',
                '<strong>Counseling:</strong> Career guidance at Hero Kompetanse',
                '<strong>Location:</strong> Frankfurt am Main, Germany',
            ),
            pdf_filename='Ivana_Jovic_CV.pdf',
            **base_kwargs,
        ),
        'backend': CVProfile(
            slug='backend',
            label='Career Counselor & Educator',
            headline='Career Counselor & Educator',
            subtitle='Karriereveiledning · Voksenopplæring',
            description='Career counseling and adult education roles in the Frankfurt / Rhine-Main area.',
            summary=_SUMMARY_BASE,
            highlights=_HIGHLIGHTS_BASE,
            closing=(
                'Focused on guidance, adult learning, and structured support for diverse learners.'
            ),
            print_summary=(
                'Career counselor and adult-education professional with authorized teacher '
                'training and long experience in Norwegian instruction and guidance.'
            ),
            print_summary_points=(
                '<strong>Counseling:</strong> Career guidance and course facilitation',
                '<strong>Teaching:</strong> Norwegian for adults; Spanish substitute teaching',
                '<strong>Pedagogy:</strong> Practical-Pedagogical Education, University of Oslo',
            ),
            pdf_filename='Ivana_Jovic_Counselor_CV.pdf',
            **base_kwargs,
        ),
        'fullstack': CVProfile(
            slug='fullstack',
            label='Language Teacher',
            headline='Language Teacher',
            subtitle='Spanish · Norwegian · Adult education',
            description='Spanish and Norwegian teaching — substitute and adult programs.',
            summary=(
                'Language teacher with classroom and adult-education experience in Spanish '
                'and Norwegian. Pedagogical authorization from the University of Oslo. '
                'Based in Frankfurt am Main, Germany.'
            ),
            highlights=(
                'Substitute Spanish teacher (grades 2–10) at Rudolf Steiner School',
                'Norwegian instruction for foreign-speaking adults at Hero Kompetanse and Caritas',
                'Spanish language and culture studies with exchange in Costa Rica',
            ),
            closing='Brings structured classroom management and intercultural sensitivity to language programs.',
            print_summary='Language teacher — Spanish and Norwegian — with authorized pedagogical training.',
            print_summary_points=(
                '<strong>Spanish:</strong> Substitute teaching grades 2–10',
                '<strong>Norwegian:</strong> Adult learners and career-program participants',
                '<strong>Education:</strong> Telemark University College; University of Oslo pedagogy',
            ),
            pdf_filename='Ivana_Jovic_Language_Teacher_CV.pdf',
            **base_kwargs,
        ),
        'software-engineer': CVProfile(
            slug='software-engineer',
            label='Education & Program Professional',
            headline='Education & Program Professional',
            subtitle='Training · Coordination · NGO experience',
            description='Program coordination, training delivery, and education-sector roles.',
            summary=(
                'Education and program professional with experience designing and delivering '
                'training on human trafficking, coordinating course activities, and supporting '
                'vulnerable groups. BA International Development. Based in Frankfurt am Main.'
            ),
            highlights=(
                'Anti-trafficking casework and awareness training at Hope for Justice',
                'Career counseling and course design at Hero Kompetanse',
                'International development background with field research in Mexico',
            ),
            closing='Suited to NGO, education, and social-program roles requiring coordination and communication.',
            print_summary='Education and program professional with NGO, counseling, and training experience.',
            print_summary_points=(
                '<strong>Programs:</strong> Course activities and stakeholder coordination',
                '<strong>NGO:</strong> Hope for Justice — victim support and training',
                '<strong>Degree:</strong> BA International Development',
            ),
            pdf_filename='Ivana_Jovic_Education_Program_CV.pdf',
            **base_kwargs,
        ),
        'technical-support': CVProfile(
            slug='technical-support',
            label='Customer Service & Reception',
            headline='Customer Service & Reception Specialist',
            subtitle='Front desk · Hospitality · Multilingual service',
            description='Reception, customer care, and front-office roles.',
            summary=(
                'Reception and customer-care professional with six years at Olympiatoppen '
                'Sportshotell Oslo: check-in/out, billing, booking systems (Protel, Opera), '
                'and crisis management. Multilingual communication. Based in Frankfurt am Main.'
            ),
            highlights=(
                'Long hospitality reception experience with groups and organizations',
                'Online booking, billing, and settlement reporting',
                'Calm crisis handling — fire, theft, and damage incidents',
            ),
            closing='Reliable front-office professional for hotels, sport facilities, and service organizations.',
            print_summary='Reception and customer-service specialist with hotel and booking-system experience.',
            print_summary_points=(
                '<strong>Reception:</strong> Olympiatoppen Sportshotell (2011–2017)',
                '<strong>Systems:</strong> Protel, Opera, Microsoft Office',
                '<strong>Languages:</strong> Five languages for guest communication',
            ),
            pdf_filename='Ivana_Jovic_Customer_Service_CV.pdf',
            **base_kwargs,
        ),
        'manual': CVProfile(
            slug='manual',
            label='General Professional CV',
            headline='Ivana Jovic',
            subtitle='Education · Languages · Service',
            description='Full professional profile — teaching, counseling, reception, and languages.',
            summary=_SUMMARY_BASE,
            highlights=_HIGHLIGHTS_BASE,
            closing=(
                'Open to teaching, counseling, reception, coordination, and multilingual '
                'service roles in Frankfurt, Rhine-Main, and NRW.'
            ),
            print_summary=_SUMMARY_BASE,
            print_summary_points=(
                '<strong>Education:</strong> BA International Development; pedagogical authorization',
                '<strong>Experience:</strong> Teaching, counseling, reception, NGO work',
                '<strong>Languages:</strong> Serbo-Croatian (native) plus four additional languages',
            ),
            pdf_filename='Ivana_Jovic_General_CV.pdf',
            **base_kwargs,
        ),
    }


_PROFILES: dict[str, CVProfile] | None = None


def _load_profiles() -> dict[str, CVProfile]:
    global _PROFILES
    if _PROFILES is None:
        _PROFILES = _profiles()
    return _PROFILES


def list_cv_profiles() -> list[CVProfile]:
    return list(_load_profiles().values())


def get_cv_profile(slug: str | None = None) -> CVProfile:
    key = (slug or DEFAULT_CV_SLUG).strip().lower()
    profile = _load_profiles().get(key)
    if profile is None:
        raise Http404(f'CV profile not found: {key}')
    return profile


def iter_cv_profiles() -> Iterator[CVProfile]:
    yield from list_cv_profiles()
