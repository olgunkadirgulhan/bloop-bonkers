"""YouTube Analytics (sadece okuma): video başına izlenme süresi ve izleyicinin videoda kaldığı oran.
    python tools/analytics.py [VIDEO_ID ...]      # boşsa: tüm bölümler + son 8 Short
Gecikme: Analytics verisi 1-2 gün geriden gelir."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from googleapiclient.discovery import build  # noqa: E402


def mmss(s):
    s = int(round(s)); return f'{s // 60}:{s % 60:02d}'


def main():
    hist = json.loads((Path(__file__).resolve().parent.parent / 'history.json').read_text())
    vids = {v['id']: v for v in hist['videos'] if v.get('privacy') == 'public'}
    ids = sys.argv[1:] or ([k for k, v in vids.items() if v.get('kind') == 'episode']
                           + [k for k, v in vids.items() if v.get('kind', 'short') == 'short'][-8:])
    import os
    from google.oauth2.credentials import Credentials
    creds = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'], client_id=os.environ['YT_CLIENT_ID'],
                        client_secret=os.environ['YT_CLIENT_SECRET'], token_uri='https://oauth2.googleapis.com/token')
    ya = build('youtubeAnalytics', 'v2', credentials=creds, cache_discovery=False)
    end = date.today().isoformat(); start = (date.today() - timedelta(days=90)).isoformat()
    print(f'{"video":<12} {"izlenme":>8} {"ort. süre":>9} {"izlenen %":>9}  saat   başlık')
    for vid in ids:
        r = ya.reports().query(ids='channel==MINE', startDate=start, endDate=end, filters=f'video=={vid}',
                               metrics='views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage').execute()
        row = (r.get('rows') or [[0, 0, 0, 0]])[0]
        v = vids.get(vid, {})
        print(f'{vid:<12} {int(row[0]):>8} {mmss(row[2]):>9} {row[3]:>8.0f}% {row[1] / 60:>6.1f}  {v.get("title", "")[:50]}')
        if v.get('kind') == 'episode':
            rr = ya.reports().query(ids='channel==MINE', startDate=start, endDate=end, filters=f'video=={vid}',
                                    dimensions='elapsedVideoTimeRatio', metrics='audienceWatchRatio').execute()
            pts = rr.get('rows') or []
            if pts:
                print('   elde tutma: ' + '  '.join(f'%{int(p[0] * 100)}→{p[1] * 100:.0f}' for p in pts[::10]))


if __name__ == '__main__':
    main()
