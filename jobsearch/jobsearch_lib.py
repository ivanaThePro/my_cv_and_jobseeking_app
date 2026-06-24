"""Shared library for job matching pipeline and Streamlit UI."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from datetime import datetime
from html import unescape
from pathlib import Path

import requests

DEFAULT_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

SCRIPT_DIR = Path(__file__).resolve().parent
JOBS_CACHE_PATH = SCRIPT_DIR / "data" / "jobs_cache.json"
JOBS_LIVE_PATH = SCRIPT_DIR / "data" / "jobs_cache_live.json"
SCORED_JOBS_PATH = SCRIPT_DIR / "data" / "scored_jobs.json"
SOURCE_DIAGNOSTICS_PATH = SCRIPT_DIR / "data" / "source_diagnostics.json"
PROFILE_PATH = SCRIPT_DIR / "profile.json"
CANDIDATE_PROFILE_ID = "ivana_jovic_v1"
CANDIDATE_NAME = "Ivana Jovic"
LEGACY_MATCH_MARKERS = re.compile(
    r"\b(earmyas|measho|gebre|addis ababa|linnaeus|uppsala|lule[aå]|"
    r"dell\b|dell awards?|199\s*ects|~199|computer science degree|"
    r"technical support awards?|ethiopia\b|stem bachelor|software design coursework|"
    r"data management.*coursework)\b",
    re.IGNORECASE,
)
CV_PROFILE_PATH = SCRIPT_DIR / "data" / "cv_profile.json"
QUALIFICATIONS_PATH = SCRIPT_DIR / "data" / "qualifications.json"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
SCORE_MODEL = os.getenv("MISTRAL_SCORE_MODEL", "mistral-small-latest")
MATERIALS_MODEL = os.getenv("MISTRAL_MATERIALS_MODEL", "mistral-small-latest")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


# Tunable via .env — lower values surface more jobs on the apply list.
MATCH_MODE = os.getenv("JOB_MATCH_MODE", "broad").strip().lower()  # strict | broad
APPLY_SCORE_MIN = _env_int("JOB_APPLY_SCORE_MIN", 45)
APPLY_MUST_RATIO_MIN = _env_float("JOB_APPLY_RATIO_MIN", 0.32)
REVIEW_SCORE_MIN = _env_int("JOB_REVIEW_SCORE_MIN", 38)
REVIEW_MUST_RATIO_MIN = _env_float("JOB_REVIEW_RATIO_MIN", 0.25)
BROAD_SCORE_MIN = _env_int("JOB_BROAD_SCORE_MIN", 50)
PREFILTER_MODE = os.getenv("JOB_PREFILTER_MODE", "wide").strip().lower()

TARGET_CITY_KEYWORDS = re.compile(
    r"\b(frankfurt|hanau|cologne|köln|koeln|bonn|düsseldorf|dusseldorf|duesseldorf|"
    r"offenbach|mainz|wiesbaden|darmstadt|leverkusen|bergisch|ruhrgebiet|"
    r"eschborn|neuss|kronberg|oberursel|bad homburg|hockenheim|maintal|"
    r"rüdesheim|ruedesheim|ingelheim|troisdorf|siegburg|pulheim|monheim)\b",
    re.IGNORECASE,
)
TARGET_REGION_BROAD = re.compile(
    r"\b(nrw|north rhine|hesse|hessen|main-kinzig|ruhr|rhine-main|köln-bonn|nordrhein)\b",
    re.IGNORECASE,
)

US_EXCLUDE_KEYWORDS = re.compile(
    r"\b(united states|u\.?s\.?\s*a\.?|usa\b|u\.s\.-based|america only|"
    r"residents of (alabama|florida|illinois|indiana|kansas|michigan|new york|ohio|texas)|"
    r"remote \(united states\)|\(united states\))\b",
    re.IGNORECASE,
)

REMOTE_GERMANY_KEYWORDS = re.compile(
    r"\b(remote.*(germany|deutschland|eu|europe)|germany.*remote|deutschland.*remote|"
    r"europe.*remote|remote.*frankfurt|remote.*köln|remote.*cologne|"
    r"work from home.*germany|hybrid.*frankfurt|hybrid.*köln|hybrid.*cologne)\b",
    re.IGNORECASE,
)

# Other German cities outside the target Rhine-Main / NRW focus (exclude unless target area also named)
OTHER_GERMANY_CITIES = re.compile(
    r"\b(berlin|munich|münchen|muenchen|hamburg|stuttgart|leipzig|dresden|nuremberg|"
    r"nürnberg|nuernberg|bremen|hannover|essen|dortmund|bochum|bielefeld|mannheim|"
    r"karlsruhe|augsburg|kiel|lübeck|luebeck|magdeburg|potsdam|rostock|saarbrücken|"
    r"saarbruecken|freiburg|regensburg|heidelberg|ulm|konstanz)\b",
    re.IGNORECASE,
)

INTERMEDIARY_BOARD_HOST = re.compile(
    r"(arbeitnow\.com|stepstone\.de|indeed\.com|jooble\.org|"
    r"linkedin\.com|xing\.com|google\.com|europa\.eu/eures|eures\.europa\.eu)",
    re.IGNORECASE,
)

HARD_GERMAN_REQUIRED = re.compile(
    r"\b(muttersprache|native german|deutsch als muttersprache|"
    r"verhandlungssicher(?:e|es|en)?\s+deutsch|fließend(?:e|es|en)?\s+deutsch|"
    r"deutsch\s+(?:auf\s+)?(?:c1|c2)(?:[\s-]?niveau)?|german\s+(?:c1|c2)|"
    r"deutschkenntnisse.*(?:c1|c2|muttersprache|verhandlungssicher))\b",
    re.IGNORECASE,
)

TRAINEE_PROGRAM_SIGNAL = re.compile(
    r"\b(traineeprogramm|trainee program|graduate program|absolventenprogramm|"
    r"einstiegsprogramm|entry program|berufseinsteiger)\b",
    re.IGNORECASE,
)

WERKSTUDENT_SIGNAL = re.compile(
    r"\b(werkstudent|working student|studentische|student assistant|praktikant)\b",
    re.IGNORECASE,
)

SENIOR_EXCLUDE = re.compile(
    r"\b(vice president|\bvp\b|director of|head of|chief |c-level|"
    r"\bsenior\b|\blead\b|chapter lead|teamleiter|teamleitung|"
    r"10\+\s*years|15\+\s*years|20\+\s*years|principal engineer|staff engineer|"
    r"executive director|senior director|experte\b|oberärzt)\b",
    re.IGNORECASE,
)

JUNIOR_SIGNAL = re.compile(
    r"\b(junior|entry[\s-]?level|associate|graduate|trainee|intern|werkstudent|"
    r"praktikant|working student|0-2 years|1-2 years|2 years)\b",
    re.IGNORECASE,
)

IRRELEVANT_ROLE = re.compile(
    r"\b(registered nurse|physician|surgeon|dentist|attorney|lawyer|"
    r"licensed clinical|medical doctor|md required|cpa required|"
    r"facharzt|oberärzt|gutachter.*medizin|altenpfleger|pflegefach|"
    r"pflegehelfer|betreuungskraft|intensivpflege|operationssaal|"
    r"forklift operator|warehouse picker|delivery driver|cleaner|cashier|"
    r"staplerfahrer|gabelstapler|lagerlogistik|fachkraft.*lager|"
    r"elektroniker.*automatisierung|haustechniker|heizung.*sanitär|"
    r"servicekraft.*gastronom|frühstücksservice|gastgewerbe|"
    r"putzkraft|reinigungskraft|gebäudereinigung|hausmeister|janitor|"
    r"security guard|night watchman|judo|karate|yoga instructor|"
    r"buddhist|buddhism|hindu priest|hinduism teacher|religion teacher|"
    r"religious teacher|imam\b|pastor|missionary|"
    r"theology|worship leader)\b",
    re.IGNORECASE,
)

NON_IT_JOB_BLOB = re.compile(
    r"\b(judo|karate|yoga|buddhis|hindu temple|mosque|church pastor|"
    r"religious education|theology|worship|cleaning company|gebäudereinigung|"
    r"reinigungsfirma|putzservice|hausmeister(?!.*(?:it|software))|"
    r"facility cleaner|domestic worker|childcare|kindergarten teacher|"
    r"hairdresser|friseur|baker|bäcker|chef cook|kitchen porter)\b",
    re.IGNORECASE,
)

BACHELOR_DEGREE_SIGNAL = re.compile(
    r"\b(bachelor|bachelor'?s|bachelorabschluss|bachelor degree|university degree|"
    r"hochschulabschluss|hochschulstudium|abgeschlossenes studium|studium|"
    r"university graduate|college degree|absolvent|graduate degree|"
    r"berufseinsteiger|career starter|first job|entry.?level|einsteiger)\b",
    re.IGNORECASE,
)

BROAD_BACHELOR_TITLE = re.compile(
    r"\b(coordinator|koordinator|analyst|analystin|assistant|assistent|"
    r"associate|sachbearbeiter|referent|specialist|spezialist|berater|"
    r"consultant|project manager|projektmanager|projektkoordinator|"
    r"trainee|praktikant|werkstudent|graduate|absolvent|junior|"
    r"officer|administrator|fachkraft)\b",
    re.IGNORECASE,
)

RELATED_FIELD_SIGNAL = re.compile(
    r"\b(software|python|it\b|tech|digital|data|analyst|support|helpdesk|"
    r"project|coordinator|research|science|stem|environment|sustainability|"
    r"climate|energy|engineering|mathematics|business|customer|operations|"
    r"administration|documentation|quality|testing|cloud|database|"
    r"integration|implementation|consulting|multilingual|ngo|program|"
    r"office|büro|verwaltung|sachbearbeit|kommunikation|communication|"
    r"marketing|planning|organisation|organization|compliance|finance|"
    r"controlling|procurement|personalwesen|human resources|beratung|"
    r"education|bildung|training|schulung|knowledge|prozess|process)\b",
    re.IGNORECASE,
)

MANUAL_LABOR_TITLE = re.compile(
    r"\b(cleaner|reinigung|lagerist|warehouse|fahrer|driver|bauarbeiter|"
    r"produktionsmitarbeiter|pflegehelfer|gärtner|kellner|köchin|koch|"
    r"monteur|schweißer|maurer|friseur|bäcker)\b",
    re.IGNORECASE,
)

KNOWLEDGE_WORK_SIGNAL = re.compile(
    r"\b(office|büro|administration|verwaltung|sachbearbeit|koordination|"
    r"analyst|beratung|consulting|customer|kundenbetreuung|project|projekt|"
    r"research|forschung|marketing|communication|kommunikation|planning|"
    r"organisation|organization|data|digital|quality|qualität|process|prozess|"
    r"compliance|finance|finanz|controlling|procurement|einkauf|personal|"
    r"hr\b|human resources|wissensarbeit|kenntnisse|hochschule|studium)\b",
    re.IGNORECASE,
)

COURSE_SUBJECT_SIGNAL = re.compile(
    r"\b(mathemat|statistic|statistik|physics|physik|calculus|algebra|"
    r"environment|umwelt|sustainab|nachhaltig|climate|klima|energy|energie|"
    r"renewable|erneuerbar|ecolog|engineering|ingenieur|"
    r"data analys|datenanalys|reporting|documentation|dokumentation|"
    r"project manag|projektmanag|coordination|koordinat|research|forschung|"
    r"stem\b|science|laborator|labor|quality|qualität|process|prozess|"
    r"compliance|customer service|kundenservice|multilingual|mehrsprachig|"
    r"communication|kommunikation|teaching|education|bildung|training|"
    r"finance assistant|controlling assistant|procurement|einkauf|"
    r"hr assistant|marketing assistant|sales support|consulting|beratung|"
    r"python|sql|database|analyst|analystin|office|büro|administration)\b",
    re.IGNORECASE,
)

ENGLISH_OUTPUT_RULE = (
    "LANGUAGE: Every text field in your JSON response MUST be written in English only. "
    "Translate German job requirements into English in requirement, evidence, reasoning, "
    "required_met, required_missing, and cultural_fit_summary. Keep company names unchanged."
)

GERMAN_TEXT_SIGNAL = re.compile(
    r"(ä|ö|ü|ß|\b(und|oder|sowie|mit|im|am|an|zu|von|für|aber|auch|als|bei|"
    r"mindestens|erfolgreich|abgeschlossen|studium|informatik|mathematik|"
    r"berufserfahrung|kenntnisse|voraussetzung|qualifikation|aufgaben|"
    r"verantwortung|wir bieten|sie haben|müssen|können|deutschkenntnisse|"
    r"englischkenntnisse|hochschulabschluss|berufseinsteiger|fähigkeit|"
    r"interesse|gängigen|programmiersprachen|bspw|leistungen|vergleichbare|"
    r"eigenverantwortlich|lösungsorientierte|arbeitsweise|engagement|"
    r"projektvorgehensweisen|wirtschafts|softwareentwicklung)\b)",
    re.IGNORECASE,
)

# German job-posting phrases → English (longest / most specific first).
_GERMAN_PHRASE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sehr\s+gute[n]?\s+deutsch-\s*und\s+gute[n]?\s+englischkenntnisse?\s+in\s+wort\s+und\s+schrift", re.I),
     "very good German and good English written and spoken skills"),
    (re.compile(r"sehr\s+gute[n]?\s+deutsch-\s*und\s+gute[n]?\s+englisch", re.I),
     "very good German and good English"),
    (re.compile(r"fähigkeit\s+im\s+team,?\s*aber\s+auch\s+eigenverantwortlich\s+zu\s+arbeiten", re.I),
     "ability to work in a team and also independently"),
    (re.compile(r"interesse\s+an\s+agilen\s+projektvorgehensweisen", re.I),
     "interest in agile project methodologies"),
    (re.compile(r"lösungsorientierte\s+arbeitsweise\s+und\s+engagement", re.I),
     "solution-oriented work style and commitment"),
    (re.compile(r"university\s+degree\s+mit\s+guten\s+leistungen\s+in\s+\(wirtschafts-\)\s*informatik,?\s*mathematik\s+oder\s+vergleichbare\s+kenntnisse", re.I),
     "university degree with good grades in (business) informatics, mathematics, or comparable skills"),
    (re.compile(r"softwareentwicklungs?kenntnisse?\s+(?:in\s+)?gängigen\s+programmiersprachen", re.I),
     "software development knowledge of common programming languages"),
    (re.compile(r"softwareentwicklungs?knowledge\s+of\s+gängigen\s+programmiersprachen", re.I),
     "software development knowledge of common programming languages"),
    (re.compile(r"abgeschlossenes?\s+(hochschul)?studium", re.I), "completed university degree"),
    (re.compile(r"hochschulabschluss", re.I), "university degree"),
    (re.compile(r"mit\s+guten\s+leistungen", re.I), "with good grades"),
    (re.compile(r"vergleichbare\s+kenntnisse", re.I), "comparable skills"),
    (re.compile(r"\(wirtschafts-\)\s*informatik", re.I), "(business) informatics"),
    (re.compile(r"wirtschaftsinformatik", re.I), "business informatics"),
    (re.compile(r"softwareentwicklung", re.I), "software development"),
    (re.compile(r"programmiersprachen", re.I), "programming languages"),
    (re.compile(r"gängigen", re.I), "common"),
    (re.compile(r"\bbspw\.", re.I), "e.g."),
    (re.compile(r"berufserfahrung", re.I), "professional experience"),
    (re.compile(r"erste\s+berufserfahrung", re.I), "first professional experience"),
    (re.compile(r"kenntnisse?\s+in", re.I), "knowledge of"),
    (re.compile(r"sehr\s+gute[n]?\s+deutschkenntnisse", re.I), "very good German skills"),
    (re.compile(r"gute[n]?\s+englischkenntnisse", re.I), "good English skills"),
    (re.compile(r"wort\s+und\s+schrift", re.I), "written and spoken"),
    (re.compile(r"teamfähigkeit", re.I), "teamwork skills"),
    (re.compile(r"eigenverantwortlich", re.I), "independently"),
    (re.compile(r"eigeninitiative", re.I), "self-initiative"),
    (re.compile(r"analytische\s+fähigkeiten", re.I), "analytical skills"),
    (re.compile(r"agilen\s+projektvorgehensweisen", re.I), "agile project methodologies"),
    (re.compile(r"interesse\s+an", re.I), "interest in"),
    (re.compile(r"fähigkeit\s+im\s+team", re.I), "ability to work in a team"),
    (re.compile(r"lösungsorientierte\s+arbeitsweise", re.I), "solution-oriented work style"),
    (re.compile(r"\binformatik\b", re.I), "computer science"),
    (re.compile(r"\bmathematik\b", re.I), "mathematics"),
    (re.compile(r"\bund\b", re.I), "and"),
    (re.compile(r"\boder\b", re.I), "or"),
    (re.compile(r"\bmit\b", re.I), "with"),
    (re.compile(r"\bzu\b", re.I), "to"),
    (re.compile(r"teilweise\s+erfüllt", re.I), "partially met"),
    (re.compile(r"nicht\s+erfüllt", re.I), "not met"),
    (re.compile(r"erfüllt", re.I), "met"),
]

_GERMAN_WORD_MAP = {
    "kenntnisse": "skills",
    "kenntnis": "knowledge",
    "fähigkeit": "ability",
    "fähigkeiten": "abilities",
    "voraussetzung": "requirement",
    "voraussetzungen": "requirements",
    "aufgaben": "tasks",
    "verantwortung": "responsibility",
    "berufseinsteiger": "career starter",
    "hochschulabsolvent": "university graduate",
    "studium": "degree studies",
    "leistungen": "grades",
    "vergleichbare": "comparable",
    "gängigen": "common",
    "eigenverantwortlich": "independently",
    "lösungsorientierte": "solution-oriented",
    "arbeitsweise": "work style",
    "engagement": "commitment",
    "deutschkenntnisse": "German skills",
    "englischkenntnisse": "English skills",
}


def _looks_german(text: str) -> bool:
    if not text or len(text.strip()) < 4:
        return False
    if re.search(r"[äöüß]", text, re.I):
        return True
    return bool(GERMAN_TEXT_SIGNAL.search(text))


def _translate_phrase_to_english(text: str) -> str:
    if not text:
        return text
    out = text
    for pattern, replacement in _GERMAN_PHRASE_MAP:
        out = pattern.sub(replacement, out)
    # Fix common AI hybrids (German stem glued to English phrase).
    out = re.sub(
        r"softwareentwicklungs?(?:kenntnisse|knowledge)\s+of",
        "software development knowledge of",
        out,
        flags=re.I,
    )
    out = re.sub(r"englisch(?:kenntnisse|knowledge)\s+of", "English skills in", out, flags=re.I)
    out = re.sub(r"deutsch-\s*und\s+gute[n]?\s+englisch", "German and good English", out, flags=re.I)
    if _looks_german(out):
        for de, en in _GERMAN_WORD_MAP.items():
            out = re.sub(rf"\b{re.escape(de)}\b", en, out, flags=re.I)
    return re.sub(r"\s{2,}", " ", out).strip()


_TITLE_EN_PHRASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"werkstudent(?:in)?", re.I), "Working Student"),
    (re.compile(r"praktikant(?:in)?", re.I), "Intern"),
    (re.compile(r"trainee(?:programm)?", re.I), "Trainee"),
    (re.compile(r"ausbildung", re.I), "Apprenticeship"),
    (re.compile(r"entwickler(?:in)?", re.I), "Developer"),
    (re.compile(r"ingenieur(?:in)?", re.I), "Engineer"),
    (re.compile(r"sachbearbeiter(?:in)?", re.I), "Administrator"),
    (re.compile(r"mitarbeiter(?:in)?", re.I), "Associate"),
    (re.compile(r"datenmanager(?:in)?", re.I), "Data Manager"),
    (re.compile(r"daten[\-\s]?governance", re.I), "Data Governance"),
    (re.compile(r"it[\-\s]?support", re.I), "IT Support"),
    (re.compile(r"software[\-\s]?entwickler(?:in)?", re.I), "Software Developer"),
    (re.compile(r"full[\-\s]?stack", re.I), "Full Stack"),
    (re.compile(r"berufseinsteiger", re.I), "Entry Level"),
    (re.compile(r"hochschulabsolvent(?:in)?", re.I), "Graduate"),
]


def english_display_title(title: str) -> str:
    """Short English-friendly job title for lists (strips m/w/d, translates common German role words)."""
    t = (title or "").strip()
    if not t:
        return "Role"
    t = re.sub(
        r"\s*[\(\[](?:m/?w/?d|w/?m/?d|d/m/w|mwd|all genders|divers|alle geschlechter)[\)\]]\s*",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r":in\b", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip()
    for pattern, replacement in _TITLE_EN_PHRASES:
        t = pattern.sub(replacement, t)
    if _looks_german(t):
        t = _translate_phrase_to_english(t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -|")
    return t or title


def localize_match_for_display(match: dict) -> dict:
    """Return a copy of match analysis with English display strings."""
    if not isinstance(match, dict) or not match:
        return match
    out = json.loads(json.dumps(match, ensure_ascii=False))

    def _fix_str(val: str) -> str:
        if not val:
            return val
        if not _looks_german(val):
            return val
        return _translate_phrase_to_english(val)

    for key in (
        "reasoning",
        "cultural_fit_summary",
        "title_vs_requirements_note",
        "logistics_notes",
        "role_category",
    ):
        if isinstance(out.get(key), str):
            out[key] = _fix_str(out[key])

    for key in ("required_met", "required_missing", "preferred_met", "dealbreakers"):
        if isinstance(out.get(key), list):
            out[key] = [_fix_str(str(x)) for x in out[key]]

    for row in out.get("requirements_analysis") or []:
        if not isinstance(row, dict):
            continue
        for field in ("requirement", "evidence", "section"):
            if isinstance(row.get(field), str):
                row[field] = _fix_str(row[field])
        status = str(row.get("status") or "").lower()
        row["status"] = {
            "met": "met",
            "partial": "partial",
            "missing": "missing",
            "erfüllt": "met",
            "teilweise": "partial",
            "fehlt": "missing",
        }.get(status, status)

    return out


def _match_german_sample(match: dict) -> str:
    parts: list[str] = []
    for row in match.get("requirements_analysis") or []:
        if isinstance(row, dict):
            parts.append(str(row.get("requirement") or ""))
    parts.extend(str(x) for x in (match.get("required_met") or [])[:4])
    parts.extend(str(x) for x in (match.get("required_missing") or [])[:4])
    parts.append(str(match.get("reasoning") or ""))
    return " ".join(p for p in parts if p)


def ensure_match_english(api_key: str, match: dict) -> dict:
    """Force English analysis text; uses AI re-write only when output still looks German."""
    match = localize_match_for_display(match)
    sample = _match_german_sample(match)
    if not _looks_german(sample):
        return match
    system = (
        "Translate this job-match JSON into English. Keep JSON structure, numbers, and scores. "
        "Translate requirement, evidence, reasoning, required_met, required_missing into English. "
        "Return only valid JSON."
    )
    try:
        translated = mistral_json(api_key, system, json.dumps(match, ensure_ascii=False))
        if isinstance(translated, dict) and "match_score" in translated:
            return normalize_match_result(translated)
    except Exception:
        pass
    return match

MARKETING_HEAVY_TITLE = re.compile(
    r"\b(social media|performance marketing|paid social|content marketing|"
    r"brand marketing|grafikdesign|influencer|seo manager|online marketing manager)\b",
    re.IGNORECASE,
)
IT_ROLE_TITLE = re.compile(
    r"\b(python developer|software developer|software engineer|softwareentwickler|"
    r"backend developer|frontend developer|full[\s-]?stack developer|devops|"
    r"sysadmin|system administrator|fachinformatiker|informatik entwickler|"
    r"helpdesk|service desk|it support|it-support|it specialist|it technician|"
    r"support technician|technical support|desktop support|network support|"
    r"system support|infrastructure support|end[\s-]?user support|"
    r"1st[\s-]?level support|2nd[\s-]?level support|first[\s-]?level support|"
    r"second[\s-]?level support|application support engineer|"
    r"qa engineer|test engineer|software tester|programmer|web developer|"
    r"django|api developer|cloud engineer|linux admin|datenbankentwickler|"
    r"it consultant|it-berater|it berater|systembetreuer|it administrator)\b",
    re.IGNORECASE,
)
IT_CONTEXT_BLOB = re.compile(
    r"\b(helpdesk|service desk|active directory|windows server|microsoft 365|"
    r"ticketing|jira service|itil|endpoint management|laptop support|"
    r"hardware support|software support|remote support|vpn|firewall|"
    r"server support|it infrastructure|fachinformatik|sysadmin|"
    r"it[\s-]?support|network admin|desktop support|incident management)\b",
    re.IGNORECASE,
)
IT_SUPPORT_TITLE_LOOSE = re.compile(
    r"\b(support\b.*\b(it|technical|helpdesk|desktop|network|system)\b|"
    r"\b(it|technical|helpdesk|desktop|network|system)\b.*\bsupport\b)\b",
    re.IGNORECASE,
)

NON_IT_DEGREE_TITLE = re.compile(
    r"\b(sachbearbeiter|referent|projektkoordinator|projektassist|koordinator|"
    r"office coordinator|administrative assistant|verwaltung|bürokaufmann|"
    r"junior analyst|business analyst|operations analyst|research assistant|"
    r"traineeprogramm|trainee program|graduate program|berufseinsteiger|"
    r"hochschulabsolvent|universitätsabsolvent|young professional|"
    r"hr assistant|personalreferent|customer service|kundenservice|kundenberater|"
    r"marketing assistant|sales assistant|compliance assistant|"
    r"esg analyst|sustainability analyst|energy analyst|documentation|"
    r"program coordinator|documentation officer|junior consultant|"
    r"werkstudent(?!.*(?:software|entwickler|developer|it\b)))\b",
    re.IGNORECASE,
)

EXCLUDED_TITLE = re.compile(
    r"\b(pflege|gesundheits|kranken|nurs|physio|mfa\b|zahnmed|arzt|helfer/in|"
    r"marketing manager|accountant|controller|copywriter|ppc |amazon advertising|"
    r"creative strategist|email marketing|abteilungsleiter|department manager|"
    r"heizung|servicetechniker|kundendienstmonteur|monteur|verkauf|sales manager|"
    r"geschäftsführer|geschaeftsfuehrer|ausbildung (?!fachinformatik)|"
    r"steuerfach|rechtsanwalt|personalreferent(?! it)|recruiter|"
    r"pflegefach|operationssaal|intensiv|reinigung|putzkraft|hausmeister|"
    r"judo|karate|yoga|buddhist|hindu|hinduism|religion teacher|imam|pastor|priester|theolog)\b",
    re.IGNORECASE,
)

# Intermediary boards / search pages — not a direct job application.
BAD_APPLY_URL = re.compile(
    r"(arbeitnow\.com/jobs/companies/[^/?#]+/?(?:$|[?#])|"
    r"indeed\.com/(?:$|[?#]|jobs/?$|jobs\?|viewjobs\?)|"
    r"stepstone\.de/(?:$|[?#]|5/index\.htm|jobs/?$|jobs\?|stellenangebote\.html)|"
    r"linkedin\.com/jobs(?:/search|[?#]|$)|"
    r"xing\.com/jobs(?:/search|[?#]|$)|"
    r"arbeitsagentur\.de/jobsuche/?(?:$|[?#])|"
    r"arbeitsagentur\.de/jobsuche\?|"
    r"arbeitsagentur\.de/(?:$|karriere/?(?:$|[?#]))|"
    r"google\.com/search)",
    re.IGNORECASE,
)

ARBEITSAGENTUR_JOBDETAIL_BASE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/"

# Generic career/marketing pages — not a specific job posting.
GENERIC_LANDING_URL = re.compile(
    r"(/karriere/das-bietet|/karriere/faqs|/karriere/?(?:$|[?#])|"
    r"/careers/?(?:$|[?#])|/about(?:-us)?/?(?:$|[?#])|/benefits/?(?:$|[?#])|"
    r"/team/?(?:$|[?#])|/unternehmen/?(?:$|[?#]))",
    re.IGNORECASE,
)

# Known single-job listing URL patterns.
JOB_LISTING_URL = re.compile(
    r"(arbeitsagentur\.de/jobsuche/jobdetail/|"
    r"europa\.eu/eures/portal/jv-detail|eures\.europa\.eu/.+jv|"
    r"stepstone\.de/stellenangebote--|"
    r"indeed\.com/viewjob|indeed\.com/rc/clk|"
    r"arbeitnow\.com/jobs/|jooble\.org/jobs/|"
    r"/job/apply/\d|jobs\.ratbacher\.de/job/|"
    r"greenhouse\.io/.+/jobs/\d|jobs\.lever\.co/|"
    r"myworkdayjobs\.com/.+/job/|personio\.de/jobs/\d|"
    r"smartrecruiters\.com/.+/\d|"
    r"/stellenangebote/[^/?#]+|/jobs/view/\d)",
    re.IGNORECASE,
)

PRE_DEGREE_STUDENT_PROGRAM = re.compile(
    r"\b(duales studium|dual(?:\s+study)?\s+program|ausbildung zum|ausbildung als|"
    r"hochschulzugangsberechtigung|fachhochschulreife|\babitur\b|"
    r"regelstudienzeit|studienbeginn|starte deine ausbildung|"
    r"starte dein duales studium|wechselst du zwischen deinem studium|"
    r"semester-?regelstudienzeit|ihk-?abschluss als)\b",
    re.IGNORECASE,
)

GRADUATE_TRAINEE_PROGRAM = re.compile(
    r"\b(traineeprogramm|trainee program|graduate program|graduiertenprogramm|"
    r"absolventenprogramm|einstiegsprogramm|entry program|"
    r"mit abgeschlossenem (?:studium|hochschulstudium)|nach (?:deinem )?studium|"
    r"berufseinsteiger mit studium|quereinsteiger mit studium|"
    r"weiterbildung.*(?:mit )?(?:festanstellung|übernahme))\b",
    re.IGNORECASE,
)

ANY_BACHELOR_FIELD_SIGNAL = re.compile(
    r"\b(any bachelor|any field|all disciplines|beliebiges studium|"
    r"studium in beliebiger|unabhängig vom studienfach|"
    r"hochschulabschluss.*(?:egal|beliebig|jeweiligen)|"
    r"bachelor'?s? degree in any|degree in any field|"
    r"abgeschlossenes studium.*(?:beliebig|jeweiligen)|"
    r"universitätsabschluss)\b",
    re.IGNORECASE,
)

MATCH_SCHEMA = """
Return ONLY valid JSON with:
{
  "match_score": <0-100 based on REQUIREMENTS not job title>,
  "recommendation": "apply" | "review" | "skip",
  "role_category": "<best-fit family>",
  "title_vs_requirements_note": "<does title match posting requirements?>",
  "requirements_analysis": [
    {"requirement": "", "section": "must-have|preferred|responsibility|education|logistics",
     "status": "met|partial|missing", "evidence": ""}
  ],
  "must_have_met_count": 0,
  "must_have_total": 0,
  "required_met": [],
  "required_missing": [],
  "preferred_met": [],
  "transferable_bridges": [],
  "dealbreakers": [],
  "logistics_ok": true,
  "logistics_notes": "",
  "cultural_fit_summary": "",
  "reasoning": ""
}
"""

MATERIALS_SCHEMA = """
Return ONLY valid JSON with:
{
  "tailored_resume": "...",
  "cover_letter": "...",
  "key_angles": []
}
"""

HTML_CV_SCHEMA = """
Return ONLY valid JSON with:
{
  "header_job_title": "<short target role for CV header, e.g. Junior Data Analyst>",
  "profile_intro": "<2-3 sentences tailored to this job; facts from CV only>",
  "profile_highlights": [
    "<optional HTML bullet with <strong>keyword</strong> emphasis, max 3 bullets>"
  ],
  "skill_boxes": [
    {"heading": "<skill group 1>", "content": "<comma-separated skills relevant to job>"},
    {"heading": "<skill group 2>", "content": "<...>"},
    {"heading": "<skill group 3>", "content": "<...>"}
  ],
  "interests": "<one short interests line>"
}
"""

COVER_LETTER_HTML_SCHEMA = """
Return ONLY valid JSON with:
{
  "greeting": "<Dear Hiring Manager or named contact if known>",
  "paragraphs": [
    "<opening: role interest and fit, 2-4 sentences>",
    "<body: education, transferable skills, evidence from CV — 3-5 sentences>",
    "<closing: availability, relocation to Germany, call to action — 2-3 sentences>"
  ],
  "closing": "<Kind regards, or Mit freundlichen Grüßen if posting is German>",
  "subject_line": "<short application subject, e.g. Application for Junior Analyst>"
}
"""


API_ENV_KEYS = frozenset({
    "MISTRAL_API_KEY",
    "MISTRAL_MODEL",
    "APIFY_TOKEN",
    "APIFY_DATASET_ID",
    "APIFY_DATASET_IDS",
    "APIFY_AUTO_RUN",
    "APIFY_MAX_ACTOR_RUNS",
    "APIFY_LINKEDIN_ACTOR_ID",
    "JOOBLE_API_KEY",
})

APIFY_SOURCES_PATH = SCRIPT_DIR / "config" / "apify_sources.json"
APIFY_CONFIG_DIR = SCRIPT_DIR / "config"


def load_env_files() -> None:
    """Load .env / environment.env; overwrite empty API keys so Django decouple does not block them."""
    search_dirs = [SCRIPT_DIR, SCRIPT_DIR.parent, SCRIPT_DIR.parent.parent]
    seen = set()
    for directory in search_dirs:
        if directory in seen:
            continue
        seen.add(directory)
        for name in ("environment.env", ".env"):
            path = directory / name
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if not key:
                    continue
                current = os.environ.get(key, "").strip()
                if key in API_ENV_KEYS and value:
                    os.environ[key] = value
                elif not current:
                    os.environ[key] = value
    _refresh_match_thresholds()


def _refresh_match_thresholds() -> None:
    """Re-read tunables after .env is loaded (Django imports this module before apps.ready)."""
    global MATCH_MODE, APPLY_SCORE_MIN, APPLY_MUST_RATIO_MIN
    global REVIEW_SCORE_MIN, REVIEW_MUST_RATIO_MIN, BROAD_SCORE_MIN
    MATCH_MODE = os.getenv("JOB_MATCH_MODE", "broad").strip().lower()
    APPLY_SCORE_MIN = _env_int("JOB_APPLY_SCORE_MIN", 45)
    APPLY_MUST_RATIO_MIN = _env_float("JOB_APPLY_RATIO_MIN", 0.32)
    REVIEW_SCORE_MIN = _env_int("JOB_REVIEW_SCORE_MIN", 38)
    REVIEW_MUST_RATIO_MIN = _env_float("JOB_REVIEW_RATIO_MIN", 0.25)
    BROAD_SCORE_MIN = _env_int("JOB_BROAD_SCORE_MIN", 50)


def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    clusters = profile.get("search_keyword_clusters", {})
    if clusters and not profile.get("all_search_keywords"):
        flat: list[str] = []
        for terms in clusters.values():
            flat.extend(terms)
        profile["all_search_keywords"] = sorted(set(flat))
    return profile


def load_qualifications() -> dict:
    """Structured qualification inventory for requirements-based matching."""
    if QUALIFICATIONS_PATH.exists():
        return json.loads(QUALIFICATIONS_PATH.read_text(encoding="utf-8"))
    if CV_PROFILE_PATH.exists():
        return json.loads(CV_PROFILE_PATH.read_text(encoding="utf-8"))
    return {}


def build_matching_context(cv: str, profile: dict | None = None) -> str:
    profile = profile or load_profile()
    quals = load_qualifications()
    return f"""## Full CV text
{cv}

## Candidate profile (locations, eligibility, strategy)
{json.dumps(profile, indent=2)}

## Structured qualifications inventory (source of truth for matching)
{json.dumps(quals, indent=2)}

## Matching rules
1. IGNORE job title unless it clearly contradicts the description.
2. Extract requirements from: Qualifications, Requirements, Must have, Nice to have, Responsibilities, What you bring, Your profile, Skills, Education, Languages, Location.
3. Titles vary widely (e.g. "Associate", "Specialist", "Analyst", "Engineer", "Consultant", "Werkstudent") — match on requirements only.
4. Map each must-have to qualifications using transferable skills (BA degree, pedagogical authorization, languages, counseling, reception).
5. Recognize role families and title aliases in qualifications.role_families_eligible and title_aliases_to_recognize.
6. Teaching, language instruction, and adult education experience qualify for education, Sprachkurs, and training roles.
7. Reception + multilingual + documentation qualify for customer service, front desk, and office admin roles.
8. Candidate holds BA International Development plus authorized teacher training: qualify for entry-level KNOWLEDGE-WORK roles (education, counseling, office, coordination, NGO, research assistant) — not only IT titles.
9. Match on degree level + transferable experience (teaching, counseling, languages, reception) even when job title is generic (Coordinator, Specialist, Sachbearbeiter).
10. Do not invent skills. Use partial when adjacent coursework or experience applies.
11. EU citizen — Germany/EU work authorized unless posting requires specific license candidate lacks.
12. Exclude manual labor, licensed trades, and clinical roles.
13. English-speaking workplace is a strong plus — candidate is fluent in English; prefer scoring English-friendly roles highly.
14. German A1 or "advantage" is partial fit, not a dealbreaker, unless posting requires native/C1+ German as hard must-have.
15. Generic "university degree" / "Bachelor" / "Hochschulabschluss" requirements are MET by BA International Development and pedagogical authorization.
16. Include teaching, education, counseling, office, admin, HR, customer service, coordination, NGO, research — Frankfurt / Rhine-Main / NRW focus.
17. "Any bachelor's degree" / generic Hochschulabschluss = met by BA + teacher authorization — score these highly.
18. Graduate trainee / Einstiegsprogramm after studies = eligible; dual-study for Abitur holders = not candidate fit.
19. PRIMARY SIGNAL = education (BA, pedagogy), languages, and people-facing experience — NOT years in the same industry.
20. Do NOT require prior job titles to match the posting; Norwegian work history is valid transferable experience.
21. When posting asks for "first experience" or Berufseinsteiger, education, teaching practice, and counseling count as evidence.
22. Prefer scoring 50%+ for any knowledge-work role where degree + transferable skills fit, even without domain work history.
23. Candidate is Ivana Jovic ONLY — cite facts from the CV and qualifications JSON above. NEVER mention 199 ECTS, Dell, Addis Ababa, Ethiopia, computer science degree, Linnaeus, technical support awards, or STEM/software coursework unless explicitly present in the CV text.
24. For degree requirements cite: BA International Development, Practical-Pedagogical Education (authorized teacher), and related studies — not ECTS totals.
"""


def html_to_text(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</(p|li|h[1-6]|div|section|tr)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def resolve_default_cv() -> Path:
    for name in ("cv.txt", "cv.html", "cv.pdf"):
        for directory in (SCRIPT_DIR, SCRIPT_DIR.parent, SCRIPT_DIR.parent.parent):
            path = directory / name
            if path.exists():
                return path
    return SCRIPT_DIR / "cv.html"


def load_cv(cv_path: Path | None = None) -> str:
    path = cv_path or resolve_default_cv()
    if not path.exists():
        raise FileNotFoundError(f"CV not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
    elif suffix in (".html", ".htm"):
        text = html_to_text(path.read_text(encoding="utf-8"))
    else:
        text = path.read_text(encoding="utf-8").strip()
    if len(text) < 100:
        raise ValueError("CV too short")
    return text


def slugify(*parts: str, max_len: int = 80) -> str:
    raw = "_".join(p for p in parts if p)
    raw = re.sub(r"[^\w\s-]", "", raw.lower())
    raw = re.sub(r"[\s_-]+", "_", raw).strip("_")
    return raw[:max_len] or "job"


def parse_json_response(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _strip_html(value: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", value, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|li|h[1-6]|div|section|tr)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def mistral_json(api_key: str, system: str, user: str, retries: int = 3, *, model: str | None = None) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model or MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    last_error = None
    for attempt in range(retries + 1):
        response = requests.post(MISTRAL_URL, json=payload, headers=headers, timeout=90 if model in (SCORE_MODEL, MATERIALS_MODEL) else 120)
        result = response.json()
        if "choices" not in result:
            is_rate_limit = response.status_code == 429 or result.get("code") == "1300"
            if is_rate_limit and attempt < retries:
                wait = min(60, 5 * (2**attempt))
                time.sleep(wait)
                continue
            raise RuntimeError(f"Mistral error: {result}")
        try:
            return parse_json_response(result["choices"][0]["message"]["content"])
        except json.JSONDecodeError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Invalid JSON from Mistral: {last_error}")


def load_cached_jobs() -> list[dict]:
    if not JOBS_CACHE_PATH.exists():
        raise FileNotFoundError(f"No cache at {JOBS_CACHE_PATH}")
    data = json.loads(JOBS_CACHE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Cache empty")
    return data


def save_jobs_cache(jobs: list[dict]) -> None:
    JOBS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOBS_CACHE_PATH.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def save_live_jobs(jobs: list[dict], *, sources: list[dict] | None = None) -> None:
    """Partial results while search is still running (shown in the UI)."""
    JOBS_LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(jobs),
        "sources": sources or [],
        "jobs": jobs[-200:],
    }
    JOBS_LIVE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_live_jobs() -> dict:
    if not JOBS_LIVE_PATH.exists():
        return {"jobs": [], "count": 0, "sources": []}
    try:
        data = json.loads(JOBS_LIVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"jobs": [], "count": 0, "sources": []}
    if not isinstance(data, dict):
        return {"jobs": [], "count": 0, "sources": []}
    return data


def clear_live_jobs() -> None:
    if JOBS_LIVE_PATH.exists():
        JOBS_LIVE_PATH.unlink()


def _decode_eures_jvid(jv_id: str) -> str:
    """EURES jvId is base64-encoded Arbeitsagentur refnr (often '10001-123-S 1')."""
    if not jv_id:
        return ""
    try:
        padded = jv_id + "=" * (-len(jv_id) % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="replace").strip()
        if decoded and decoded[-1].isdigit():
            parts = decoded.rsplit(" ", 1)
            if len(parts) == 2 and parts[1].isdigit():
                decoded = parts[0].strip()
        return decoded
    except Exception:
        return ""


def _extract_arbeitsagentur_refnr(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"arbeitsagentur\.de/jobsuche/jobdetail/([^?#]+)", url, re.I)
    if not match:
        return ""
    from urllib.parse import unquote

    return unquote(match.group(1)).strip("/")


def arbeitsagentur_jobdetail_url(refnr: str) -> str:
    refnr = (refnr or "").strip().lstrip("/")
    if not refnr:
        return ""
    return f"{ARBEITSAGENTUR_JOBDETAIL_BASE}{refnr}"


def _eures_jvid_from_url(url: str) -> str:
    match = re.search(r"[?&]jvId=([^&#]+)", url or "", re.I)
    if not match:
        return ""
    from urllib.parse import unquote

    return unquote(match.group(1)).strip()


def normalize_apply_url(url: str) -> str:
    """Clean and normalize a job URL."""
    value = (url or "").strip()
    if not value:
        return ""
    value = value.rstrip(".,;)\\]'\"")
    # Broken RSS/HTML truncation e.g. ...marketing_tactic=karriere)und
    if ")" in value:
        tail = value[value.rfind(")") + 1:]
        if tail and not tail.startswith("%") and len(tail) < 12:
            value = value[: value.rfind(")")]
    lower = value.lower()

    jv_id = _eures_jvid_from_url(value)
    if jv_id:
        refnr = _decode_eures_jvid(jv_id)
        if refnr:
            return arbeitsagentur_jobdetail_url(refnr)

    refnr = _extract_arbeitsagentur_refnr(value)
    if refnr:
        return arbeitsagentur_jobdetail_url(refnr)

    if "arbeitsagentur.de/jobsuche" in lower and "ids=" in value:
        ref = value.split("ids=", 1)[1].split("&", 1)[0].split(",", 1)[0].strip()
        if ref:
            return arbeitsagentur_jobdetail_url(ref)
    if not value.startswith("http"):
        return ""
    return value


def is_job_listing_url(url: str) -> bool:
    """Strict: URL must point at one specific job posting."""
    url = normalize_apply_url(url)
    if len(url) < 12 or not url.startswith("http"):
        return False
    if GENERIC_LANDING_URL.search(url):
        return False
    if BAD_APPLY_URL.search(url):
        return False
    if JOB_LISTING_URL.search(url):
        return True
    if re.match(r"https?://[^/]+/?$", url, re.I):
        return False
    return False


def is_intermediary_board_url(url: str) -> bool:
    return bool(INTERMEDIARY_BOARD_HOST.search(url or ""))


def hard_german_required(blob: str) -> bool:
    return bool(HARD_GERMAN_REQUIRED.search(blob or ""))


def extract_apply_urls_from_description(description: str) -> tuple[str, str]:
    """Return (employer_direct_url, intermediary_listing_url) from posting text."""
    employer = ""
    listing = ""
    for raw in re.findall(r"https?://[^\s<>\"'\]]+", description or ""):
        url = normalize_apply_url(raw.rstrip(".,;)\\]'"))
        if not is_job_listing_url(url):
            continue
        if is_intermediary_board_url(url):
            listing = listing or url
        else:
            return url, listing
    return employer, listing


def resolve_apply_url(job: dict) -> str:
    """Return a verified job listing URL, or empty string if none found."""
    refnr = _ensure_text(job.get("refnr"))
    if refnr:
        return arbeitsagentur_jobdetail_url(refnr)

    for field in ("applyUrl", "url", "link", "apply_url", "application_url", "job_url"):
        raw = _ensure_text(job.get(field))
        if not raw:
            continue
        jv_id = _eures_jvid_from_url(raw)
        if jv_id:
            decoded = _decode_eures_jvid(jv_id)
            if decoded:
                return arbeitsagentur_jobdetail_url(decoded)
        extracted = _extract_arbeitsagentur_refnr(raw)
        if extracted:
            return arbeitsagentur_jobdetail_url(extracted)

    desc, _, _title, _company = job_text_fields(job)
    employer_url, _listing_url = extract_apply_urls_from_description(desc)
    if employer_url:
        return employer_url

    candidates: list[str] = []

    for field in ("applyUrl", "url", "link", "apply_url", "application_url", "job_url"):
        val = normalize_apply_url(_ensure_text(job.get(field)))
        if val and val not in candidates:
            candidates.append(val)

    if desc:
        for raw in re.findall(r"https?://[^\s<>\"'\]]+", desc):
            val = normalize_apply_url(raw.rstrip(".,;)\\]'"))
            if val and val not in candidates:
                candidates.append(val)
        for raw in re.findall(r'href=["\']?(https?://[^"\'>\s]+)', desc, re.I):
            val = normalize_apply_url(raw)
            if val and val not in candidates:
                candidates.append(val)

    for url in candidates:
        if is_job_listing_url(url) and not is_intermediary_board_url(url):
            return url
    for url in candidates:
        if is_job_listing_url(url):
            return url
    return ""


def _jobs_for_live_feed(jobs: list[dict], limit: int = 80) -> list[dict]:
    """Compact rows for the live search panel in the UI."""
    rows: list[dict] = []
    for job in jobs[-limit:]:
        _, _, title, company = job_text_fields(job)
        raw_url = job.get("applyUrl") or job.get("url") or job.get("link") or ""
        rows.append({
            "title": title or "Unknown title",
            "company": company or "",
            "location": job.get("location") or "",
            "source": job.get("source") or "",
            "apply_url": resolve_apply_url(job) or normalize_apply_url(raw_url),
        })
    return rows


def save_source_diagnostics(diagnostics: dict) -> None:
    SOURCE_DIAGNOSTICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_DIAGNOSTICS_PATH.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")


def load_source_diagnostics() -> dict:
    if not SOURCE_DIAGNOSTICS_PATH.exists():
        return {}
    return json.loads(SOURCE_DIAGNOSTICS_PATH.read_text(encoding="utf-8"))


REMOTIVE_URL = "https://remotive.io/api/remote-jobs"
ARBEITNOW_URL = "https://arbeitnow.com/api/job-board-api"
ARBEITSAGENTUR_JOBS_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
ARBEITSAGENTUR_DETAILS_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails"
ARBEITSAGENTUR_API_KEY = "jobboerse-jobsuche"
ARBEITSAGENTUR_SEARCHES = [
    # Non-IT degree / office / graduate roles first
    ("Berufseinsteiger", "Frankfurt am Main"),
    ("Berufseinsteiger", "Köln"),
    ("Berufseinsteiger", "Düsseldorf"),
    ("Berufseinsteiger", "Bonn"),
    ("Hochschulabsolvent", "Frankfurt am Main"),
    ("Hochschulabsolvent", "Köln"),
    ("Universitätsabsolvent", "Frankfurt am Main"),
    ("Universitätsabsolvent", "Köln"),
    ("Traineeprogramm", "Frankfurt am Main"),
    ("Traineeprogramm", "Köln"),
    ("Einstiegsprogramm", "Düsseldorf"),
    ("Absolvent", "Frankfurt am Main"),
    ("Absolvent", "Köln"),
    ("Quereinsteiger Studium", "Bonn"),
    ("Quereinsteiger", "Frankfurt am Main"),
    ("Quereinsteiger", "Düsseldorf"),
    ("Projektkoordinator", "Frankfurt am Main"),
    ("Projektkoordinator", "Köln"),
    ("Sachbearbeiter", "Frankfurt am Main"),
    ("Sachbearbeiter", "Düsseldorf"),
    ("Junior Analyst", "Köln"),
    ("Research Assistant", "Frankfurt am Main"),
    ("Research Assistant", "Düsseldorf"),
    ("Junior Consultant", "Köln"),
    ("Junior Consultant", "Düsseldorf"),
    ("Verwaltung", "Frankfurt am Main"),
    ("Verwaltung", "Köln"),
    ("Verwaltung", "Bonn"),
    ("Büro", "Frankfurt am Main"),
    ("Büro", "Düsseldorf"),
    ("Bürokaufmann", "Düsseldorf"),
    ("Kundenservice", "Frankfurt am Main"),
    ("Personal", "Köln"),
    ("Marketing Assistant", "Frankfurt am Main"),
    ("English", "Frankfurt am Main"),
    ("English speaking", "Köln"),
    ("Studium", "Frankfurt am Main"),
    ("Studium", "Köln"),
    ("Praktikum Hochschule", "Frankfurt am Main"),
    ("Praktikum Hochschule", "Bonn"),
    ("Trainee", "Frankfurt am Main"),
    ("Trainee", "Köln"),
    ("Junior", "Frankfurt am Main"),
    ("Junior", "Köln"),
    ("Werkstudent", "Frankfurt am Main"),
    ("Werkstudent", "Köln"),
    ("Datenanalyst", "Frankfurt am Main"),
    # IT roles — still searched, but lower priority in round-robin
    ("Python", "Frankfurt am Main"),
    ("Softwareentwickler", "Frankfurt am Main"),
    ("IT-Support", "Frankfurt am Main"),
    ("Fachinformatiker", "Frankfurt am Main"),
    ("Helpdesk", "Frankfurt am Main"),
    ("Python", "Köln"),
    ("Softwareentwickler", "Köln"),
    ("IT-Support", "Köln"),
    ("Python", "Düsseldorf"),
    ("IT-Support", "Düsseldorf"),
    ("Softwareentwickler", "Bonn"),
    ("Junior Entwickler", "Frankfurt am Main"),
    ("Quereinsteiger IT", "Köln"),
    ("Systemadministrator", "Mainz"),
]
ARBEITNOW_SEARCH_QUERIES = [
    "Berufseinsteiger",
    "Bachelor Absolvent",
    "Hochschulabsolvent",
    "Sachbearbeiter",
    "Projektkoordinator",
    "Junior Analyst",
    "Business Analyst",
    "Office Coordinator",
    "Research Assistant",
    "Trainee",
    "Python Developer",
    "IT Support",
    "Helpdesk",
    "Junior Developer",
    "Werkstudent",
    "Verwaltung",
    "Frankfurt",
    "Köln",
    "Cologne",
    "Düsseldorf",
    "Bonn",
]
JOOBLE_API_BASE_URL = "https://jooble.org/api/"
STEPSTONE_RSS_URLS = [
    "https://www.stepstone.de/rss/stellenangebote-in-frankfurt",
    "https://www.stepstone.de/rss/stellenangebote-in-koeln",
    "https://www.stepstone.de/rss/stellenangebote-in-bonn",
    "https://www.stepstone.de/rss/stellenangebote-in-duesseldorf",
    "https://www.stepstone.de/rss/stellenangebote-in-mainz",
    "https://www.stepstone.de/rss/stellenangebote-in-wiesbaden",
    "https://www.stepstone.de/rss/stellenangebote-in-darmstadt",
    "https://www.stepstone.de/rss/stellenangebote-in-offenbach",
]
JOOBLE_TARGET_CITIES = ["Frankfurt", "Köln", "Bonn", "Düsseldorf", "Hanau", "Mainz", "Wiesbaden"]
JOOBLE_SEARCH_KEYWORDS = [
    "Universitätsabschluss", "Hochschulabsolvent", "Bachelor", "Studium",
    "Berufseinsteiger", "Quereinsteiger", "Traineeprogramm", "Entry Level",
    "Sachbearbeiter", "Projektkoordinator", "Junior Analyst", "Business Analyst",
    "Office Coordinator", "Verwaltung", "Research Assistant", "Young Professional",
    "Customer Service", "HR Assistant", "Trainee", "Werkstudent", "English speaking",
    "Python Developer", "IT Support", "Technical Support", "Helpdesk",
]
INDEED_SEARCH_KEYWORDS = [
    "Universitätsabschluss", "Hochschulabsolvent", "Bachelor", "Studium",
    "Berufseinsteiger", "Quereinsteiger", "Traineeprogramm", "Entry Level",
    "Sachbearbeiter", "Projektkoordinator", "Junior Analyst", "Business Analyst",
    "Office Coordinator", "Verwaltung", "Research Assistant", "Young Professional",
    "Customer Service", "HR Assistant", "Trainee", "English speaking", "Werkstudent",
    "Python Developer", "Software Developer", "IT Support", "Helpdesk",
]
INDEED_TARGET_LOCATIONS = [
    ("Frankfurt", "Frankfurt"),
    ("Köln", "K%C3%B6ln"),
    ("Cologne", "Cologne"),
    ("Bonn", "Bonn"),
    ("Düsseldorf", "D%C3%BCsseldorf"),
    ("Dusseldorf", "Dusseldorf"),
    ("Hanau", "Hanau"),
    ("Mainz", "Mainz"),
    ("Wiesbaden", "Wiesbaden"),
    ("Darmstadt", "Darmstadt"),
]
ADZUNA_RSS_URLS = [
    "https://www.adzuna.de/jobs/search?location0=DE&location1=Hessen&location2=Frankfurt&results_per_page=50&content-type=rss",
    "https://www.adzuna.de/jobs/search?location0=DE&location1=NRW&location2=K%C3%B6ln&results_per_page=50&content-type=rss",
    "https://www.adzuna.de/jobs/search?location0=DE&location1=NRW&location2=D%C3%BCsseldorf&results_per_page=50&content-type=rss",
]


def _build_indeed_rss_urls() -> list[str]:
    from urllib.parse import quote_plus

    urls: list[str] = []
    for _label, encoded in INDEED_TARGET_LOCATIONS:
        for keyword in INDEED_SEARCH_KEYWORDS:
            urls.append(f"https://de.indeed.com/rss?q={quote_plus(keyword)}&l={encoded}")
    return urls


INDEED_RSS_URLS = _build_indeed_rss_urls()
RSS_JOB_FEED_URLS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://remoteok.com/remote-dev-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin.rss",
    "https://weworkremotely.com/categories/remote-customer-support.rss",
]
REMOTIVE_CATEGORIES = [
    "software-dev",
    "devops",
    "customer-support",
    "qa",
    "data",
]

ALTERNATIVE_SOURCES = [
    "Arbeitsagentur Jobsuche API (free, official DE)",
    "Arbeitnow API (free, many IT listings)",
    "StepStone RSS (free)",
    "Indeed RSS (free)",
    "Adzuna RSS (free)",
    "Remotive API (remote, filtered for Germany/EU)",
    "EU remote job RSS feeds",
    "Jooble API (free key at jooble.org)",
    "Apify LinkedIn/Indeed (paid, optional)",
]


def profile_search_keywords(max_terms: int = 28) -> list[str]:
    """Search terms from profile clusters — non-IT degree roles first, then IT."""
    profile = load_profile()
    clusters = profile.get("search_keyword_clusters") or {}
    non_it_keys = (
        "education_any_degree", "graduate_trainee", "bachelor_entry_level",
        "office_administration", "business_analysis", "stem_sustainability",
        "stem_general", "general_graduate", "customer_and_service", "hr_and_people",
        "sales_and_marketing_junior", "multilingual_advisory", "english_workplace",
        "customer_success", "integration_delivery", "documentation_training",
    )
    it_keys = (
        "software_development", "it_support", "qa_testing", "data_analytics",
        "cloud_infra",
    )
    ordered_groups: list[list[str]] = []
    for key in non_it_keys:
        if clusters.get(key):
            ordered_groups.append(clusters[key])
    for key in it_keys:
        if clusters.get(key):
            ordered_groups.append(clusters[key])
    for key, group in clusters.items():
        if key not in non_it_keys and key not in it_keys and group:
            ordered_groups.append(group)

    terms: list[str] = []
    idx = 0
    while len(terms) < max_terms and ordered_groups:
        added = False
        for group in ordered_groups:
            if idx < len(group):
                t = _ensure_text(group[idx])
                if t and t not in terms:
                    terms.append(t)
                    added = True
                if len(terms) >= max_terms:
                    break
        if not added:
            break
        idx += 1
    flat = profile.get("all_search_keywords") or []
    for term in flat:
        t = _ensure_text(term)
        if t and t not in terms:
            terms.append(t)
        if len(terms) >= max_terms:
            break
    return terms[:max_terms]


def profile_target_cities() -> list[str]:
    profile = load_profile()
    prefs = profile.get("location_preferences") or {}
    cities = prefs.get("cities") or []
    if cities:
        return cities
    return [
        "Frankfurt am Main", "Köln", "Bonn", "Düsseldorf", "Hanau",
        "Mainz", "Wiesbaden", "Darmstadt", "Offenbach",
    ]


def build_arbeitsagentur_searches() -> list[tuple[str, str]]:
    """Keyword × city matrix from your profile (capped to avoid API overload)."""
    keywords = profile_search_keywords(32)
    cities = profile_target_cities()[:10]
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for city in cities:
        for kw in keywords[:14]:
            pair = (kw[:80], city[:80])
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    for pair in ARBEITSAGENTUR_SEARCHES:
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    cap = _env_int("ARBEITSAGENTUR_MAX_SEARCHES", 16)
    return pairs[:cap]


def build_arbeitnow_queries() -> list[str]:
    queries = list(ARBEITNOW_SEARCH_QUERIES)
    seen = set(q.lower() for q in queries)
    for kw in profile_search_keywords(16):
        if kw.lower() not in seen:
            queries.append(kw)
            seen.add(kw.lower())
    for city in profile_target_cities()[:6]:
        c = city.split(",")[0].strip()
        if c.lower() not in seen:
            queries.append(c)
            seen.add(c.lower())
    return queries[: _env_int("ARBEITNOW_MAX_QUERIES", 10)]


def build_jooble_search_matrix() -> list[tuple[str, str]]:
    cities = profile_target_cities()[:8] or JOOBLE_TARGET_CITIES
    keywords = profile_search_keywords(12) or JOOBLE_SEARCH_KEYWORDS
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for city in cities:
        short = city.split(",")[0].strip()
        for kw in keywords:
            pair = (kw, short)
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    cap = _env_int("JOOBLE_MAX_SEARCHES", 36)
    return pairs[:cap]


def _ensure_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("name", "label", "text", "value", "firma", "arbeitgeber", "ort"):
            nested = value.get(key)
            if nested is None or isinstance(nested, dict):
                continue
            text = str(nested).strip()
            if text:
                return text
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(item).strip() for item in value if item)
    return str(value).strip()


def _coerce_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _arbeitsort_parts(value: object, *, fallback: str = "") -> tuple[str, str]:
    if isinstance(value, dict):
        ort = _ensure_text(value.get("ort")) or fallback
        plz = _ensure_text(value.get("plz"))
        return ort, plz
    if isinstance(value, str):
        text = value.strip()
        return text or fallback, ""
    return fallback, ""


def _arbeitgeber_label(value: object) -> str:
    if isinstance(value, dict):
        return _ensure_text(
            value.get("name") or value.get("firma") or value.get("arbeitgeber") or value.get("label")
        )
    return _ensure_text(value)


def _arbeitsagentur_search_rows(data: object) -> list[dict]:
    """Normalize search API payload to a list of job dict rows."""
    if not isinstance(data, dict):
        return []
    rows = data.get("stellenangebote")
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _parse_company_from_title(title: str) -> str:
    text = _ensure_text(title)
    if " - " in text:
        candidate = text.split(" - ")
        if len(candidate) > 1:
            return candidate[-1].strip()
    if "|" in text:
        candidate = text.split("|")
        if len(candidate) > 1:
            return candidate[-1].strip()
    return ""


def _normalize_job(raw: dict, source: str) -> dict:
    title = _ensure_text(raw.get("title") or raw.get("job_title") or raw.get("position") or raw.get("name") or raw.get("headline"))
    company = _ensure_text(raw.get("company") or raw.get("companyName") or raw.get("company_name") or raw.get("employer") or raw.get("organization") or raw.get("author"))
    if not company:
        company = _parse_company_from_title(title)
    location = _ensure_text(raw.get("location") or raw.get("candidate_required_location") or raw.get("city") or raw.get("region") or raw.get("area") or raw.get("place"))
    description = _ensure_text(raw.get("description") or raw.get("descriptionText") or raw.get("descriptionHtml") or raw.get("jobDescription") or raw.get("summary") or raw.get("content") or raw.get("body") or raw.get("snippet"))
    description = _strip_html(description)
    url = _ensure_text(raw.get("url") or raw.get("applyUrl") or raw.get("job_url") or raw.get("application_url") or raw.get("link") or raw.get("source_url") or raw.get("redirect_url"))
    normalized = {
        **raw,
        "title": title or "Unknown title",
        "company": company or "Unknown company",
        "location": location,
        "description": description,
        "url": url,
        "applyUrl": url,
        "source": source,
    }
    apply_url = resolve_apply_url(normalized)
    if apply_url:
        normalized["url"] = apply_url
        normalized["applyUrl"] = apply_url
    return normalized


def _merge_job_lists(job_lists: list[list[dict]]) -> list[dict]:
    merged: dict[tuple[str, str, str, str], dict] = {}
    for jobs in job_lists:
        for job in jobs:
            normalized_job = _normalize_job(job, job.get("source", "Unknown"))
            key = (
                normalized_job["title"].lower(),
                normalized_job["company"].lower(),
                normalized_job["location"].lower(),
                normalized_job["url"].lower(),
            )
            if key not in merged:
                merged[key] = normalized_job
    return list(merged.values())


def _job_location_blob(job: dict) -> str:
    addr = job.get("companyAddress")
    addr_text = ""
    if isinstance(addr, dict):
        addr_text = " ".join(
            str(addr.get(k, "")) for k in ("streetAddress", "addressLocality", "addressRegion", "addressCountry")
        )
    elif addr:
        addr_text = str(addr)
    return " ".join([
        str(job.get("location") or ""),
        str(job.get("country") or ""),
        str(job.get("descriptionText") or job.get("description") or "")[:1500],
        addr_text,
    ])


def is_us_or_non_germany_job(job: dict) -> bool:
    """Exclude US and other clearly non-Germany postings."""
    blob = _job_location_blob(job)
    country = str(job.get("country") or "").upper().strip()
    if country in ("US", "USA", "UNITED STATES"):
        return True
    if US_EXCLUDE_KEYWORDS.search(blob):
        return True
    if re.search(r"\b(only|must be|resident).{0,40}\b(usa|united states|u\.s\.)\b", blob, re.I):
        return True
    return False


def is_target_region_job(job: dict) -> bool:
    """Only Frankfurt / Köln / Bonn / Düsseldorf (+ Rhine-Main/NRW suburbs) or explicit remote Germany."""
    if is_us_or_non_germany_job(job):
        return False
    loc_field = str(job.get("location") or "").strip()
    if loc_field:
        if OTHER_GERMANY_CITIES.search(loc_field) and not TARGET_CITY_KEYWORDS.search(loc_field):
            return False
        if TARGET_CITY_KEYWORDS.search(loc_field):
            return True
        if REMOTE_GERMANY_KEYWORDS.search(loc_field):
            return True
    blob = _job_location_blob(job)
    in_city = bool(TARGET_CITY_KEYWORDS.search(blob))
    remote_ok = bool(REMOTE_GERMANY_KEYWORDS.search(blob))
    if OTHER_GERMANY_CITIES.search(blob) and not in_city and not remote_ok:
        return False
    if in_city:
        return True
    if remote_ok:
        return True
    loc = str(job.get("location") or "").strip().lower()
    if loc in ("remote, germany", "remote - germany", "remote germany"):
        return True
    return False


def filter_germany_jobs(jobs: list[dict], remote_eu_ok: bool = True) -> list[dict]:
    """Strict filter — target cities only (ignores remote_eu_ok legacy flag)."""
    return [job for job in jobs if is_target_region_job(job)]


def _job_search_blob(job: dict) -> str:
    desc, _, title, company = job_text_fields(job)
    return f"{title} {company} {desc}".lower()


def _term_matches_blob(term: str, blob: str) -> bool:
    """Avoid false positives like 'bi' inside 'Kombination' or 'in' inside German words."""
    term = term.strip().lower()
    if not term:
        return False
    if len(term) <= 4 and " " not in term:
        return bool(re.search(r"\b" + re.escape(term) + r"\b", blob, re.I))
    return term in blob


def is_direct_apply_url(url: str) -> bool:
    """True when URL points at one job application, not a portal search/homepage."""
    return is_job_listing_url(url)


def title_is_eligible_for_candidate(title: str, role_families: list[str]) -> bool:
    """Job title matches IT/support/data or other bachelor-level roles in profile."""
    if not title or EXCLUDED_TITLE.search(title):
        return False
    if IRRELEVANT_ROLE.search(title):
        return False
    if MARKETING_HEAVY_TITLE.search(title) and not IT_ROLE_TITLE.search(title):
        return False
    if IT_ROLE_TITLE.search(title):
        return True
    if BROAD_BACHELOR_TITLE.search(title):
        return True
    return _title_matches_role_families(title, role_families)


def is_bachelor_level_opportunity(blob: str, title: str) -> bool:
    """
    Roles open to bachelor's / university graduates in related fields
    (not only strict IT titles).
    """
    if not blob or NON_IT_JOB_BLOB.search(blob) or NON_IT_JOB_BLOB.search(title):
        return False
    if not BACHELOR_DEGREE_SIGNAL.search(blob):
        return False
    if RELATED_FIELD_SIGNAL.search(blob) or RELATED_FIELD_SIGNAL.search(title):
        return True
    if BROAD_BACHELOR_TITLE.search(title) and JUNIOR_SIGNAL.search(blob):
        return True
    if BACHELOR_DEGREE_SIGNAL.search(blob) and (
        BROAD_BACHELOR_TITLE.search(title) or JUNIOR_SIGNAL.search(blob)
    ):
        return True
    return False


def is_professional_non_manual_role(blob: str, title: str) -> bool:
    """Entry-level knowledge-work roles (not manual) open to bachelor's graduates."""
    if MANUAL_LABOR_TITLE.search(title) or MANUAL_LABOR_TITLE.search(blob):
        return False
    if NON_IT_JOB_BLOB.search(blob) or NON_IT_JOB_BLOB.search(title):
        return False
    knowledge = KNOWLEDGE_WORK_SIGNAL.search(blob) or KNOWLEDGE_WORK_SIGNAL.search(title)
    degree_or_entry = (
        BACHELOR_DEGREE_SIGNAL.search(blob)
        or JUNIOR_SIGNAL.search(blob)
        or BROAD_BACHELOR_TITLE.search(title)
    )
    if knowledge and degree_or_entry:
        return True
    if BACHELOR_DEGREE_SIGNAL.search(blob) and BROAD_BACHELOR_TITLE.search(title):
        return True
    if BACHELOR_DEGREE_SIGNAL.search(blob) and KNOWLEDGE_WORK_SIGNAL.search(blob):
        return True
    return False


def is_pre_degree_student_program(blob: str, title: str) -> bool:
    """Dual study / Ausbildung for school-leavers — not employment for degree holders."""
    if GRADUATE_TRAINEE_PROGRAM.search(blob) or GRADUATE_TRAINEE_PROGRAM.search(title):
        return False
    return bool(
        PRE_DEGREE_STUDENT_PROGRAM.search(blob)
        or PRE_DEGREE_STUDENT_PROGRAM.search(title)
    )


def is_any_bachelor_field_job(blob: str, title: str) -> bool:
    """Posting accepts any bachelor's field or generic university degree."""
    return bool(
        ANY_BACHELOR_FIELD_SIGNAL.search(blob)
        or ANY_BACHELOR_FIELD_SIGNAL.search(title)
        or (
            BACHELOR_DEGREE_SIGNAL.search(blob)
            and re.search(
                r"\b(beliebig|any|all fields|jeweiligen|nicht relevant|offen)\b",
                blob,
                re.I,
            )
        )
    )


def is_generic_bachelor_knowledge_role(blob: str, title: str) -> bool:
    """Any non-manual role that mentions a degree — cast a wide net for opportunities."""
    if EXCLUDED_TITLE.search(title) or IRRELEVANT_ROLE.search(title):
        return False
    if MANUAL_LABOR_TITLE.search(title) or MANUAL_LABOR_TITLE.search(blob):
        return False
    if NON_IT_JOB_BLOB.search(blob) or NON_IT_JOB_BLOB.search(title):
        return False
    if not BACHELOR_DEGREE_SIGNAL.search(blob) and not JUNIOR_SIGNAL.search(blob):
        return False
    return bool(
        KNOWLEDGE_WORK_SIGNAL.search(blob)
        or KNOWLEDGE_WORK_SIGNAL.search(title)
        or BROAD_BACHELOR_TITLE.search(title)
    )


def job_passes_candidate_prefilter(
    job: dict,
    *,
    role_families: list[str],
    match_terms: list[str],
) -> tuple[bool, str]:
    """Return (keep, reject_reason) for cache prefilter."""
    desc, _, title, _ = job_text_fields(job)
    blob = _job_search_blob(job)
    title_l = title.lower()

    if EXCLUDED_TITLE.search(title) or IRRELEVANT_ROLE.search(title):
        return False, "irrelevant_role"
    if NON_IT_JOB_BLOB.search(blob) or NON_IT_JOB_BLOB.search(title):
        return False, "irrelevant_role"
    if is_pre_degree_student_program(blob, title):
        return False, "student_program"
    if is_any_bachelor_field_job(blob, title):
        return True, ""
    if GRADUATE_TRAINEE_PROGRAM.search(blob) or GRADUATE_TRAINEE_PROGRAM.search(title):
        return True, ""

    if PREFILTER_MODE == "wide":
        if MANUAL_LABOR_TITLE.search(title) or MANUAL_LABOR_TITLE.search(blob):
            return False, "irrelevant_role"
        if SENIOR_EXCLUDE.search(title) or (
            SENIOR_EXCLUDE.search(blob) and not JUNIOR_SIGNAL.search(blob)
        ):
            return False, "senior_excluded"
        if BROAD_BACHELOR_TITLE.search(title) or IT_ROLE_TITLE.search(title):
            return True, ""
        if KNOWLEDGE_WORK_SIGNAL.search(blob) or KNOWLEDGE_WORK_SIGNAL.search(title):
            return True, ""
        if JUNIOR_SIGNAL.search(blob) or GRADUATE_TRAINEE_PROGRAM.search(blob):
            return True, ""
        return False, "irrelevant_role"

    it_title = title_is_eligible_for_candidate(title, role_families)
    bachelor_fit = is_bachelor_level_opportunity(blob, title)
    professional_fit = is_professional_non_manual_role(blob, title)
    generic_bachelor = is_generic_bachelor_knowledge_role(blob, title)
    has_overlap = any(
        _term_matches_blob(term, blob) or _term_matches_blob(term, title_l)
        for term in match_terms
        if len(term) >= 4
    )

    if not it_title and not bachelor_fit and not professional_fit and not generic_bachelor and not has_overlap:
        return False, "irrelevant_role"
    if SENIOR_EXCLUDE.search(blob) and not JUNIOR_SIGNAL.search(blob):
        return False, "senior_excluded"
    return True, ""


def _extract_external_apply_url(description: str) -> str:
    """Employer career/apply link embedded in posting HTML/text."""
    employer, listing = extract_apply_urls_from_description(description)
    return employer or listing


def is_full_requirement_match(match: dict) -> bool:
    """All extracted must-have requirements met."""
    if not match:
        return False
    must_total = int(match.get("must_have_total") or 0)
    must_met = int(match.get("must_have_met_count") or 0)
    if must_total >= 3 and must_met >= must_total:
        return True
    return int(match.get("match_score") or 0) >= 95


def is_it_focused_job(job: dict) -> bool:
    """True when title/blob is primarily a software/IT/support engineering role."""
    _, _, title, _ = job_text_fields(job)
    blob = _job_search_blob(job)
    if IT_ROLE_TITLE.search(title) or IT_ROLE_TITLE.search(blob):
        return True
    if IT_SUPPORT_TITLE_LOOSE.search(title):
        return True
    if re.search(r"\bsupport\b", title, re.IGNORECASE) and IT_CONTEXT_BLOB.search(blob):
        return True
    return False


def _candidate_course_match_terms(qualifications: dict | None = None) -> list[str]:
    """Keywords from coursework, skills blocks, and eligible role families."""
    qualifications = qualifications or load_qualifications()
    raw: list[str] = []
    for block_key in (
        "technical_qualifications",
        "support_qualifications",
        "stem_environment_qualifications",
        "people_qualifications",
    ):
        for item in qualifications.get(block_key) or []:
            if isinstance(item, str):
                raw.append(item.lower())
    for rf in qualifications.get("role_families_eligible") or []:
        if isinstance(rf, str):
            raw.append(rf.lower())
    for alias in qualifications.get("title_aliases_to_recognize") or []:
        if isinstance(alias, str):
            raw.append(alias.lower())
    terms: list[str] = []
    for phrase in raw:
        for word in re.findall(r"[a-z0-9]{4,}", phrase):
            if word not in terms:
                terms.append(word)
    return terms


def job_has_course_relevance(job: dict, qualifications: dict | None = None) -> bool:
    """Posting touches subjects or skills from the candidate's degree/courses."""
    _, _, title, _ = job_text_fields(job)
    blob = _job_search_blob(job)
    title_l = title.lower()
    if COURSE_SUBJECT_SIGNAL.search(blob) or COURSE_SUBJECT_SIGNAL.search(title):
        return True
    for term in _candidate_course_match_terms(qualifications):
        if _term_matches_blob(term, blob) or _term_matches_blob(term, title_l):
            return True
    return False


def is_non_it_degree_job(job: dict) -> bool:
    """Relevant knowledge-work role outside software/IT — any course overlap counts."""
    _, _, title, _ = job_text_fields(job)
    blob = _job_search_blob(job)
    if EXCLUDED_TITLE.search(title) or IRRELEVANT_ROLE.search(title):
        return False
    if NON_IT_JOB_BLOB.search(blob) or NON_IT_JOB_BLOB.search(title):
        return False
    if MANUAL_LABOR_TITLE.search(title) or MANUAL_LABOR_TITLE.search(blob):
        return False
    if is_it_focused_job(job):
        return False
    return bool(
        NON_IT_DEGREE_TITLE.search(title)
        or is_degree_level_posting(blob, title)
        or is_generic_bachelor_knowledge_role(blob, title)
        or is_any_bachelor_field_job(blob, title)
        or is_professional_non_manual_role(blob, title)
        or is_bachelor_level_opportunity(blob, title)
        or job_has_course_relevance(job)
        or (
            BROAD_BACHELOR_TITLE.search(title)
            and (
                KNOWLEDGE_WORK_SIGNAL.search(blob)
                or JUNIOR_SIGNAL.search(blob)
                or BACHELOR_DEGREE_SIGNAL.search(blob)
                or job_has_course_relevance(job)
            )
        )
    )


def is_degree_level_posting(blob: str, title: str = "") -> bool:
    text = f"{title} {blob}"
    return bool(
        BACHELOR_DEGREE_SIGNAL.search(text)
        or is_any_bachelor_field_job(text, title)
        or is_bachelor_level_opportunity(text, title)
    )


def is_degree_requirement_met(match: dict, blob: str = "", title: str = "") -> bool:
    """Education/degree requirements fully met for a degree-level role."""
    if not is_degree_level_posting(blob, title):
        return False
    if not match:
        return is_bachelor_level_opportunity(blob, title) or is_any_bachelor_field_job(blob, title)
    edu_reqs = []
    for req in match.get("requirements_analysis") or []:
        text = (req.get("requirement") or "").lower()
        section = (req.get("section") or "").lower()
        if section == "education" or any(
            k in text
            for k in ("degree", "bachelor", "hochschul", "studium", "university", "abschluss", "graduate")
        ):
            edu_reqs.append(req)
    if edu_reqs:
        return all((r.get("status") or "").lower() == "met" for r in edu_reqs)
    return is_full_requirement_match(match)


def _title_matches_role_families(title: str, role_families: list[str]) -> bool:
    title_l = title.lower()
    for family in role_families:
        family_l = family.lower()
        if family_l in title_l:
            return True
        for word in family_l.split():
            if len(word) >= 5 and word in title_l:
                return True
    return False


def prefilter_jobs_for_candidate(
    jobs: list[dict],
    profile: dict | None = None,
    qualifications: dict | None = None,
    *,
    require_direct_apply_url: bool | None = None,
) -> tuple[list[dict], dict]:
    """
    Keep jobs in target region with a real description. Wide mode keeps almost all
    knowledge-work listings; strict mode requires CV keyword overlap.
    """
    if require_direct_apply_url is None:
        require_direct_apply_url = _env_bool("JOB_REQUIRE_DIRECT_APPLY_URL", True)
    profile = profile or load_profile()
    qualifications = qualifications or load_qualifications()
    keywords = [k.lower() for k in (profile.get("all_search_keywords") or [])]
    if not keywords:
        clusters = profile.get("search_keyword_clusters") or {}
        for terms in clusters.values():
            keywords.extend(t.lower() for t in terms)
        keywords = sorted(set(keywords))

    role_families = [r.lower() for r in qualifications.get("role_families_eligible", [])]
    title_aliases = [t.lower() for t in qualifications.get("title_aliases_to_recognize", [])]
    course_terms = [
        t.lower()
        for key in (
            "technical_qualifications",
            "support_qualifications",
            "stem_environment_qualifications",
            "people_qualifications",
            "teaching_qualifications",
            "counseling_and_ngo_qualifications",
            "office_and_service_qualifications",
            "digital_qualifications",
        )
        for t in (qualifications.get(key) or [])
        if isinstance(t, str) and len(t) >= 4
    ]
    match_terms = sorted(set(keywords + role_families + title_aliases + course_terms))

    stats = {
        "input": len(jobs),
        "wrong_location": 0,
        "no_description": 0,
        "irrelevant_role": 0,
        "senior_excluded": 0,
        "no_cv_overlap": 0,
        "bad_apply_url": 0,
        "student_program": 0,
        "kept": 0,
    }
    kept: list[dict] = []

    for job in jobs:
        if not is_target_region_job(job):
            stats["wrong_location"] += 1
            continue
        desc, _, title, _ = job_text_fields(job)
        if len(desc) < 80:
            stats["no_description"] += 1
            continue
        apply_url = (job.get("applyUrl") or job.get("url") or job.get("link") or "").strip()
        if not apply_url:
            resolved = resolve_apply_url(job)
            if resolved:
                job["applyUrl"] = resolved
                job["url"] = resolved
                apply_url = resolved
        if require_direct_apply_url:
            if not is_direct_apply_url(apply_url):
                external = _extract_external_apply_url(desc)
                if external:
                    job["applyUrl"] = external
                    job["url"] = external
                    apply_url = external
                else:
                    stats["bad_apply_url"] += 1
                    continue
        elif apply_url and not is_direct_apply_url(apply_url):
            external = _extract_external_apply_url(desc)
            if external:
                job["applyUrl"] = external
                job["url"] = external
        keep, reason = job_passes_candidate_prefilter(
            job,
            role_families=role_families,
            match_terms=match_terms,
        )
        if not keep:
            stats[reason if reason in stats else "irrelevant_role"] += 1
            continue
        kept.append(job)

    stats["kept"] = len(kept)
    return kept, stats


def finalize_jobs_cache(jobs: list[dict]) -> list[dict]:
    """Location + CV relevance filter applied before saving cache."""
    profile = load_profile()
    qualifications = load_qualifications()
    located = filter_germany_jobs(jobs)
    filtered, stats = prefilter_jobs_for_candidate(located, profile, qualifications)
    diagnostics = load_source_diagnostics()
    diagnostics["cv_prefilter"] = stats
    diagnostics["after_location_filter"] = len(located)
    diagnostics["after_cv_prefilter"] = len(filtered)
    diagnostics["total_jobs"] = len(filtered)
    save_source_diagnostics(diagnostics)
    if not filtered:
        raise RuntimeError(
            "No jobs matched your region AND CV keywords after filtering. "
            f"Region matches: {len(located)}; CV overlap: 0. "
            "Try Refresh again or add JOOBLE_API_KEY / a Germany Apify dataset."
        )
    try:
        previous = load_cached_jobs()
    except Exception:
        previous = []
    if previous:
        combined = _merge_job_lists([previous, filtered])
    else:
        combined = filtered
    save_jobs_cache(combined)
    return combined


def _match_payload_text(meta: dict) -> str:
    """Concatenate match fields for legacy-marker detection."""
    parts: list[str] = []
    match = meta.get("match") if isinstance(meta.get("match"), dict) else meta
    if not isinstance(match, dict):
        return str(meta or "")
    for row in match.get("requirements_analysis") or []:
        if isinstance(row, dict):
            parts.extend(
                str(row.get(key) or "")
                for key in ("requirement", "evidence", "section", "status")
            )
    for key in (
        "reasoning",
        "cultural_fit_summary",
        "title_vs_requirements_note",
        "logistics_notes",
    ):
        parts.append(str(match.get(key) or ""))
    for key in ("required_met", "required_missing", "preferred_met", "transferable_bridges"):
        parts.extend(str(x) for x in (match.get(key) or []))
    return " ".join(p for p in parts if p)


def is_legacy_match_payload(meta: dict) -> bool:
    """True when score belongs to the previous candidate or predates profile tagging."""
    if not isinstance(meta, dict):
        return True
    if meta.get("candidate_profile_id") != CANDIDATE_PROFILE_ID:
        return True
    return bool(LEGACY_MATCH_MARKERS.search(_match_payload_text(meta)))


def scrub_legacy_match_language(match: dict) -> dict:
    """Strip hallucinated references to the previous candidate profile."""
    if not isinstance(match, dict):
        return match

    def _clean(text: str) -> str:
        if not text or not LEGACY_MATCH_MARKERS.search(text):
            return text
        cleaned = LEGACY_MATCH_MARKERS.sub("", text)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;.-")
        return cleaned or "See CV: BA International Development, teaching, counseling, and office experience."

    for key in (
        "reasoning",
        "cultural_fit_summary",
        "title_vs_requirements_note",
        "logistics_notes",
    ):
        if isinstance(match.get(key), str):
            match[key] = _clean(match[key])
    for list_key in ("required_met", "required_missing", "preferred_met", "transferable_bridges"):
        items = match.get(list_key)
        if isinstance(items, list):
            match[list_key] = [_clean(str(x)) for x in items if _clean(str(x))]
    rows = match.get("requirements_analysis")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("requirement", "evidence"):
                if isinstance(row.get(key), str):
                    row[key] = _clean(row[key])
    return match


def clear_all_scored_runs() -> int:
    """Delete all saved AI score folders so jobs can be rescored from scratch."""
    import shutil

    removed = 0
    out = SCRIPT_DIR / "output"
    if out.exists():
        for run in list(out.iterdir()):
            if run.is_dir():
                shutil.rmtree(run, ignore_errors=True)
                removed += 1
    if SCORED_JOBS_PATH.exists():
        try:
            SCORED_JOBS_PATH.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def normalize_match_result(match: dict) -> dict:
    """Enforce requirements-based recommendation from must-have coverage (not title)."""
    if not isinstance(match, dict):
        return {"match_score": 0, "recommendation": "skip", "dealbreakers": ["Invalid AI response"]}

    match = scrub_legacy_match_language(match)
    must_total = int(match.get("must_have_total") or 0)
    must_met = int(match.get("must_have_met_count") or 0)
    score = int(match.get("match_score") or 0)
    dealbreakers = match.get("dealbreakers") or []
    logistics_ok = match.get("logistics_ok", True)

    ratio = (must_met / must_total) if must_total > 0 else (score / 100.0)

    if dealbreakers or logistics_ok is False:
        match["recommendation"] = "skip"
    elif MATCH_MODE == "broad":
        if score >= APPLY_SCORE_MIN and ratio >= 0.25:
            match["recommendation"] = "apply"
        elif score >= BROAD_SCORE_MIN or ratio >= 0.20:
            match["recommendation"] = "review"
        else:
            match["recommendation"] = "skip"
    elif must_total >= 6 and ratio < REVIEW_MUST_RATIO_MIN:
        match["recommendation"] = "skip"
        score = min(score, int(ratio * 100))
    elif score >= APPLY_SCORE_MIN and ratio >= APPLY_MUST_RATIO_MIN and must_met >= 1:
        match["recommendation"] = "apply"
    elif score >= REVIEW_SCORE_MIN and ratio >= REVIEW_MUST_RATIO_MIN:
        match["recommendation"] = "review"
    else:
        match["recommendation"] = "skip"

    match["match_score"] = max(0, min(100, score))
    match["must_have_coverage_pct"] = round(ratio * 100, 1)
    match["qualified_to_apply"] = is_qualified_to_apply(match)
    match["broad_opportunity"] = is_broad_opportunity(match)
    return match


def is_apply_list_job(match: dict, apply_url: str = "") -> bool:
    """Should appear on the user's apply list (direct link + no dealbreakers)."""
    if apply_url and not is_direct_apply_url(apply_url):
        return False
    if not isinstance(match, dict) or not match:
        return False
    if match.get("dealbreakers"):
        return False
    if match.get("logistics_ok") is False:
        return False
    score = int(match.get("match_score") or 0)
    rec = match.get("recommendation") or "skip"
    if MATCH_MODE == "broad":
        return is_broad_opportunity(match)
    if rec == "apply":
        return True
    if rec == "review" and score >= 40:
        return True
    if match.get("qualified_to_apply"):
        return True
    return False


def is_broad_opportunity(match: dict) -> bool:
    """Worth opening / applying — used for the mass opportunities list after AI scoring."""
    if match.get("dealbreakers"):
        return False
    if match.get("logistics_ok") is False:
        return False
    score = int(match.get("match_score") or 0)
    rec = match.get("recommendation")
    if rec == "skip" and score < BROAD_SCORE_MIN:
        return False
    return score >= BROAD_SCORE_MIN or rec in ("apply", "review")


def is_qualified_to_apply(match: dict) -> bool:
    """Jobs on the strict apply shortlist: strong apply, or solid review worth submitting."""
    if match.get("dealbreakers"):
        return False
    if match.get("logistics_ok") is False:
        return False
    score = int(match.get("match_score") or 0)
    must_total = int(match.get("must_have_total") or 0)
    must_met = int(match.get("must_have_met_count") or 0)
    ratio = (must_met / must_total) if must_total > 0 else (score / 100.0)
    rec = match.get("recommendation")
    if MATCH_MODE == "broad":
        return is_broad_opportunity(match)
    if rec == "apply":
        return score >= APPLY_SCORE_MIN and ratio >= APPLY_MUST_RATIO_MIN
    if rec == "review":
        return score >= max(APPLY_SCORE_MIN - 5, 45) and ratio >= REVIEW_MUST_RATIO_MIN
    return False


def fetch_remotive_germany_friendly() -> list[dict]:
    """Remote jobs that allow Germany / EU / worldwide (from Remotive API)."""
    batches: list[list[dict]] = []
    for category in REMOTIVE_CATEGORIES:
        try:
            time.sleep(0.8)
            batches.append(fetch_remotive_jobs(category))
        except Exception:
            continue
    merged = _merge_job_lists(batches)
    kept: list[dict] = []
    for job in merged:
        loc = _ensure_text(job.get("location"))
        blob = f"{loc} {_job_search_blob(job)}"
        if is_target_region_job(job):
            kept.append(job)
            continue
        if REMOTE_GERMANY_KEYWORDS.search(blob):
            kept.append(job)
            continue
        if re.search(
            r"\b(worldwide|anywhere|global|europe|european union|eu\b|emea)\b",
            blob,
            re.I,
        ):
            job["location"] = loc or "Remote (EU/worldwide)"
            kept.append(job)
    return kept


def fetch_germany_free_jobs(
    on_source_done=None,
) -> tuple[list[dict], list[dict]]:
    """Germany-focused free sources (no global US-heavy feeds)."""
    jobs: list[dict] = []
    sources_meta: list[dict] = []

    def _arbeitsagentur_loader():
        def _batch(partial: list[dict]) -> None:
            if not on_source_done or not partial:
                return
            try:
                merged = _merge_job_lists([*jobs, *partial])
                on_source_done(
                    source_name="Arbeitsagentur API (free DE)",
                    merged_jobs=merged,
                    sources_meta=list(sources_meta),
                    step=0,
                    total_steps=1,
                    partial=True,
                )
            except Exception:
                pass

        return fetch_arbeitsagentur_jobs(on_batch_done=_batch)

    fast = _env_bool("WEB_FAST_SEARCH", True)
    if fast:
        loaders = [
            ("Arbeitnow API (expanded)", fetch_arbeitnow_expanded),
            ("StepStone RSS (DE)", lambda: fetch_rss_jobs(STEPSTONE_RSS_URLS, "StepStone RSS")),
            ("Indeed RSS (DE)", lambda: fetch_rss_jobs(INDEED_RSS_URLS, "Indeed RSS")),
            ("Arbeitsagentur API (free DE)", _arbeitsagentur_loader),
            ("EURES EU job portal (free)", fetch_eures_jobs),
            ("Remotive API (remote DE/EU)", fetch_remotive_germany_friendly),
        ]
    else:
        loaders = [
            ("Arbeitsagentur API (free DE)", _arbeitsagentur_loader),
            ("EURES EU job portal (free)", fetch_eures_jobs),
            ("Arbeitnow API (expanded)", fetch_arbeitnow_expanded),
            ("Remotive API (remote DE/EU)", fetch_remotive_germany_friendly),
            ("StepStone RSS (DE)", lambda: fetch_rss_jobs(STEPSTONE_RSS_URLS, "StepStone RSS")),
            ("Indeed RSS (DE)", lambda: fetch_rss_jobs(INDEED_RSS_URLS, "Indeed RSS")),
            ("Adzuna RSS (DE)", lambda: fetch_rss_jobs(ADZUNA_RSS_URLS, "Adzuna RSS")),
            ("Remote jobs RSS", lambda: fetch_rss_jobs(RSS_JOB_FEED_URLS, "Remote jobs RSS")),
        ]
    jooble_key = os.getenv("JOOBLE_API_KEY", "").strip()
    if jooble_key and not fast:
        for keyword, city in build_jooble_search_matrix():
            loaders.append((
                f"Jooble API ({keyword}, {city})",
                lambda c=city, kw=keyword, key=jooble_key: fetch_jooble_jobs(key, kw, c),
            ))

    total_loaders = len(loaders)
    for index, (name, loader) in enumerate(loaders, start=1):
        try:
            from cvapp import pipeline_status as pstatus
            if pstatus.is_cancelled():
                break
        except Exception:
            pass
        try:
            source_jobs = loader()
            filtered = filter_germany_jobs(source_jobs)
            sources_meta.append({
                "source": name,
                "count": len(filtered),
                "raw_count": len(source_jobs),
                "status": "ok" if filtered else "empty",
            })
            jobs.extend(filtered)
            merged = _merge_job_lists([jobs])
            if on_source_done:
                on_source_done(
                    source_name=name,
                    merged_jobs=merged,
                    sources_meta=list(sources_meta),
                    step=index,
                    total_steps=total_loaders,
                )
        except Exception as exc:
            sources_meta.append({"source": name, "count": 0, "status": "error", "error": str(exc)})
            if on_source_done:
                on_source_done(
                    source_name=name,
                    merged_jobs=_merge_job_lists([jobs]),
                    sources_meta=list(sources_meta),
                    step=index,
                    total_steps=total_loaders,
                    error=str(exc)[:120],
                )

    return _merge_job_lists([jobs]), sources_meta


def _actor_id_to_slug(actor_id: str) -> str:
    return actor_id.strip().replace("/", "~")


def load_apify_sources_config() -> dict:
    if not APIFY_SOURCES_PATH.is_file():
        return {"actors": []}
    try:
        return json.loads(APIFY_SOURCES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"actors": []}


def load_apify_input_config(filename: str) -> dict:
    path = APIFY_CONFIG_DIR / filename
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_apify_dataset_specs() -> list[tuple[str, str]]:
    """Return (label, dataset_id) from APIFY_DATASET_IDS and legacy APIFY_DATASET_ID."""
    specs: list[tuple[str, str]] = []
    multi = os.getenv("APIFY_DATASET_IDS", "").strip()
    if multi:
        for part in multi.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                label, ds_id = part.split(":", 1)
                specs.append((label.strip() or "Apify", ds_id.strip()))
            else:
                specs.append(("Apify dataset", part))
    legacy = os.getenv("APIFY_DATASET_ID", "").strip()
    if legacy and not any(ds_id == legacy for _, ds_id in specs):
        specs.append(("Apify (legacy)", legacy))
    return specs


def fetch_apify_dataset_items(apify_token: str, dataset_id: str) -> list[dict]:
    url = (
        f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        f"?clean=true&token={apify_token}"
    )
    response = requests.get(url, timeout=90, headers=DEFAULT_REQUEST_HEADERS)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []
    return data


def run_apify_actor_sync(
    apify_token: str,
    actor_id: str,
    run_input: dict,
    *,
    timeout_secs: int = 300,
) -> list[dict]:
    """Run an Apify actor synchronously and return dataset items (billed per Apify pricing)."""
    slug = _actor_id_to_slug(actor_id)
    url = f"https://api.apify.com/v2/acts/{slug}/run-sync-get-dataset-items"
    params = {
        "token": apify_token,
        "timeout": timeout_secs,
        "memory": 1024,
    }
    response = requests.post(
        url,
        params=params,
        json=run_input,
        timeout=timeout_secs + 60,
        headers=DEFAULT_REQUEST_HEADERS,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


def _indeed_search_run_input(base_cfg: dict, search: dict) -> dict:
    return {
        "country": base_cfg.get("country", "de"),
        "query": search.get("query", "IT Support"),
        "location": search.get("location", "Frankfurt"),
        "maxResults": int(base_cfg.get("maxResultsPerSearch", 30)),
    }


def fetch_apify_via_configured_actors(apify_token: str) -> tuple[list[dict], list[dict]]:
    """Run enabled actors from config/apify_sources.json (Indeed, LinkedIn, etc.)."""
    cfg = load_apify_sources_config()
    max_runs = _env_int("APIFY_MAX_ACTOR_RUNS", 12)
    runs_done = 0
    batches: list[list[dict]] = []
    sources_meta: list[dict] = []

    linkedin_actor_override = os.getenv("APIFY_LINKEDIN_ACTOR_ID", "").strip()

    for actor_cfg in cfg.get("actors") or []:
        if not actor_cfg.get("enabled"):
            continue
        actor_id = (actor_cfg.get("actorId") or "").strip()
        if actor_cfg.get("key") == "linkedin" and linkedin_actor_override:
            actor_id = linkedin_actor_override
        if not actor_id:
            sources_meta.append({
                "source": actor_cfg.get("sourceLabel", "Apify actor"),
                "count": 0,
                "raw_count": 0,
                "status": "skipped",
                "error": "No actorId — set in apify_sources.json or APIFY_LINKEDIN_ACTOR_ID",
            })
            continue

        label = actor_cfg.get("sourceLabel") or actor_id
        input_name = actor_cfg.get("inputConfig") or ""
        base_input = load_apify_input_config(input_name) if input_name else {}
        run_mode = actor_cfg.get("runMode", "single")

        try:
            if run_mode == "searches":
                raw_jobs: list[dict] = []
                for search in base_input.get("searches") or []:
                    if runs_done >= max_runs:
                        break
                    run_input = _indeed_search_run_input(base_input, search)
                    items = run_apify_actor_sync(apify_token, actor_id, run_input)
                    raw_jobs.extend(items)
                    runs_done += 1
                    time.sleep(1.0)
            else:
                if runs_done >= max_runs:
                    continue
                # Drop _comment keys from input JSON
                run_input = {k: v for k, v in base_input.items() if not str(k).startswith("_")}
                items = run_apify_actor_sync(apify_token, actor_id, run_input)
                raw_jobs = items
                runs_done += 1

            normalized = [_normalize_job(job, label) for job in raw_jobs]
            filtered = filter_germany_jobs(normalized)
            sources_meta.append({
                "source": label,
                "count": len(filtered),
                "raw_count": len(raw_jobs),
                "status": "ok" if filtered else "empty",
                "actorId": actor_id,
            })
            batches.append(filtered)
        except Exception as exc:
            sources_meta.append({
                "source": label,
                "count": 0,
                "raw_count": 0,
                "status": "error",
                "error": str(exc)[:200],
                "actorId": actor_id,
            })

    return _merge_job_lists(batches), sources_meta


def fetch_all_apify_jobs(apify_token: str) -> tuple[list[dict], list[dict]]:
    """Merge jobs from saved dataset IDs + optional live actor runs (APIFY_AUTO_RUN)."""
    batches: list[list[dict]] = []
    sources_meta: list[dict] = []

    for label, dataset_id in parse_apify_dataset_specs():
        try:
            raw = fetch_apify_dataset_items(apify_token, dataset_id)
            normalized = [_normalize_job(job, label) for job in raw]
            filtered = filter_germany_jobs(normalized)
            sources_meta.append({
                "source": label,
                "count": len(filtered),
                "raw_count": len(raw),
                "status": "ok" if raw else "empty",
                "datasetId": dataset_id,
            })
            batches.append(filtered)
        except Exception as exc:
            sources_meta.append({
                "source": label,
                "count": 0,
                "raw_count": 0,
                "status": "error",
                "error": str(exc)[:200],
                "datasetId": dataset_id,
            })

    auto_run = os.getenv("APIFY_AUTO_RUN", "").strip().lower() in ("1", "true", "yes", "on")
    if auto_run:
        actor_jobs, actor_meta = fetch_apify_via_configured_actors(apify_token)
        sources_meta.extend(actor_meta)
        if actor_jobs:
            batches.append(actor_jobs)

    return _merge_job_lists(batches), sources_meta


def refresh_jobs_cache(*, include_apify: bool = True, on_progress=None) -> list[dict]:
    """
    Unified refresh: merge free DE sources (always) + optional Apify datasets / auto-run.
    If Apify is empty or US-only, free sources still fill the cache (automatic fallback).
    """
    clear_live_jobs()

    def _live_update(**kwargs):
        if on_progress:
            on_progress(**kwargs)

    def _after_source(**kwargs):
        merged_jobs = kwargs.get("merged_jobs") or []
        sources_meta = kwargs.get("sources_meta") or []
        save_live_jobs(merged_jobs, sources=sources_meta)
        fields = {
            "phase": "search",
            "live_count": len(merged_jobs),
            "latest_jobs": _jobs_for_live_feed(merged_jobs),
            "sources": sources_meta,
        }
        if kwargs.get("partial"):
            fields["message"] = f"Loading jobs… {len(merged_jobs)} ready so far"
        else:
            fields["message"] = (
                f"Searching… {kwargs.get('source_name', '')} "
                f"({kwargs.get('step', 0)}/{kwargs.get('total_steps', 0)})"
            )
            fields["progress"] = kwargs.get("step", 0)
            fields["total"] = kwargs.get("total_steps", 0)
        _live_update(**fields)

    free_jobs, free_sources = fetch_germany_free_jobs(on_source_done=_after_source)
    apify_jobs: list[dict] = []
    apify_sources: list[dict] = []
    apify_raw_total = 0
    apify_errors: list[str] = []

    if include_apify and not _env_bool("WEB_FAST_SEARCH", True):
        token = os.getenv("APIFY_TOKEN", "").strip()
        auto_run = os.getenv("APIFY_AUTO_RUN", "").strip().lower() in ("1", "true", "yes", "on")
        has_datasets = bool(parse_apify_dataset_specs())
        if token and (has_datasets or auto_run):
            _live_update(phase="search", message="Searching paid sources (Apify)…")
            try:
                apify_jobs, apify_sources = fetch_all_apify_jobs(token)
                merged_so_far = filter_germany_jobs(_merge_job_lists([apify_jobs, free_jobs]))
                save_live_jobs(merged_so_far, sources=[*apify_sources, *free_sources])
                _live_update(
                    phase="search",
                    message=f"Apify done · {len(apify_jobs)} jobs",
                    live_count=len(merged_so_far),
                    latest_jobs=_jobs_for_live_feed(merged_so_far),
                    sources=[*apify_sources, *free_sources],
                )
            except Exception as exc:
                apify_errors.append(str(exc)[:200])
                apify_sources.append({
                    "source": "Apify",
                    "count": 0,
                    "raw_count": 0,
                    "status": "error",
                    "error": str(exc)[:200],
                })

    apify_raw_total = sum(m.get("raw_count", 0) for m in apify_sources)
    merged = filter_germany_jobs(_merge_job_lists([apify_jobs, free_jobs]))
    _live_update(
        phase="filter",
        message=f"Filtering {len(merged)} jobs for your region and skills…",
        live_count=len(merged),
        latest_jobs=_jobs_for_live_feed(merged),
    )
    min_apify = _env_int("APIFY_MIN_REGION_JOBS", 5)
    apify_weak = len(apify_jobs) < min_apify

    diagnostics = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "fetch_mode": "unified",
        "apify_raw": apify_raw_total,
        "apify_germany": len(apify_jobs),
        "free_in_region": len(free_jobs),
        "apify_auto_run": os.getenv("APIFY_AUTO_RUN", "").strip().lower() in ("1", "true", "yes", "on"),
        "apify_fallback_used": apify_weak and len(free_jobs) > 0,
        "apify_errors": apify_errors,
        "sources": [*apify_sources, *free_sources],
    }
    diagnostics["filtered_out"] = max(0, apify_raw_total - len(apify_jobs))
    diagnostics["merged_before_cv_filter"] = len(merged)
    save_source_diagnostics(diagnostics)

    if not merged:
        raise RuntimeError(
            "No jobs in Frankfurt / Köln / Bonn / Düsseldorf after merging all sources. "
            f"Apify in-region: {len(apify_jobs)} (raw {apify_raw_total}); free in-region: {len(free_jobs)}."
        )
    return finalize_jobs_cache(merged)


def fetch_jobs(apify_token: str, dataset_id: str | None = None) -> list[dict]:
    if dataset_id:
        os.environ["APIFY_DATASET_ID"] = dataset_id
    return refresh_jobs_cache(include_apify=True)


def verify_apify_dataset(apify_token: str, dataset_id: str) -> dict:
    """Quick check: sample locations from an Apify dataset (for debugging US vs DE data)."""
    raw = fetch_apify_dataset_items(apify_token, dataset_id)
    normalized = [_normalize_job(job, "Apify") for job in raw[:100]]
    in_region = filter_germany_jobs(normalized)
    locations: list[str] = []
    for job in normalized[:15]:
        locations.append(str(job.get("location") or job.get("country") or "?")[:80])
    return {
        "dataset_id": dataset_id,
        "raw_count": len(raw),
        "sample_size": len(normalized),
        "in_target_region": len(in_region),
        "sample_locations": locations,
        "ok_for_germany": len(in_region) >= max(1, len(normalized) // 10),
    }


def fetch_remotive_jobs(category: str | None = None) -> list[dict]:
    url = REMOTIVE_URL
    params = {}
    if category:
        params["search"] = category
    response = requests.get(url, params=params, timeout=60, headers=DEFAULT_REQUEST_HEADERS)
    response.raise_for_status()
    data = response.json()
    jobs = data.get("jobs") or []
    normalized = []
    for job in jobs:
        normalized.append(_normalize_job({
            "title": job.get("title"),
            "company": job.get("company_name") or job.get("company"),
            "location": job.get("candidate_required_location"),
            "description": job.get("description"),
            "url": job.get("url") or job.get("job_url") or job.get("application_url"),
        }, "Remotive API"))
    return normalized


def fetch_arbeitnow_jobs(max_pages: int = 3, search: str | None = None) -> list[dict]:
    """Arbeitnow free API (100 jobs/page). Rate-limited — use polite delays."""
    jobs: list[dict] = []
    try:
        for page in range(1, max_pages + 1):
            if page > 1:
                time.sleep(2.0)
            params: dict = {"page": page}
            if search:
                params["search"] = search
            response = requests.get(
                ARBEITNOW_URL,
                params=params,
                timeout=60,
                headers=DEFAULT_REQUEST_HEADERS,
            )
            if response.status_code == 403:
                break
            response.raise_for_status()
            data = response.json()
            records = data.get("data") or data.get("jobs") or []
            if not records:
                break
            for job in records:
                title = _ensure_text(job.get("title") or job.get("position"))
                if not title or EXCLUDED_TITLE.search(title):
                    continue
                desc = _ensure_text(job.get("description") or job.get("remote"))
                stub = {
                    "title": title,
                    "company": job.get("company_name") or job.get("company"),
                    "location": job.get("location"),
                    "description": desc,
                    "url": job.get("url") or job.get("job_url") or job.get("website"),
                }
                if not (is_it_focused_job(stub) or is_non_it_degree_job(stub)):
                    continue
                jobs.append(_normalize_job(stub, "Arbeitnow API"))
    except Exception:
        pass
    return jobs


def _arbeitsagentur_headers() -> dict:
    return {
        **DEFAULT_REQUEST_HEADERS,
        "X-API-Key": ARBEITSAGENTUR_API_KEY,
    }


def _strip_html_to_text(html: str, limit: int = 12000) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _html_meta_content(html: str, *, name: str = "", prop: str = "") -> str:
    if prop:
        pattern = (
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\']'
            r'[^>]+content=["\']([^"\']+)'
        )
    else:
        pattern = (
            rf'<meta[^>]+name=["\']{re.escape(name)}["\']'
            r'[^>]+content=["\']([^"\']+)'
        )
    match = re.search(pattern, html, re.I)
    return _ensure_text(match.group(1)) if match else ""


def import_job_from_url(raw_url: str, api_key: str = "") -> dict:
    """Fetch one job posting from a pasted URL (Arbeitsagentur API or generic page)."""
    from urllib.parse import urlparse

    url = normalize_apply_url((raw_url or "").strip())
    if not url.startswith("http"):
        raise ValueError("Paste a full job URL starting with https://")

    refnr = _extract_arbeitsagentur_refnr(url)
    if not refnr:
        jv_id = _eures_jvid_from_url(url)
        if jv_id:
            refnr = _decode_eures_jvid(jv_id)

    if refnr:
        encoded = base64.b64encode(refnr.encode("utf-8")).decode("ascii")
        response = requests.get(
            f"{ARBEITSAGENTUR_DETAILS_URL}/{encoded}",
            headers=_arbeitsagentur_headers(),
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        ort, plz = _arbeitsort_parts(data.get("arbeitsort"))
        loc = ", ".join(part for part in (plz, ort) if part) or "Germany"
        if "germany" not in loc.lower():
            loc = f"{loc}, Germany"
        description, external = _fetch_arbeitsagentur_job_detail(refnr)
        if not description:
            description = _ensure_text(
                data.get("stellenangebotsBeschreibung") or data.get("stellenbeschreibung") or ""
            )
        apply_url = (
            external
            if external and is_job_listing_url(external)
            else arbeitsagentur_jobdetail_url(refnr)
        )
        return {
            "title": _ensure_text(data.get("titel") or data.get("beruf") or "Job posting"),
            "company": _arbeitgeber_label(data.get("arbeitgeber")) or "Unknown company",
            "location": loc,
            "description": description,
            "url": arbeitsagentur_jobdetail_url(refnr),
            "applyUrl": apply_url,
            "refnr": refnr,
            "source": "Imported · Arbeitsagentur",
            "provider": "Imported",
        }

    response = requests.get(
        url, timeout=35, headers=DEFAULT_REQUEST_HEADERS, allow_redirects=True
    )
    response.raise_for_status()
    html = response.text
    title = (
        _html_meta_content(html, prop="og:title")
        or _html_meta_content(html, name="twitter:title")
        or ""
    )
    if not title:
        title_match = re.search(r"(?is)<title[^>]*>([^<]+)</title>", html)
        title = _ensure_text(title_match.group(1)) if title_match else ""
    title = title.split("|")[0].split(" - ")[0].strip() or "Imported job"
    company = urlparse(url).netloc.replace("www.", "")
    location = ""
    description = (
        _html_meta_content(html, prop="og:description")
        or _html_meta_content(html, name="description")
        or ""
    )
    body_text = _strip_html_to_text(html)
    if api_key and len(body_text) > 200:
        try:
            parsed = mistral_json(
                api_key,
                "Extract job posting fields from web page text. " + ENGLISH_OUTPUT_RULE,
                (
                    f"URL: {url}\n\nText:\n{body_text[:9000]}\n\n"
                    'Return JSON: {"title":"","company":"","location":"","description":""}'
                ),
                model=MATERIALS_MODEL,
            )
            if isinstance(parsed, dict):
                title = _ensure_text(parsed.get("title")) or title
                company = _ensure_text(parsed.get("company")) or company
                location = _ensure_text(parsed.get("location")) or location
                description = _ensure_text(parsed.get("description")) or description
        except Exception:
            pass
    if not description or len(description) < 120:
        description = body_text
    if len(description) < 80:
        description = body_text[:8000] or f"Job posting imported from {url}"

    return {
        "title": title,
        "company": company or "Unknown company",
        "location": location,
        "description": description[:12000],
        "url": url,
        "applyUrl": url,
        "source": "Imported link",
        "provider": "Imported",
    }


def _fetch_arbeitsagentur_job_detail(refnr: str) -> tuple[str, str]:
    encoded = base64.b64encode(refnr.encode("utf-8")).decode("ascii")
    response = requests.get(
        f"{ARBEITSAGENTUR_DETAILS_URL}/{encoded}",
        headers=_arbeitsagentur_headers(),
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    description = _ensure_text(
        data.get("stellenangebotsBeschreibung")
        or data.get("stellenbeschreibung")
        or ""
    )
    external = _extract_external_apply_url(description)
    return description, external


def fetch_arbeitsagentur_jobs(
    max_searches: int | None = None,
    max_detail_fetches: int | None = None,
    *,
    on_batch_done=None,
) -> list[dict]:
    """
    Free official German job database (Bundesagentur für Arbeit).
    No API key signup — public X-API-Key: jobboerse-jobsuche
    """
    searches = build_arbeitsagentur_searches()
    max_searches = max_searches or _env_int("ARBEITSAGENTUR_MAX_SEARCHES", 16)
    max_detail_fetches = max_detail_fetches or _env_int("ARBEITSAGENTUR_MAX_DETAILS", 80)
    max_pages = _env_int("ARBEITSAGENTUR_PAGES", 2)
    listings: dict[str, dict] = {}

    for was, wo in searches[:max_searches]:
        for page in range(1, max_pages + 1):
            try:
                time.sleep(0.35)
                response = requests.get(
                    ARBEITSAGENTUR_JOBS_URL,
                    params={"was": was, "wo": wo, "umkreis": 35, "size": 25, "page": page},
                    headers=_arbeitsagentur_headers(),
                    timeout=45,
                )
                response.raise_for_status()
                data = response.json()
                rows = _arbeitsagentur_search_rows(data)
                if not rows:
                    break
                for row in rows:
                    refnr = row.get("refnr")
                    if not refnr or refnr in listings:
                        continue
                    ort, _plz = _arbeitsort_parts(row.get("arbeitsort"), fallback=wo)
                    listings[refnr] = {
                        "title": _ensure_text(row.get("titel") or row.get("beruf") or "Unknown title"),
                        "company": _arbeitgeber_label(row.get("arbeitgeber")) or "Unknown company",
                        "location": f"{ort}, Germany",
                        "description": "",
                        "url": arbeitsagentur_jobdetail_url(refnr),
                        "refnr": refnr,
                    }
            except Exception:
                continue

    jobs: list[dict] = []
    details_fetched = 0
    for refnr, stub in listings.items():
        if details_fetched >= max_detail_fetches:
            break
        try:
            time.sleep(0.25)
            description, external_url = _fetch_arbeitsagentur_job_detail(refnr)
            stub["description"] = description or (
                f"{stub['title']} at {stub['company']}. {stub['location']}."
            )
            if external_url and is_job_listing_url(external_url):
                # Keep the official Arbeitsagentur listing unless the external link is a direct employer ATS.
                if "arbeitsagentur.de/jobsuche/jobdetail" not in (stub.get("url") or "").lower():
                    stub["url"] = external_url
                elif "arbeitsagentur.de" not in external_url.lower():
                    stub["url"] = external_url
            details_fetched += 1
        except Exception:
            stub["description"] = f"{stub['title']} at {stub['company']}. {stub['location']}."
        try:
            jobs.append(_normalize_job(stub, "Arbeitsagentur API"))
        except Exception:
            continue
        if on_batch_done and len(jobs) % 20 == 0:
            try:
                on_batch_done(list(jobs))
            except Exception:
                pass
    if on_batch_done and jobs:
        try:
            on_batch_done(list(jobs))
        except Exception:
            pass
    return jobs


EURES_SEARCH_URL = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"


def _eures_search_payload(keyword: str, page: int) -> dict:
    return {
        "resultsPerPage": 25,
        "page": page,
        "sortSearch": "MOST_RECENT",
        "keywords": [{"keyword": keyword[:120], "specificSearchCode": "EVERYWHERE"}],
        "occupationUris": [],
        "skillUris": [],
        "requiredExperienceCodes": [],
        "positionScheduleCodes": [],
        "sectorCodes": [],
        "educationAndQualificationLevelCodes": [],
        "positionOfferingCodes": [],
        "locationCodes": ["de"],
        "euresFlagCodes": [],
        "otherBenefitsCodes": [],
        "requiredLanguages": [],
        "minNumberPost": None,
        "sessionId": "ivana-cv-jobsearch",
        "requestLanguage": "en",
        "publicationPeriod": None,
    }


def _parse_eures_location(jv: dict, description: str) -> str:
    loc_map = jv.get("locationMap") or {}
    de_codes = loc_map.get("DE") or []
    if de_codes:
        return f"{de_codes[0]}, Germany"
    match = re.search(r"Standort:\s*([^<\n,]+)", description, re.I)
    if match:
        return f"{match.group(1).strip()}, Germany"
    return "Germany"


def fetch_eures_jobs() -> list[dict]:
    """European Employment Services (EURES) — EU public job portal, Germany filter."""
    from urllib.parse import quote

    keywords = profile_search_keywords(24)
    max_keywords = _env_int("EURES_MAX_KEYWORDS", 18)
    max_pages = _env_int("EURES_MAX_PAGES", 3)
    seen_ids: set[str] = set()
    jobs: list[dict] = []
    headers = {
        **DEFAULT_REQUEST_HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    for keyword in keywords[:max_keywords]:
        for page in range(1, max_pages + 1):
            try:
                time.sleep(0.45)
                response = requests.post(
                    EURES_SEARCH_URL,
                    json=_eures_search_payload(keyword, page),
                    headers=headers,
                    timeout=45,
                )
                response.raise_for_status()
                rows = response.json().get("jvs") or []
                if not rows:
                    break
                for row in rows:
                    jid = row.get("id")
                    if not jid or jid in seen_ids:
                        continue
                    seen_ids.add(jid)
                    description = _strip_html(row.get("description") or "")
                    employer = (row.get("employer") or {}).get("name") or ""
                    refnr = _decode_eures_jvid(jid)
                    aa_url = arbeitsagentur_jobdetail_url(refnr) if refnr else ""
                    jobs.append(_normalize_job({
                        "title": row.get("title") or "Unknown title",
                        "company": employer,
                        "location": _parse_eures_location(row, description),
                        "description": description,
                        "url": aa_url or f"https://europa.eu/eures/portal/jv-detail/jv?jvId={quote(jid, safe='')}",
                        "refnr": refnr,
                    }, "EURES (EU)"))
            except Exception:
                break
    return jobs


def fetch_arbeitnow_expanded() -> list[dict]:
    """Multiple keyword/location queries to pull more listings into the cache."""
    pages = _env_int("ARBEITNOW_MAX_PAGES", 5)
    batches: list[list[dict]] = [fetch_arbeitnow_jobs(max_pages=pages)]
    for query in build_arbeitnow_queries():
        time.sleep(1.2)
        batches.append(fetch_arbeitnow_jobs(max_pages=2, search=query))
    return _merge_job_lists(batches)


def fetch_jooble_jobs(api_key: str | None = None, keywords: str = "IT Support", location: str = "Frankfurt") -> list[dict]:
    if not api_key:
        return []
    jobs: list[dict] = []
    url = JOOBLE_API_BASE_URL.rstrip("/") + "/" + api_key
    payload = {
        "keywords": keywords,
        "location": location,
        "page": 1,
    }
    try:
        response = requests.post(url, json=payload, timeout=60, headers=DEFAULT_REQUEST_HEADERS)
        response.raise_for_status()
        data = response.json()
        results = data.get("jobs") or data.get("results") or data.get("data") or []
        for job in results:
            jobs.append(_normalize_job({
                "title": job.get("title") or job.get("position"),
                "company": job.get("company"),
                "location": job.get("location"),
                "description": job.get("description"),
                "url": job.get("url") or job.get("link") or job.get("apply_url"),
            }, "Jooble API"))
    except Exception:
        pass
    return jobs


def _location_hint_from_feed_url(feed_url: str) -> str:
    url = feed_url.lower()
    hints = (
        ("frankfurt", "Frankfurt am Main, Germany"),
        ("koeln", "Köln, Germany"),
        ("cologne", "Cologne, Germany"),
        ("bonn", "Bonn, Germany"),
        ("duesseldorf", "Düsseldorf, Germany"),
        ("dusseldorf", "Düsseldorf, Germany"),
        ("mainz", "Mainz, Germany"),
        ("wiesbaden", "Wiesbaden, Germany"),
        ("darmstadt", "Darmstadt, Germany"),
        ("offenbach", "Offenbach, Germany"),
        ("hanau", "Hanau, Germany"),
        ("köln", "Köln, Germany"),
        ("k%C3%B6ln", "Köln, Germany"),
        ("d%C3%BCsseldorf", "Düsseldorf, Germany"),
    )
    for key, label in hints:
        if key in url:
            return label
    return ""


def fetch_rss_jobs(feed_urls: list[str], source_name: str = "RSS") -> list[dict]:
    jobs: list[dict] = []
    for feed_url in feed_urls:
        location_hint = _location_hint_from_feed_url(feed_url)
        try:
            response = requests.get(feed_url, timeout=30, headers=DEFAULT_REQUEST_HEADERS)
            response.raise_for_status()
            content = response.content
            root = __import__("xml.etree.ElementTree", fromlist=["ElementTree"]).fromstring(content)
            for item in root.findall(".//item"):
                title = item.findtext("title", default="Unknown title")
                description = item.findtext("description", default="") or item.findtext("summary", default="")
                link = item.findtext("link", default="")
                company = item.findtext("author", default="") or _parse_company_from_title(title)
                location = item.findtext("location", default="") or location_hint
                link = normalize_apply_url(link)
                if not is_job_listing_url(link):
                    for raw in re.findall(r"https?://[^\s<>\"']+", description):
                        candidate = normalize_apply_url(raw.rstrip(".,;)\\]'"))
                        if is_job_listing_url(candidate):
                            link = candidate
                            break
                jobs.append(_normalize_job({
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": description,
                    "url": link,
                }, source_name))
        except Exception:
            continue
    return jobs


def fetch_free_jobs() -> list[dict]:
    return refresh_jobs_cache(include_apify=False)


def load_jobs(use_cache: bool = True, source: str = "auto") -> list[dict]:
    if use_cache:
        return load_cached_jobs()
    if source == "free":
        return fetch_free_jobs()
    apify_token = os.getenv("APIFY_TOKEN", "").strip()
    apify_ready = bool(
        parse_apify_dataset_specs()
        or os.getenv("APIFY_AUTO_RUN", "").strip().lower() in ("1", "true", "yes", "on")
    )
    if source == "free":
        return refresh_jobs_cache(include_apify=False)
    return refresh_jobs_cache(include_apify=True)


def is_germany_job(job: dict) -> bool:
    return is_target_region_job(job)


def job_text_fields(job: dict) -> tuple[str, str, str, str]:
    description = (
        job.get("descriptionText")
        or job.get("descriptionHtml")
        or job.get("jobDescription")
        or job.get("description")
        or ""
    ).strip()
    about_us = _ensure_text(job.get("companyDescription"))
    title = _ensure_text(job.get("title") or "Unknown title")
    company = _ensure_text(
        job.get("companyName")
        or job.get("company_name")
        or job.get("company")
        or "Unknown company"
    )
    return description, about_us, title, company


def match_job(
    api_key: str,
    cv: str,
    job: dict,
    profile: dict | None = None,
) -> dict:
    description, about_us, title, company = job_text_fields(job)
    profile = profile or load_profile()
    loc_prefs = profile.get("location_preferences", {})
    about_block = f"\n## Company About Us\n{about_us}\n" if about_us else ""
    context = build_matching_context(cv, profile)

    quals = load_qualifications()
    system = (
        "You are a strict requirements-based job-fit analyst for Germany/EU hiring. "
        "IGNORE the job title unless it aligns with extracted requirements. "
        "Step 1: Extract EVERY must-have skill, tool, years of experience, degree, language, and "
        "location requirement from the posting (Qualifications, Requirements, Must have, Profile, Skills). "
        "Step 2: Map each must-have to the candidate qualifications inventory with evidence from the CV. "
        "Step 3: Score ONLY from requirement coverage — never from title prestige. "
        "Candidate has BA International Development and authorized teacher training: match knowledge-work roles "
        "(education, counseling, languages, office, coordination, NGO, reception, research support) when requirements align. "
        "Candidate is based in Frankfurt am Main — target Rhine-Main, Hesse, and NRW or remote/hybrid Germany/EU. "
        "Use dealbreakers from profile for US-only, senior 5+ years, licenses not held. "
        f"{ENGLISH_OUTPUT_RULE} "
        f"{MATCH_SCHEMA}"
    )
    user = f"""{context}

## Eligible role families (title hints only — includes non-IT bachelor roles)
{json.dumps(quals.get('role_families_eligible', []))}

## Job posting
Title (hint only): {title}
Company: {company}
Location: {job.get('location')}
Remote: {job.get('workRemoteAllowed')}

## Full description — extract requirements from THIS text
{description}
{about_block}

Target cities: {loc_prefs.get('cities', [])}
Rules:
- Set must_have_total = count of explicit must-have requirements you extracted (minimum 5 if posting is detailed).
- must_have_met_count = requirements with status met (partial counts as 0.5, round down).
- match_score = round(100 * must_have_met_count / max(must_have_total, 1)) adjusting -15 max for logistics.
- English: if posting is English-speaking or requires fluent English, status met (candidate fluent).
- German: B1/B2 or "advantage" = partial; only native/C1+ mandatory German is a real gap. International/English teams = German often partial.
- Degree: generic Bachelor/university degree/Hochschulabschluss/any field = met via BA International Development and pedagogical authorization.
- Sachbearbeiter / office / admin / coordinator: met if candidate has reception, documentation, multilingual, or program coordination experience.
- Teaching / Sprachkurs / education roles: met or partial via authorized teacher status, Spanish and Norwegian instruction experience.
- NGO / social program roles: partial-to-met via Hope for Justice and career counseling background.
- Trainee / Traineeprogramm / Berufseinsteiger after studies: entry path — score 50%+ when degree + transferable skills align.
- Experience: "first job", Berufseinsteiger, graduate, trainee = do not require 3+ years; map teaching, counseling, and reception as evidence.
- Education-first: score from BA International Development, pedagogy, languages, and people-facing experience — NOT from having worked in that exact field before in Germany.
- NEVER cite 199 ECTS, Dell, Addis Ababa, computer science degree, or technical support awards — not in this CV.
- Evidence in requirements_analysis should cite teaching, counseling, reception, and education from the CV only.
- recommendation apply if match_score >= {APPLY_SCORE_MIN}, must_have_met_count/must_have_total >= {APPLY_MUST_RATIO_MIN}, must_have_met_count >= 1, no dealbreakers.
- recommendation review if score >= {REVIEW_SCORE_MIN} and ratio >= {REVIEW_MUST_RATIO_MIN}.
- else skip.
- required_met / required_missing must list concrete skills from the posting, not generic traits.
- requirements_analysis: at least 6 rows with requirement, section, status, evidence citing CV facts.
- {ENGLISH_OUTPUT_RULE}
"""
    raw = mistral_json(api_key, system, user, model=SCORE_MODEL)
    return ensure_match_english(api_key, normalize_match_result(raw))


def generate_materials(
    api_key: str,
    cv: str,
    job: dict,
    match: dict,
    profile: dict | None = None,
) -> dict:
    description, about_us, title, company = job_text_fields(job)
    profile = profile or load_profile()
    about_block = f"\n## Company About Us\n{about_us}\n" if about_us else ""
    system = (
        "Write truthful tailored application materials. Only facts from CV. "
        "Emphasize flexible education and transferable skills for Germany market. "
        f"{MATERIALS_SCHEMA}"
    )
    user = f"""CV:\n{cv}\n\nProfile:\n{json.dumps(profile)}\n\nRole: {title} @ {company}\n\nMatch:\n{json.dumps(match)}\n\nJob:\n{description}\n{about_block}"""
    raw = mistral_json(api_key, system, user)
    return normalize_materials_result(raw)


def normalize_html_cv_result(data: dict) -> dict:
    """Sanitize AI JSON for the 2-page HTML CV builder."""
    if not isinstance(data, dict):
        data = {}
    boxes = []
    for item in data.get("skill_boxes") or []:
        if not isinstance(item, dict):
            continue
        heading = str(item.get("heading") or "").strip()
        content = str(item.get("content") or "").strip()
        if heading and content:
            boxes.append({"heading": heading, "content": content})
    highlights = []
    for item in data.get("profile_highlights") or []:
        text = str(item or "").strip()
        if text:
            highlights.append(text)
    return {
        "header_job_title": str(data.get("header_job_title") or "").strip(),
        "profile_intro": str(data.get("profile_intro") or "").strip(),
        "profile_highlights": highlights[:3],
        "skill_boxes": boxes[:3],
        "interests": str(data.get("interests") or "").strip(),
    }


def generate_tailored_html_cv(
    api_key: str,
    cv: str,
    job: dict,
    *,
    match: dict | None = None,
    profile: dict | None = None,
    base_slug: str = "graduate-trainee",
    output_language: str = "auto",
) -> dict:
    """AI content for a Support-Technician-style HTML CV tailored to one job."""
    description, about_us, title, company = job_text_fields(job)
    profile = profile or load_profile()
    match = match or {}
    output_language = (output_language or "auto").strip().lower()
    lang_hint = {
        "en": "Write ALL output in English.",
        "de": "Write ALL output in German (Deutsch).",
        "no": "Write ALL output in Norwegian Bokmal.",
    }.get(output_language, "Mirror the posting language (auto).")
    about_block = f"\n## Company About Us\n{about_us}\n" if about_us else ""
    system = (
        "You tailor a 2-page German job-market CV for ONE specific posting. "
        "Use ONLY facts from the candidate CV and profile — never invent employers, degrees, or skills. "
        "Emphasize BA International Development, pedagogical authorization, languages, teaching/counseling experience, and Frankfurt-based availability. "
        f"{lang_hint} "
        "header_job_title should match the posting title closely but stay honest (e.g. Junior Analyst not Senior). "
        "skill_boxes: exactly 3 groups tailored to this role; Languages box is added automatically — do not include languages. "
        f"{HTML_CV_SCHEMA}"
    )
    user = (
        f"Base CV template slug: {base_slug}\n\n"
        f"CV text:\n{cv}\n\n"
        f"Profile:\n{json.dumps(profile)}\n\n"
        f"Target job: {title} @ {company}\n"
        f"Location: {job.get('location')}\n\n"
        f"Match analysis (if any):\n{json.dumps(match)}\n\n"
        f"Job description:\n{description}\n{about_block}"
    )
    raw = mistral_json(api_key, system, user, model=MATERIALS_MODEL)
    return normalize_html_cv_result(raw)


def normalize_cover_letter_result(data: dict) -> dict:
    """Sanitize AI JSON for the HTML cover letter builder."""
    if not isinstance(data, dict):
        data = {}
    paragraphs = []
    for item in data.get("paragraphs") or []:
        text = str(item or "").strip()
        if text:
            paragraphs.append(text)
    return {
        "greeting": str(data.get("greeting") or "Dear Hiring Manager").strip(),
        "paragraphs": paragraphs[:4],
        "closing": str(data.get("closing") or "Kind regards,").strip(),
        "subject_line": str(data.get("subject_line") or "").strip(),
    }


def generate_tailored_cover_letter(
    api_key: str,
    cv: str,
    job: dict,
    *,
    match: dict | None = None,
    profile: dict | None = None,
    output_language: str = "auto",
) -> dict:
    """AI content for a one-page HTML cover letter tailored to one job."""
    description, about_us, title, company = job_text_fields(job)
    profile = profile or load_profile()
    match = match or {}
    output_language = (output_language or "auto").strip().lower()
    lang_hint = {
        "en": "Write ALL output in English.",
        "de": "Write ALL output in German (Deutsch).",
        "no": "Write ALL output in Norwegian Bokmal.",
    }.get(output_language, "Mirror the posting language: English posting -> English letter; German posting -> German letter.")
    about_block = f"\n## Company About Us\n{about_us}\n" if about_us else ""
    system = (
        "You write a concise, truthful cover letter for ONE German/EU job posting. "
        "Use ONLY facts from the candidate CV and profile — never invent employers, degrees, or skills. "
        "Emphasize BA degree, teacher authorization, multilingual skills, and base in Frankfurt am Main, Germany. "
        f"{lang_hint} "
        "Keep total length under 400 words across all paragraphs. "
        f"{COVER_LETTER_HTML_SCHEMA}"
    )
    user = (
        f"CV text:\n{cv}\n\n"
        f"Profile:\n{json.dumps(profile)}\n\n"
        f"Target job: {title} @ {company}\n"
        f"Location: {job.get('location')}\n\n"
        f"Match analysis (if any):\n{json.dumps(match)}\n\n"
        f"Job description:\n{description}\n{about_block}"
    )
    raw = mistral_json(api_key, system, user, model=MATERIALS_MODEL)
    return normalize_cover_letter_result(raw)


def refine_tailored_html_cv(
    api_key: str,
    cv: str,
    job: dict,
    *,
    match: dict | None = None,
    profile: dict | None = None,
    base_slug: str = "graduate-trainee",
    current_payload: dict | None = None,
    instruction: str = "",
    output_language: str = "auto",
) -> dict:
    """Revise tailored CV JSON using candidate feedback."""
    description, about_us, title, company = job_text_fields(job)
    profile = profile or load_profile()
    match = match or {}
    output_language = (output_language or "auto").strip().lower()
    lang_hint = {
        "en": "Keep ALL output in English.",
        "de": "Keep ALL output in German (Deutsch).",
        "no": "Keep ALL output in Norwegian Bokmal.",
    }.get(output_language, "Keep language matching the posting (auto).")
    about_block = f"\n## Company About Us\n{about_us}\n" if about_us else ""
    system = (
        "You revise a tailored CV JSON for ONE job posting based on the candidate's feedback. "
        "Use ONLY facts from the candidate CV and profile — never invent employers, degrees, or skills. "
        "Apply the requested changes while keeping the same JSON schema. "
        f"{lang_hint} "
        f"{HTML_CV_SCHEMA}"
    )
    current_block = (
        f"\nCurrent tailored CV JSON to edit:\n{json.dumps(current_payload)}\n"
        if current_payload
        else ""
    )
    user = (
        f"Candidate changes / notes (apply these):\n{instruction.strip()}\n\n"
        f"Base CV template slug: {base_slug}\n\n"
        f"CV text:\n{cv}\n\n"
        f"Profile:\n{json.dumps(profile)}\n\n"
        f"Target job: {title} @ {company}\n"
        f"Location: {job.get('location')}\n\n"
        f"Match analysis:\n{json.dumps(match)}\n\n"
        f"Job description:\n{description}\n{about_block}"
        f"{current_block}"
    )
    raw = mistral_json(api_key, system, user, model=MATERIALS_MODEL)
    return normalize_html_cv_result(raw)


def refine_tailored_cover_letter(
    api_key: str,
    cv: str,
    job: dict,
    *,
    match: dict | None = None,
    profile: dict | None = None,
    current_payload: dict | None = None,
    instruction: str = "",
    output_language: str = "auto",
) -> dict:
    """Revise tailored cover letter JSON using candidate feedback."""
    description, about_us, title, company = job_text_fields(job)
    profile = profile or load_profile()
    match = match or {}
    output_language = (output_language or "auto").strip().lower()
    lang_hint = {
        "en": "Keep ALL output in English.",
        "de": "Keep ALL output in German (Deutsch).",
        "no": "Keep ALL output in Norwegian Bokmal.",
    }.get(output_language, "Keep language matching the posting (auto).")
    about_block = f"\n## Company About Us\n{about_us}\n" if about_us else ""
    system = (
        "You revise a tailored cover letter JSON for ONE job posting based on the candidate's feedback. "
        "Use ONLY facts from the candidate CV — never invent experience. Keep the same JSON schema. "
        f"{lang_hint} "
        f"{COVER_LETTER_HTML_SCHEMA}"
    )
    current_block = (
        f"\nCurrent letter JSON to edit:\n{json.dumps(current_payload)}\n"
        if current_payload
        else ""
    )
    user = (
        f"Candidate changes / notes (apply these):\n{instruction.strip()}\n\n"
        f"CV text:\n{cv}\n\n"
        f"Profile:\n{json.dumps(profile)}\n\n"
        f"Target job: {title} @ {company}\n\n"
        f"Match analysis:\n{json.dumps(match)}\n\n"
        f"Job description:\n{description}\n{about_block}"
        f"{current_block}"
    )
    raw = mistral_json(api_key, system, user, model=MATERIALS_MODEL)
    return normalize_cover_letter_result(raw)


def _coerce_material_text(value: object) -> str:
    """Mistral sometimes returns resume/cover letter as nested dicts — files need str."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "content", "body", "resume", "cover_letter", "full_text"):
            if key in value and isinstance(value[key], str):
                return value[key]
        parts = []
        for k, v in value.items():
            if isinstance(v, str) and v.strip():
                parts.append(f"## {k}\n{v}")
        if parts:
            return "\n\n".join(parts)
        return json.dumps(value, indent=2, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(_coerce_material_text(v) for v in value if v)
    return str(value)


def normalize_materials_result(materials: dict) -> dict:
    """Ensure tailored_resume and cover_letter are strings for file output."""
    if not isinstance(materials, dict):
        return {"tailored_resume": "", "cover_letter": "", "key_angles": []}
    angles = materials.get("key_angles") or []
    if not isinstance(angles, list):
        angles = [angles]
    return {
        "tailored_resume": _coerce_material_text(materials.get("tailored_resume")),
        "cover_letter": _coerce_material_text(materials.get("cover_letter")),
        "key_angles": [str(a) for a in angles if a],
    }


def _normalize_pdf_text(text: str) -> str:
    safe = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return '<br/>'.join([line.strip() for line in safe.splitlines() if line.strip()])


def _write_text_pdf(content: str, output_path: Path, title: str) -> None:
    if not REPORTLAB_AVAILABLE:
        return
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        'Heading',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        spaceAfter=12,
    )
    body = ParagraphStyle(
        'Body',
        parent=styles['BodyText'],
        fontSize=11,
        leading=14,
    )
    doc = SimpleDocTemplate(str(output_path), pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [Paragraph(title, heading), Spacer(1, 12), Paragraph(_normalize_pdf_text(content), body)]
    doc.build(story)


def should_generate(match: dict, min_score: int) -> bool:
    if not is_qualified_to_apply(match) and match.get("recommendation") != "review":
        return False
    if match.get("dealbreakers"):
        return False
    if match.get("recommendation") == "skip":
        return False
    return int(match.get("match_score", 0)) >= min_score


def write_job_output(
    out_dir: Path,
    job: dict,
    title: str,
    company: str,
    match: dict,
    materials: dict | None,
) -> Path:
    folder = out_dir / slugify(company, title)
    folder.mkdir(parents=True, exist_ok=True)
    desc_text, _, _, _ = job_text_fields(job)
    meta = {
        "candidate_profile_id": CANDIDATE_PROFILE_ID,
        "candidate_name": CANDIDATE_NAME,
        "title": title,
        "company": company,
        "location": job.get("location"),
        "country": job.get("country"),
        "remote": job.get("workRemoteAllowed"),
        "workplace_types": job.get("workplaceTypes"),
        "seniority": job.get("seniorityLevel"),
        "apply_url": (
            job.get("applyUrl")
            or job.get("url")
            or job.get("link")
            or _extract_external_apply_url(desc_text)
            or ""
        ),
        "match": match,
        "description_preview": (job.get("descriptionText") or "")[:2000],
    }
    (folder / "match.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if desc_text:
        (folder / "job_description.txt").write_text(desc_text, encoding="utf-8")
    if materials:
        materials = normalize_materials_result(materials)
        tailored_resume = materials.get("tailored_resume", "")
        cover_letter = materials.get("cover_letter", "")
        (folder / "tailored_resume.txt").write_text(
            tailored_resume, encoding="utf-8"
        )
        (folder / "cover_letter.txt").write_text(
            cover_letter, encoding="utf-8"
        )
        if tailored_resume and REPORTLAB_AVAILABLE:
            try:
                _write_text_pdf(tailored_resume, folder / "tailored_resume.pdf", "Tailored Resume")
            except Exception:
                pass
        if cover_letter and REPORTLAB_AVAILABLE:
            try:
                _write_text_pdf(cover_letter, folder / "cover_letter.pdf", "Cover Letter")
            except Exception:
                pass
        angles = materials.get("key_angles") or []
        if angles:
            (folder / "positioning_notes.txt").write_text(
                "\n".join(f"- {a}" for a in angles), encoding="utf-8"
            )
    return folder


def build_summary_md(results: list[dict], out_dir: Path) -> str:
    lines = [
        "# Job match run",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Output: `{out_dir}`",
        "",
        "| Score | Action | Location | Company | Title |",
        "|------:|--------|----------|---------|-------|",
    ]
    for r in sorted(results, key=lambda x: -x["score"]):
        lines.append(
            f"| {r['score']} | {r['recommendation']} | {r.get('location', '')} | "
            f"{r['company']} | {r['title']} |"
        )
    lines.extend([
        "",
        "## Next steps",
        "1. Review **apply** and **review** in Streamlit: `streamlit run streamlit_app.py`",
        "2. Edit tailored files before submitting.",
        "3. Apply manually via apply_url in match.json.",
    ])
    return "\n".join(lines)


def list_output_runs() -> list[Path]:
    out = SCRIPT_DIR / "output"
    if not out.exists():
        return []
    runs = [p for p in out.iterdir() if p.is_dir()]
    return sorted(runs, key=lambda p: p.name, reverse=True)


def load_run_jobs(run_dir: Path) -> list[dict]:
    jobs = []
    for folder in run_dir.iterdir():
        match_file = folder / "match.json"
        if not match_file.exists():
            continue
        data = json.loads(match_file.read_text(encoding="utf-8"))
        data["folder"] = str(folder)
        data["folder_name"] = folder.name
        jobs.append(data)
    return sorted(jobs, key=lambda j: -int(j.get("match", {}).get("match_score", 0)))
