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
    'boss': ['Boss Watching vs Boss NOT Watching 😂 {g}', 'When the Boss Isn\'t Watching... ({g}) 💀', 'Boss Watching vs Not Watching: {g} 👀'],
    'public': ['In Public vs At Home 😂 {g}', 'Me in Public vs Me at Home ({g}) 🤪', 'In Public vs At Home: {g} 💀'],
    'clock': ['Me at 8 AM vs Me at 3 AM 😂 {g}', '8 AM Me vs 3 AM Me ({g}) 💀', 'Me at 8 AM vs 3 AM: {g} 🌙'],
}
TAGS = {'psycho': 'normalvspsycho', 'level': 'level1vslevel100', 'expect': 'expectationvsreality',
        'boss': 'bosswatching', 'public': 'inpublicvsathome', 'clock': '3am'}


def load():
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else {'videos': []}


# Kanal verisi yokken başlangıç ağırlıkları: 'psycho' ilk gün viral oldu (31 bin izlenme)
PRIOR = {'psycho': 9.0}   # 2026-10-10: psycho 18K-100K, diğer formatlar 1.7-5K izlenme


def performance(hist):
    """Kendi videolarımızın izlenmeleri (en az 20 saatlik olanlar) → format ve gag başına ortalama.
    YouTube'a erişilemezse boş döner; seçim o zaman PRIOR ile yapılır."""
    try:
        import upload
        if not upload.configured():
            return {}, {}
        now = datetime.now(timezone.utc)
        old = [v for v in hist['videos'][-40:] if v.get('kind', 'short') == 'short' and v.get('format')
               and (now - datetime.strptime(v['date'], '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)).total_seconds() > 20 * 3600]
        if not old:
            return {}, {}
        items = upload.client().videos().list(part='statistics', id=','.join(v['id'] for v in old)).execute()['items']
        views = {i['id']: int(i['statistics'].get('viewCount', 0)) for i in items}
    except Exception as e:
        print('performans okunamadı:', str(e)[:150]); return {}, {}
    fmt, gag = {}, {}
    for v in old:
        if v['id'] in views:
            fmt.setdefault(v['format'], []).append(views[v['id']])
            for g in v['gags']:
                gag.setdefault(g, []).append(views[v['id']])
    avg = lambda d: {k: sum(x) / len(x) for k, x in d.items()}
    return avg(fmt), avg(gag)


def weights(keys, perf, prior=None):
    """Keşif + sömürü: denenmemiş/az izlenen seçenek de şans bulur (taban 1), iyi gidenin ağırlığı en fazla 6."""
    prior = prior or {}
    top = max(perf.values(), default=0)
    return [max(prior.get(k, 1.0), 1.0 + 5.0 * perf[k] / top) if top and k in perf else prior.get(k, 1.0) for k in keys]


def pick_plan(hist, rnd, perf=({}, {})):
    fperf, gperf = perf
    past = [v for v in hist['videos'] if v.get('kind', 'short') == 'short' and v.get('format')][-12:]  # derlemeler hariç
    last2 = [v['format'] for v in past[-2:]]
    fmts = [f for f in bloop.FORMATS if not (len(last2) == 2 and last2[0] == last2[1] == f)]   # 3. kez üst üste yok
    fmt = rnd.choices(fmts, weights=weights(fmts, fperf, PRIOR))[0]
    last_cast = past[-1]['cast'] if past else None
    casts = [c for c in bloop.CAST if c != last_cast]
    cast = rnd.choices(casts, weights=[3 if c == 'bloop' else 2 for c in casts])[0]
    month = datetime.now(timezone.utc).month
    pool = [k for k, g in bloop.GAGS.items() if month in g.get('months', range(1, 13))]
    gw = dict(zip(pool, weights(pool, gperf)))
    # tekrar cezası: son 6 videoda her kullanım ağırlığı 4'te birine indirir, son videodakiler hiç seçilmez;
    # hiç kullanılmamış gag 2 kat öne çıkar (viral gag'ler her videoya girip içeriği tekrarlamasın)
    recent = [g for v in past[-6:] for g in v.get('gags', [])]
    used_ever = {g for v in hist['videos'] for g in v.get('gags', [])}
    last_gags = set(past[-1]['gags']) if past else set()
    for k in pool:
        gw[k] *= 0.25 ** recent.count(k) * (2.0 if k not in used_ever else 1.0)
        if k in last_gags and len(pool) - len(last_gags) >= 4:
            gw[k] = 0.0
    gw = {k: (w if w > 0 else 1e-9) for k, w in gw.items()}
    seen_sets = {tuple(sorted(v['gags'])) for v in past}
    last_first = past[-1]['gags'][0] if past else None
    for _ in range(200):
        n, left, gags = (4 if rnd.random() < 0.7 else 3), list(pool), []
        while len(gags) < n:                         # ağırlıklı, tekrarsız seçim
            g = rnd.choices(left, weights=[gw[k] for k in left])[0]
            gags.append(g); left.remove(g)
        if 'pumpkin' in pool and 'pumpkin' not in gags and 'pumpkin' not in last_gags and rnd.random() < 0.25:
            gags[-1] = 'pumpkin'
        if tuple(sorted(gags)) not in seen_sets and gags[0] != last_first:
            break
    last_room = past[-1].get('room') if past else None
    room = rnd.choice([r for r in bloop.ROOMS if r != last_room])
    return dict(format=fmt, cast=cast, gags=gags, room=room, seed=rnd.randrange(10 ** 6))


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
    perf = performance(hist)
    if perf[0]:
        print('format ortalama izlenme:', {k: round(v) for k, v in perf[0].items()}, flush=True)
    plan = pick_plan(hist, rnd, perf)
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
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if sum(v['date'].startswith(today) and v.get('kind', 'short') == 'short' for v in hist['videos']) == 1:
        social(mp4, title, f'https://youtube.com/shorts/{vid}', plan)


def social(mp4, title, url, plan):
    """Günün ilk videosu → social/ (artifact 'social-<run>'): fenek-shorts telegram-relay bunu TikTok/Instagram
    açıklamalarıyla Fenek botundan gönderir."""
    import shutil
    A, B, _ = bloop.FORMATS[plan['format']]
    tag = TAGS[plan['format']]
    tiktok = f"{title}\nWhich one are YOU? 1 or 2? 👇\n\n#{tag} #animation #funny #relatable #cartoon #fyp"
    insta = (f"{title}\n\nWhich one are you, {A.lower()} or {B.lower()}? Comment 1 or 2 👇\n"
             f"Follow for daily Bloop Bonkers chaos 🟣\n\n#{tag} #animation #funny #cartoon #comedy")  # Instagram: en fazla 5
    soc = HERE / 'social'
    soc.mkdir(exist_ok=True)
    shutil.copy(mp4, soc / 'video.mp4')
    (soc / 'post.json').write_text(json.dumps({'channel': 'Bloop Bonkers', 'title': title, 'url': url, 'tiktok': tiktok,
                                               'instagram': insta}, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
