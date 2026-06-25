"""Enable CV/site password in local .env (does not print the password)."""
from __future__ import annotations

import re
import secrets
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env_path = ROOT / '.env'
example = ROOT / '.env.example'

if not env_path.is_file():
    env_path.write_text(example.read_text(encoding='utf-8'), encoding='utf-8')

text = env_path.read_text(encoding='utf-8')


def get_var(name: str) -> str:
    match = re.search(rf'^{re.escape(name)}=(.*)$', text, flags=re.MULTILINE)
    return (match.group(1).strip() if match else '')


def set_var(name: str, value: str) -> None:
    global text
    pattern = rf'^{re.escape(name)}=.*$'
    line = f'{name}={value}'
    if re.search(pattern, text, flags=re.MULTILINE):
        text = re.sub(pattern, line, text, count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip() + f'\n{line}\n'


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


set_var('ENABLE_CV_PASSWORD', 'true')
set_var('CV_ACCESS_PUBLIC', 'false')
set_var('CV_ACCESS_REQUIRED', 'true')

current = get_var('CV_ACCESS_PASSWORD')
if not current or current == 'your-password-here':
    set_var('CV_ACCESS_PASSWORD', _random_password())

env_path.write_text(text, encoding='utf-8')
print('Local site password enabled (ENABLE_CV_PASSWORD=true).')
print('If you need the password, open .env and read CV_ACCESS_PASSWORD (not printed here).')
