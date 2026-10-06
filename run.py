"""Bir Short üret ve yükle: plan seç (format/karakter/gag tekrar etmez) -> render -> YouTube -> history.json.

  python run.py --no-upload        # sadece output/<id>/video.mp4
"""
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bloop  # noqa: E402

HISTORY = HERE / 'history.json'
PLAYLISTS = HERE / 'playlists.json'

TITLES = {
    'psycho': ['Normal vs Psychopath 😂 {g}', 'NORMAL vs PSYCHO: {g} Edition 🤪', 'Normal People vs Psychopaths ({g}) 💀',
               '{c}: Normal vs Psycho ({g}) 😂'],
    'level': ['Level 1 vs Level 100: {g} 🔥', '{g}: Level 1 vs Level 100 😂', 'Level 1 vs Level 100 ({g}) 💀'],
    'expect': ['Expectation vs Reality: {g} 😭', '{g}: Expectation vs Reality 💀', 'Expectation vs Reality ({g}) 😂'],
    'mom': ['Mom Watching vs Mom NOT Watching 😂 {g}', 'When Mom Isn\'t Watching... ({g}) 💀', 'Mom Watching vs Not Watching: {g} 👀'],
    'public': ['In Public vs At Home 😂 {g}', 'Me in Public vs Me at Home ({g}) 🤪', 'In Public vs At Home: {g} 💀'],
    'clock': ['Me at 8 AM vs Me at 3 AM 😂 {g}', '8 AM Me vs 3 AM Me ({g}) 💀', 'Me at 8 AM vs 3 AM: {g} 🌙'],
}
TAGS = {'psycho': 'normalvspsycho', 'level': 'level1vslevel100', 'expect': 'expectationvsreality',
        'mom': 'momwatching', 'public': 'inpublicvsathome', 'clock': '3am'}


def load():
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else {'videos': []}


def pick_plan(hist, rnd):
    past = hist['videos'][-12:]
    last_fmt = [v['format'] for v in past[-2:]]
    fmt = rnd.choice([f for f in bloop.FORMATS if f not in last_fmt])
    last_cast = past[-1]['cast'] if past else None
    casts = [c for c in bloop.CAST if c != last_cast]
    cast = rnd.choices(casts, weights=[3 if c == 'bloop' else 2 for c in casts])[0]
    month = datetime.now(timezone.utc).month
    pool = [k for k, g in bloop.GAGS.items() if month in g.get('months', range(1, 13))]
    seen_sets = {tuple(sorted(v['gags'])) for v in past}
    last_first = past[-1]['gags'][0] if past else None
    for _ in range(200):
        gags = rnd.sample(pool, 4 if rnd.random() < 0.7 else 3)
        if 'pumpkin' in pool and 'pumpkin' not in gags and rnd.random() < 0.5:
            gags[-1] = 'pumpkin'
        if tuple(sorted(gags)) not in seen_sets and gags[0] != last_first:
            break
    return dict(format=fmt, cast=cast, gags=gags, seed=rnd.randrange(10 ** 6))


def metadata(plan, hist, rnd):
    names = [bloop.GAGS[k]['name'] for k in plan['gags']]
    g = f'{names[0]} & {names[1]}'
    c = bloop.CAST[plan['cast']]['name']
    used = {v['title'] for v in hist['videos']}
    opts = [t.format(g=g, c=c) for t in TITLES[plan['format']]]
    rnd.shuffle(opts)
    title = next((t for t in opts if t not in used), opts[0] + f' #{len(hist["videos"]) + 1}')
    A, B, _ = bloop.FORMATS[plan['format']]
    desc = (f'Which one are YOU? Comment 1 or 2! 👇\n\n'
            f'{c} tries {", ".join(n.lower() for n in names[:-1])} and {names[-1].lower()}: '
            f'{A.lower()} vs {B.lower()}.\n\n'
            f'New Bloop Bonkers Shorts every day. Subscribe for more chaos! 🟣\n\n'
            f'#shorts #animation #funny #cartoon #{TAGS[plan["format"]]} #bloopbonkers')
    tags = ['bloop bonkers', f'{A.lower()} vs {B.lower()}', 'funny animation', '3d animation', 'cartoon',
            'funny shorts', 'relatable', c.lower()] + [n.lower() for n in names]
    return title, desc, tags


def main():
    no_upload = '--no-upload' in sys.argv
    hist = load(); rnd = random.Random()
    plan = pick_plan(hist, rnd)
    title, desc, tags = metadata(plan, hist, rnd)
    vid_key = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    print(f'plan: {plan}\ntitle: {title}', flush=True)
    out = HERE / 'output' / vid_key
    mp4 = bloop.render_video(plan, str(out))
    (out / 'meta.json').write_text(json.dumps(dict(plan=plan, title=title, description=desc, tags=tags), indent=2))
    if no_upload:
        print('render ok (yükleme yok):', mp4); return
    import upload
    if not upload.configured():
        sys.exit('YouTube secrets yok')
    print('kanal:', upload.check_channel())
    privacy = os.environ.get('YT_PRIVACY') or 'private'
    vid = upload.upload(mp4, title, desc, tags, privacy, category='23')
    print(f'yüklendi: https://youtube.com/shorts/{vid} ({privacy})')
    pl = json.loads(PLAYLISTS.read_text()) if PLAYLISTS.exists() else {}
    if plan['format'] in pl:
        try: upload.add_to_playlist(pl[plan['format']], vid)
        except Exception as e: print('playlist:', e)
    hist['videos'].append(dict(id=vid, date=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'), kind='short',
                               title=title, privacy=privacy, **plan))
    HISTORY.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
