import json
import re
from pathlib import Path
from collections import Counter

jobs = json.load(open(Path("jobsearch/data/jobs_cache.json"), encoding="utf-8"))
print("total", len(jobs))

no_url = 0
portal = 0
nursing = 0
samples_portal = []
samples_nurse = []
samples_no = []

PORTAL = re.compile(
    r"(indeed\.com($|/\?)|indeed\.com/jobs\?|stepstone\.de($|/\?)|"
    r"linkedin\.com/jobs|arbeitsagentur\.de/jobsuche/\?|xing\.com/jobs|"
    r"/search\?|/stellenangebote\?|jooble\.org/jobs)",
    re.I,
)
NURSE = re.compile(r"\b(pflege|nurs|kranken|medizin|physio|arzt|mfa|helfer/in)\b", re.I)

for j in jobs:
    title = (j.get("title") or j.get("positionName") or "")[:60]
    url = (j.get("applyUrl") or j.get("link") or j.get("url") or "").strip()
    blob = f"{title} {j.get('descriptionText') or j.get('description') or ''}"[:500]
    if not url or len(url) < 12:
        no_url += 1
        if len(samples_no) < 5:
            samples_no.append((title, url or "(empty)"))
    if PORTAL.search(url):
        portal += 1
        if len(samples_portal) < 8:
            samples_portal.append((title, url[:90]))
    if NURSE.search(blob) or NURSE.search(title):
        nursing += 1
        if len(samples_nurse) < 8:
            samples_nurse.append((title, url[:90] if url else "(no url)"))

print("no/bad url", no_url)
print("portal urls", portal)
print("nursing-ish", nursing)
print("\nportal samples:")
for t, u in samples_portal:
    print(" ", t, "|", u)
print("\nnurse samples:")
for t, u in samples_nurse:
    print(" ", t, "|", u)
print("\nno url samples:")
for t, u in samples_no:
    print(" ", t, "|", u)

sources = Counter(j.get("source") or "?" for j in jobs)
print("\nsources:", sources.most_common(12))
