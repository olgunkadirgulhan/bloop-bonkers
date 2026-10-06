"""Decides whether a scheduled run should make a video.

GitHub fires cron runs hours late or drops them, so the workflow is triggered
hourly and this guard produces only when a slot is due: more slots have passed
today (UTC) than videos were uploaded today. A missed slot is made up by the next
hourly run instead of being lost. The upload log is read from the latest remote
branch, not from the (possibly stale) checkout of a delayed run.

env:
  LOG_FILE     published.csv (date_utc, format) or history.json (videos[].date, .kind)
  SLOTS        short slots, UTC "HH:MM,HH:MM"
  PER_SLOT     videos one run makes (default 1)
  SHORT_KINDS  log kinds that count as shorts (default "short")
  SHORT_MODE   mode printed for a short run (default "short")
  LONG         optional weekly long videos, "tue 17:00 long,fri 15:00 school"
  MIN_GAP_MIN  skip if the last upload is more recent than this (default 45)
  BRANCH       default "main"
"""
import csv
import io
import json
import os
import subprocess
from datetime import datetime, timezone

DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


def output(go, mode=''):
    print(f'-> {"produce " + mode if go else "skip"}')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write(f'go={1 if go else 0}\nmode={mode}\n')


def uploads():
    """[(date 'YYYY-MM-DD HH:MM', kind)] for every logged upload."""
    path, branch = os.environ['LOG_FILE'], os.environ.get('BRANCH', 'main')
    subprocess.run(['git', 'fetch', '-q', '--depth', '1', 'origin', branch], check=False)
    r = subprocess.run(['git', 'show', f'origin/{branch}:{path}'], capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0 or not r.stdout.strip():
        return []
    if path.endswith('.json'):
        return [(v['date'], v.get('kind', 'short')) for v in json.loads(r.stdout).get('videos', [])]
    return [(row['date_utc'], row.get('format') or 'short') for row in csv.DictReader(io.StringIO(r.stdout))]


def main():
    now = datetime.now(timezone.utc)
    today, hhmm, weekday = now.strftime('%Y-%m-%d'), now.strftime('%H:%M'), DAYS[now.weekday()]
    log = uploads()
    done = [(d, k) for d, k in log if d.startswith(today)]

    if log:
        last = datetime.strptime(max(d for d, _ in log), '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        gap = (now - last).total_seconds() / 60
        if gap < int(os.environ.get('MIN_GAP_MIN') or 45):
            print(f'last upload {gap:.0f} min ago')
            return output(False)

    for item in filter(None, (s.strip() for s in os.environ.get('LONG', '').split(','))):
        day, at, mode = item.split()
        if day == weekday and hhmm >= at and not any(k == mode for _, k in done):
            print(f'long "{mode}" due since {at}, not uploaded today')
            return output(True, mode)

    kinds = set(os.environ.get('SHORT_KINDS', 'short').split(','))
    slots = [s.strip() for s in os.environ['SLOTS'].split(',') if s.strip()]
    due = int(os.environ.get('PER_SLOT') or 1) * sum(1 for s in slots if s <= hhmm)
    made = sum(1 for _, k in done if k in kinds)
    print(f'{hhmm} UTC: shorts due {due}, uploaded today {made}')
    output(made < due, os.environ.get('SHORT_MODE', 'short'))


if __name__ == '__main__':
    main()
