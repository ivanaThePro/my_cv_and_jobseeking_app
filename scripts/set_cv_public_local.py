"""Ensure local .env disables CV password (pre-deploy). Does not print secrets."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env_path = ROOT / '.env'
example = ROOT / '.env.example'

if not env_path.is_file():
    env_path.write_text(example.read_text(encoding='utf-8'), encoding='utf-8')

text = env_path.read_text(encoding='utf-8')

def set_var(name: str, value: str) -> None:
    global text
    pattern = rf'^{re.escape(name)}=.*$'
    line = f'{name}={value}'
    if re.search(pattern, text, flags=re.MULTILINE):
        text = re.sub(pattern, line, text, count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip() + f'\n{line}\n'

set_var('ENABLE_CV_PASSWORD', 'false')
set_var('CV_ACCESS_REQUIRED', 'false')
set_var('CV_ACCESS_PUBLIC', 'true')
set_var('CV_ACCESS_PASSWORD', '')
env_path.write_text(text, encoding='utf-8')
print('Local CV password disabled (ENABLE_CV_PASSWORD=false).')
