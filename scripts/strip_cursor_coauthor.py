"""Remove Cursor co-author trailers from git commit messages (stdin/stdout filter)."""
import sys

lines = sys.stdin.readlines()
cleaned = [line for line in lines if 'Co-authored-by: Cursor' not in line]
while cleaned and not cleaned[-1].strip():
    cleaned.pop()
sys.stdout.write(''.join(cleaned))
if cleaned:
    sys.stdout.write('\n')
