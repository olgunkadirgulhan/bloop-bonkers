"""Bir türün GÜNCEL ivmesi: son N günde yayınlanan Shorts'lar (izlenmeye göre) — trend mi, durgun mu?
QUERIES="a;b" DAYS=30 python tools/trend_check.py"""
import os, re, statistics, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import upload

yt = upload.client()
days = int(os.environ.get('DAYS', '30'))
since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
for q in os.environ['QUERIES'].split(';'):
    res = yt.search().list(part='snippet', q=q, type='video', videoDuration='short', order='viewCount',
                           publishedAfter=since, maxResults=50).execute().get('items', [])
    ids = [r['id']['videoId'] for r in res]
    vids = yt.videos().list(part='snippet,statistics', id=','.join(ids)).execute().get('items', []) if ids else []
    now = datetime.now(timezone.utc)
    rows = []
    for v in vids:
        age = max(1, (now - datetime.fromisoformat(v['snippet']['publishedAt'].replace('Z', '+00:00'))).days)
        views = int(v['statistics'].get('viewCount', 0))
        rows.append((views, views // age, age, v['snippet']['channelTitle'], v['snippet']['title']))
    rows.sort(reverse=True)
    vs = [r[0] for r in rows]
    print(f"\n=== '{q}' — son {days} gün, {len(rows)} Short | medyan {int(statistics.median(vs)) if vs else 0} izlenme | "
          f"1M+: {sum(v >= 1_000_000 for v in vs)} | 100K+: {sum(v >= 100_000 for v in vs)} | kanal sayısı {len({r[3] for r in rows})}")
    for v, pd, age, ch, t in rows[:8]:
        print(f"  {v:>11,} izl | {pd:>9,}/gün | {age:>2} gün | {ch[:22]:22} | {t[:70]}")
