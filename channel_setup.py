"""Kanal kurulumu (GitHub Actions 'channel' workflow'u, secrets'taki token ile):
açıklama, anahtar kelimeler, banner, filigran, çocuklara yönelik değil, format oynatma listeleri.
--delete-old: bu otomasyonun yüklemediği eski videoları siler (history.json'da olmayanlar).

Profil fotoğrafı, kanal adı ve @handle API ile değiştirilemez: YouTube Studio > Özelleştirme.
"""
import json
import os
import sys
from pathlib import Path

from googleapiclient.http import MediaFileUpload

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import upload  # noqa: E402
from bloop import FORMATS  # noqa: E402

BRAND = HERE / 'branding'
PLAYLISTS_FILE = HERE / 'playlists.json'
HISTORY = HERE / 'history.json'

DESCRIPTION = """Normal vs Psycho, Level 1 vs Level 100, Expectation vs Reality — and way more chaos. 🟣

Meet Bloop and friends: tiny 3D cartoon blobs living through the everyday stuff we ALL do… just very, very differently.

🟣 Bloop: the original chaos blob
🟡 Zip: zero patience, maximum speed
🟢 Grumbo: grumpy, unibrow, secretly soft
🩷 Mimi: drama queen with a bow

🎬 New Shorts every day
💬 Tell us in the comments: which one are YOU?

Original characters & animation by Bloop Bonkers."""

KEYWORDS = ('"Bloop Bonkers" "normal vs psycho" "normal vs psychopath" "level 1 vs level 100" '
            '"expectation vs reality" "funny animation" "3d animation" "cartoon shorts" "funny shorts" '
            '"relatable" "animation memes"')

PLAYLISTS = {
    'psycho': ('Normal vs Psycho 🤪', 'The normal way... and the PSYCHO way.'),
    'level': ('Level 1 vs Level 100 🔥', 'Same task, very different levels.'),
    'expect': ('Expectation vs Reality 😭', 'How it should go vs how it actually goes.'),
    'mom': ('Mom Watching vs Not Watching 👀', 'Be honest, we all did this.'),
    'public': ('In Public vs At Home 🏠', 'Two completely different people.'),
    'clock': ('8 AM Me vs 3 AM Me 🌙', 'Morning you and 3 AM you are not the same.'),
}


def step(name, fn):
    try:
        fn(); print(f'✓ {name}', flush=True)
    except Exception as e:
        print(f'✗ {name}: {str(e)[:300]}', flush=True)


def delete_old(yt, cid):
    ours = {v['id'] for v in json.loads(HISTORY.read_text()).get('videos', [])} if HISTORY.exists() else set()
    uploads = yt.channels().list(part='contentDetails', id=cid).execute()['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    vids, tok = [], None
    while True:
        r = yt.playlistItems().list(part='snippet', playlistId=uploads, maxResults=50, pageToken=tok).execute()
        vids += [(i['snippet']['resourceId']['videoId'], i['snippet']['title']) for i in r.get('items', [])]
        tok = r.get('nextPageToken')
        if not tok: break
    old = [(v, t) for v, t in vids if v not in ours]
    print(f'{len(vids)} video, {len(old)} eski video silinecek')
    for vid, t in old:
        step(f'silindi: {t[:70]}', lambda: yt.videos().delete(id=vid).execute())


def publish_all(yt):
    """history.json'daki gizli videoları herkese açık yapar."""
    hist = json.loads(HISTORY.read_text()) if HISTORY.exists() else {'videos': []}
    only = set(os.environ.get('PUBLISH_IDS', '').split()) # boş değilse yalnız bu videolar (gizli derleme açılmasın)
    for v in hist['videos']:
        if v.get('privacy') == 'public' or (only and v['id'] not in only) or (not only and v.get('kind') in ('compilation', 'episode')):
            continue
        cur = yt.videos().list(part='status', id=v['id']).execute().get('items', [])
        if not cur:
            continue
        st = cur[0]['status']; st['privacyStatus'] = 'public'
        yt.videos().update(part='status', body={'id': v['id'], 'status': st}).execute()
        v['privacy'] = 'public'; print(f"✓ yayında: {v['title']} (https://youtu.be/{v['id']})")
    HISTORY.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + '\n')


def main():
    yt = upload.client()
    if '--publish-only' in sys.argv:
        publish_all(yt); return
    ch = yt.channels().list(part='id,snippet,brandingSettings', mine=True).execute()['items'][0]
    cid, title = ch['id'], ch['snippet']['title']
    print(f'kanal: {title} ({cid})')
    if '--delete-old' in sys.argv:
        delete_old(yt, cid)

    def branding():
        banner = yt.channelBanners().insert(
            media_body=MediaFileUpload(str(BRAND / 'banner.png'), mimetype='image/png')).execute()
        channel = dict(ch.get('brandingSettings', {}).get('channel', {}))
        channel.update(title=title, description=DESCRIPTION, keywords=KEYWORDS, defaultLanguage='en')
        yt.channels().update(part='brandingSettings', body={'id': cid, 'brandingSettings': {
            'channel': channel, 'image': {'bannerExternalUrl': banner['url']}}}).execute()
    step('açıklama, anahtar kelimeler, banner', branding)
    step('kanal: çocuklara yönelik değil', lambda: yt.channels().update(part='status', body={
        'id': cid, 'status': {'selfDeclaredMadeForKids': False}}).execute())

    def watermark():
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.credentials import Credentials
        creds = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'], client_id=os.environ['YT_CLIENT_ID'],
                            client_secret=os.environ['YT_CLIENT_SECRET'], token_uri='https://oauth2.googleapis.com/token')
        b = 'bloopBoundary'
        meta = json.dumps({'timing': {'type': 'offsetFromStart', 'offsetMs': 0},
                           'position': {'type': 'corner', 'cornerPosition': 'topRight'}})
        data = (f'--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n--{b}\r\n'
                'Content-Type: image/png\r\n\r\n').encode() + (BRAND / 'watermark.png').read_bytes() + f'\r\n--{b}--\r\n'.encode()
        r = AuthorizedSession(creds).post(
            f'https://www.googleapis.com/upload/youtube/v3/watermarks/set?channelId={cid}&uploadType=multipart',
            data=data, headers={'Content-Type': f'multipart/related; boundary={b}'})
        if r.status_code >= 300:
            raise RuntimeError(f'{r.status_code} {r.text[:200]}')
    step('filigran (abone ol)', watermark)

    existing = {p['snippet']['title']: p['id'] for p in
                yt.playlists().list(part='snippet', mine=True, maxResults=50).execute().get('items', [])}
    ids = json.loads(PLAYLISTS_FILE.read_text()) if PLAYLISTS_FILE.exists() else {}
    for key, (ptitle, pdesc) in PLAYLISTS.items():
        if key in ids: continue
        if ptitle in existing:
            ids[key] = existing[ptitle]; continue
        p = yt.playlists().insert(part='snippet,status', body={
            'snippet': {'title': ptitle, 'description': pdesc + '\n\nNew Bloop Bonkers Shorts every day. #BloopBonkers',
                        'defaultLanguage': 'en'}, 'status': {'privacyStatus': 'public'}}).execute()
        ids[key] = p['id']; print(f'✓ oynatma listesi: {ptitle}')
    PLAYLISTS_FILE.write_text(json.dumps(ids, indent=2) + '\n')
    print('\nElle yapılacak: branding/profile.png -> YouTube Studio > Özelleştirme > Marka > Resim')


if __name__ == '__main__':
    main()
