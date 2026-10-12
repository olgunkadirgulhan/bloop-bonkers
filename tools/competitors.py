"""Rakip analizi: aynı formattaki popüler Shorts kanalları vs bizim kanallar (YouTube Data API, ~600 birim).
Çıktı: competitors.json + log'da özet tablo."""
import json, os, re, statistics, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import upload

QUERIES = {
    'bloop': ['normal vs psycho animation', 'level 1 vs level 100 animation shorts', 'expectation vs reality animation shorts'],
    'paw': ['cat vs dog animation shorts', 'cats vs dogs funny animation'],
}
OURS = {'bloop': 'UCdbAUr-IDGWaKXhXGnX55MQ', 'paw': 'UCA3-UkMqfJkuqm10Z587zwA'}
yt = upload.client()
since = (datetime.now(timezone.utc) - timedelta(days=120)).strftime('%Y-%m-%dT%H:%M:%SZ')


def dur(iso):
    m = re.match(r'PT(?:(\d+)M)?(?:(\d+)S)?', iso or '')
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0) if m else 0


def channel_report(cid):
    ch = yt.channels().list(part='snippet,statistics,contentDetails', id=cid).execute()['items'][0]
    up = ch['contentDetails']['relatedPlaylists']['uploads']
    items = yt.playlistItems().list(part='contentDetails', playlistId=up, maxResults=30).execute().get('items', [])
    ids = [i['contentDetails']['videoId'] for i in items]
    vids = yt.videos().list(part='snippet,statistics,contentDetails', id=','.join(ids)).execute().get('items', []) if ids else []
    views = [int(v['statistics'].get('viewCount', 0)) for v in vids]
    likes = [int(v['statistics'].get('likeCount', 0)) for v in vids]
    coms = [int(v['statistics'].get('commentCount', 0)) for v in vids]
    durs = [dur(v['contentDetails']['duration']) for v in vids]
    dates = sorted(datetime.fromisoformat(v['snippet']['publishedAt'].replace('Z', '+00:00')) for v in vids)
    span = max(1.0, (dates[-1] - dates[0]).total_seconds() / 86400) if len(dates) > 1 else 1.0
    top = sorted(vids, key=lambda v: -int(v['statistics'].get('viewCount', 0)))[:3]
    return dict(id=cid, title=ch['snippet']['title'], subs=int(ch['statistics'].get('subscriberCount', 0)),
                videos=int(ch['statistics'].get('videoCount', 0)), total_views=int(ch['statistics'].get('viewCount', 0)),
                created=ch['snippet']['publishedAt'][:10],
                median_views=int(statistics.median(views)) if views else 0, mean_dur=round(statistics.mean(durs), 1) if durs else 0,
                per_day=round(len(vids) / span, 2), like_rate=round(100 * sum(likes) / max(1, sum(views)), 2),
                comment_rate=round(1000 * sum(coms) / max(1, sum(views)), 2),
                top=[(v['snippet']['title'], int(v['statistics'].get('viewCount', 0)), dur(v['contentDetails']['duration'])) for v in top])


out = {}
for group, qs in QUERIES.items():
    found = {}
    for q in qs:
        res = yt.search().list(part='snippet', q=q, type='video', videoDuration='short', order='viewCount',
                               publishedAfter=since, maxResults=25).execute().get('items', [])
        for r in res:
            found[r['snippet']['channelId']] = found.get(r['snippet']['channelId'], 0) + 1
    cids = [c for c, _ in sorted(found.items(), key=lambda x: -x[1])][:8]
    reps = []
    for c in cids + [OURS[group]]:
        try: reps.append(dict(channel_report(c), ours=(c == OURS[group])))
        except Exception as e: print('skip', c, str(e)[:100])
    out[group] = reps
    print(f'\n=== {group} ===')
    print(f"{'channel':28} {'subs':>9} {'videos':>6} {'med.views':>9} {'dur s':>5} {'/day':>5} {'like%':>5} {'com/1k':>6}")
    for r in sorted(reps, key=lambda r: -r['median_views']):
        print(f"{('* ' if r['ours'] else '') + r['title'][:26]:28} {r['subs']:>9} {r['videos']:>6} {r['median_views']:>9} "
              f"{r['mean_dur']:>5} {r['per_day']:>5} {r['like_rate']:>5} {r['comment_rate']:>6}")
        for t, v, d in r['top'][:2]:
            print(f"      top: {v:>9} views {d:>3}s  {t[:80]}")
json.dump(out, open('competitors.json', 'w'), indent=1, ensure_ascii=False)
