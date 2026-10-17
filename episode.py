"""Uzun bölüm (yatay 16:9, TV/masaüstü): kütüphanedeki HER gag tam bir kez, karakterler sırayla.
Derlemenin aksine hiçbir sahne tekrar etmez; Shorts'tan kesilmez, her durum bu bölüm için yeniden render edilir
(yeni seed, yeni karakter). Yatay video Shorts sayılmaz → izlenme süresi YPP'nin 4.000 saatine yazılır.

  python episode.py [--no-upload]
"""
import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bloop  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

HISTORY = HERE / 'history.json'
OW, OH = 1920, 1080
BG = (24, 20, 38)
FF = None
CARD = 2.4


def ff(*args):
    subprocess.run([FF, '-y', '-loglevel', 'error', *args], check=True)


def strip(t):
    return re.sub('[\U0001F000-\U0001FFFF☀-➿‍️]', '', t).strip()


def card_png(path, lines):
    """lines: [(metin, y, boyut, renk)] → 1920x1080 kart."""
    img = Image.new('RGB', (OW, OH), BG)
    for txt, y, sz, col in lines:
        bloop.put_text_px(img, strip(txt), OW // 2, y, sz, col, max_w=1760)
    img.save(path)


def card_mp4(path, lines, seconds=CARD):
    png = str(path) + '.png'
    card_png(png, lines)
    ff('-loop', '1', '-i', png, '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', str(seconds),
       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(bloop.FPS), '-c:a', 'aac', '-shortest', str(path))


def overlay_png(path, k, n, title, cast, y0, pw, fmt='psycho'):
    """Tam kare şeffaf katman: üstte başlık, panellerin köşesinde 1. NORMAL / 2. PSYCHOPATH rozetleri
    (dikey karedeki rozet, VS kesimi yüzünden sağ panelde yarım kalıyordu)."""
    img = Image.new('RGBA', (OW, OH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, OW, 190], fill=BG + (255,))
    bloop.put_text_px(img, f'#{k}  {strip(title)}', OW // 2, 80, 84, (255, 255, 255), max_w=1500)
    bloop.put_text_px(img, f'{cast.upper()}  ·  {k}/{n}', OW // 2, 160, 40, (255, 214, 60))
    A, B, _ = bloop.FORMATS[fmt]
    for x, txt, c in ((OW // 2 - pw - 15, f'1. {A}', (60, 190, 90)), (OW // 2 + 15, f'2. {B}', (225, 50, 60))):
        spr = bloop.text_spr(txt, 40, (255, 255, 255))
        d.rounded_rectangle([x + 16, y0 + 16, x + 16 + spr.width + 26, y0 + 16 + spr.height + 18], radius=14,
                            fill=c, outline=bloop.DARK, width=4)
        img.paste(spr, (x + 29, y0 + 25), spr)
    img.save(path)


def scene(out, k, n, gag, cast, seed, room='living', fmt='psycho'):
    """Tek gag'i dikey render eder, yalnız gag penceresini (intro/outro yok) yatay düzene çevirir:
    NORMAL solda, PSYCHO sağda, üstte başlık."""
    plan = dict(format=fmt, cast=cast, gags=[gag], room=room, seed=seed)
    mp4 = bloop.render_video(plan, str(out / f'raw{k}'))
    T, PH, cut, top = bloop.TOP, bloop.PH, 58, 100   # alt 58: VS rozeti; üst 100: dikey karenin rozetleri
    ph = PH - cut - top
    pw, phs = 930, round(930 * ph / bloop.W)         # panel ölçeği
    y0 = 190 + (OH - 190 - phs) // 2
    hdr = out / f'hdr{k}.png'
    overlay_png(hdr, k, n, bloop.GAGS[gag]['title'], bloop.CAST[cast]['name'], y0, pw, fmt)
    dst = out / f'scene{k}.mp4'
    ff('-ss', str(bloop.INTRO), '-t', str(bloop.GAG), '-i', mp4, '-i', str(hdr), '-filter_complex',
       f'[0:v]crop={bloop.W}:{ph}:0:{T + top},scale={pw}:{phs}[n];'
       f'[0:v]crop={bloop.W}:{ph}:0:{T + PH + max(cut, top)},scale={pw}:{phs}[p];'
       f'color=c=0x{BG[0]:02x}{BG[1]:02x}{BG[2]:02x}:s={OW}x{OH}:r={bloop.FPS}:d={bloop.GAG}[bg];'
       f'[bg][n]overlay={OW // 2 - pw - 15}:{y0}[a];[a][p]overlay={OW // 2 + 15}:{y0}[b];'
       f'[b][1:v]overlay=0:0,format=yuv420p[v]',
       '-map', '[v]', '-map', '0:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-r', str(bloop.FPS),
       '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-shortest', str(dst))
    return dst


EP_FORMATS = ['psycho', 'level', 'public', 'clock', 'boss']   # 'expect' Dex'e ait (2026-10-14)
# 2026-10-13 kurgular (kullanıcı: "tekrar olmasın diye kurguları arttır"): her bölüm farklı yapı + farklı çerçeve
# (6 kurgu x 6 çerçeve = 36 bölüm tipi). Sıra n_ep'e göre döner; ardışık iki bölüm aynı kurguyu almaz.
KURGUS = ['situations', 'day', 'battle', 'ranked', 'room', 'theme']
DAY = {  # "Bir günüm": durumun günün hangi saatine ait olduğu (sıralama + kart)
    'alarm': '7:00 AM', 'coffee': '7:30 AM', 'toothpaste': '7:45 AM', 'cereal': '8:00 AM', 'egg': '8:10 AM', 'pancake': '8:20 AM',
    'toast': '8:30 AM', 'laundry': '9:00 AM', 'phone': '9:30 AM', 'shoelace': '9:45 AM', 'microwave': '12:00 PM', 'pizza': '12:30 PM',
    'sandwich': '12:45 PM', 'chips': '1:30 PM', 'hotdog': '1:45 PM', 'phonecall': '2:00 PM', 'pen': '2:30 PM', 'fan': '3:00 PM',
    'plant': '3:30 PM', 'lemon': '4:00 PM', 'boba': '4:30 PM', 'dumbbell': '5:00 PM', 'skate': '5:30 PM', 'doorbell': '6:00 PM',
    'spaghetti': '7:00 PM', 'hotsauce': '7:15 PM', 'dishes': '8:00 PM', 'fridge': '9:00 PM', 'popcorn': '9:30 PM', 'candle': '10:00 PM',
    'karaoke': '10:30 PM', 'nap': '11:30 PM'}
THEMES = {  # tema bölümleri: (başlık, durumlar)
    'food': ('Food Edition 🍕', {'cookie', 'icecream', 'ketchup', 'cake', 'soda', 'popcorn', 'sandwich', 'pizza', 'chips', 'lemon', 'donut',
                                'spaghetti', 'hotsauce', 'pancake', 'cereal', 'egg', 'watermelon', 'banana', 'toast', 'hotdog', 'boba'}),
    'morning': ('Morning Routine Edition ☀️', {'alarm', 'coffee', 'toothpaste', 'cereal', 'egg', 'pancake', 'toast', 'shoelace', 'phone', 'laundry'}),
    'party': ('Party Edition 🎉', {'balloon', 'cake', 'gift', 'gum', 'karaoke', 'soda', 'popcorn', 'cards', 'selfie', 'candybowl', 'costume', 'boba'}),
    'home': ('Home Alone Edition 🏠', {'fridge', 'doorbell', 'dishes', 'laundry', 'plant', 'candle', 'nap', 'microwave', 'fan', 'tissue', 'phonecall'}),
}

EP_SIZE = 14
HALLOWEEN = False


def plan_episode(hist, rnd, kurgu='situations', theme=None):
    month = datetime.now(timezone.utc).month
    gags = [k for k, g in bloop.GAGS.items() if month in g.get('months', range(1, 13))]
    # bölüm özeli: bu bölüm yalnız en yakın 'debut' grubunu tanıtır, sonraki grup bir sonraki bölüme kalır
    shown = {g for v in hist['videos'] if v.get('kind') == 'episode' for g, *_ in v.get('items', [])}
    pending = sorted({bloop.GAGS[k]['debut'] for k in gags if bloop.GAGS[k].get('debut') and k not in shown})
    all_gags = list(gags)
    gags = [k for k in gags if not bloop.GAGS[k].get('debut') or k in shown or (pending and bloop.GAGS[k]['debut'] == pending[0])]
    # günde 2 bölüm: her bölüm EP_SIZE durum; yeni (debut) durumlar önce, sonra bölümlerde en uzun süredir
    # görünmeyenler → aynı durum ardışık bölümlerde tekrar etmez
    last_used = {}
    for i, v in enumerate(v for v in hist['videos'] if v.get('kind') == 'episode'):
        for g, *_ in v.get('items', []): last_used[g] = i
    if kurgu == 'day':
        gags = [k for k in gags if k in DAY]
    elif kurgu == 'theme':
        gags = [k for k in gags if k in THEMES[theme][1]]
    # 2026-10-17 (kullanıcı: günde 1 bölüm, eşsiz): son 10 bölümde geçen durum KESİN yasak; havuz küçükse (gün/tema) kademeli gevşer
    n_eps = len([v for v in hist['videos'] if v.get('kind') == 'episode'])
    need = {'day': 12, 'ranked': 12, 'battle': 12}.get(kurgu, EP_SIZE)
    if kurgu in ('day', 'theme'):                      # küçük havuz: son 6 bölümle çakışmıyorsa yap, yoksa None (main başka kurgu seçer)
        fresh = [k for k in gags if last_used.get(k, -99) < n_eps - 6]
        if len(fresh) < min(need, 9): return None
        gags = fresh
    else:                                              # son 7 bölüm yasak; yetmezse sıradaki yeni durum grupları erkenden açılır
        pool = list(gags)
        for ng in range(1, len(pending) + 1):
            fresh = [k for k in pool if last_used.get(k, -99) < n_eps - 7]
            if len(fresh) >= need: gags = fresh; break
            if ng < len(pending):
                pool = [k for k in all_gags if (not bloop.GAGS[k].get('debut') or k in shown or bloop.GAGS[k]['debut'] in pending[:ng + 1])
                        and (kurgu != 'day' or k in DAY)]
        else:
            for back in (5, 3, 1, 0):
                fresh = [k for k in pool if last_used.get(k, -99) < n_eps - back]
                if len(fresh) >= need: gags = fresh; break
    rnd.shuffle(gags)
    gags.sort(key=lambda k: (not (bloop.GAGS[k].get('debut') and k not in shown), last_used.get(k, -1)))
    gags = gags[:{'day': 12, 'ranked': 12, 'battle': 12}.get(kurgu, EP_SIZE)]
    rnd.shuffle(gags)
    for first in ('cookie', 'icecream', 'pizza', 'coffee'):   # güçlü bir durumla aç
        if first in gags:
            gags.remove(first); gags.insert(0, first); break
    if 'gift' in gags:                               # kapanış: kutu içinde kutu
        gags.remove('gift'); gags.append('gift')
    casts = list(bloop.CAST)
    rnd.shuffle(casts)
    if kurgu == 'day':                                 # tek karakterin sabahtan geceye günü
        gags.sort(key=lambda k: datetime.strptime(DAY[k], '%I:%M %p'))
        return [(g, casts[0]) for g in gags]
    if kurgu == 'battle':                              # iki karakter sırayla
        return [(g, casts[i % 2]) for i, g in enumerate(gags)]
    return [(g, casts[i % len(casts)]) for i, g in enumerate(gags)]


def main():
    global FF
    import imageio_ffmpeg
    FF = imageio_ffmpeg.get_ffmpeg_exe()
    no_upload = '--no-upload' in sys.argv
    hist = json.loads(HISTORY.read_text())
    rnd = random.Random()
    eps = [v for v in hist['videos'] if v.get('kind') == 'episode']
    n_ep = len(eps) + 1
    if '--force' not in sys.argv and eps:          # günde en fazla 1 bölüm, aralarında en az 12 saat (yedek tetikler tekrar üretmez)
        now_ = datetime.now(timezone.utc)
        last = datetime.strptime(eps[-1]['date'], '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        today_n = sum(1 for v in eps if v['date'].startswith(now_.strftime('%Y-%m-%d')))
        if today_n >= 1 or (now_ - last).total_seconds() < 12 * 3600:   # 2026-10-17: günde 1 bölüm (kullanıcı)
            print(f'bugün {today_n} bölüm, son {eps[-1]["date"]}: atlandı'); return
    fmt = EP_FORMATS[(n_ep - 1) % len(EP_FORMATS)]   # her bölüm farklı kıyas çerçevesi
    A, B, Q = bloop.FORMATS[fmt]
    AB = f'{A.title()} vs {B.title()}'
    global HALLOWEEN
    _n = datetime.now(timezone.utc); HALLOWEEN = _n.month == 10 and _n.day >= 26   # son hafta: Cadılar Bayramı özel bölümü
    last_k = eps[-1].get('kurgu') if eps else None
    kurgu = KURGUS[(n_ep - 1) % len(KURGUS)]
    if kurgu == last_k:
        kurgu = KURGUS[n_ep % len(KURGUS)]
    theme = rnd.choice([t for t in THEMES if t != (eps[-1].get('theme') if eps else None)]) if kurgu == 'theme' else None
    one_room = rnd.choice(bloop.ROOMS) if kurgu == 'room' else None
    items = plan_episode(hist, rnd, kurgu, theme)
    if items is None and kurgu == 'theme':             # tema taze değil → başka tema dene
        for t in [t for t in THEMES if t != theme]:
            items = plan_episode(hist, rnd, kurgu, t)
            if items is not None: theme = t; break
    if items is None:                                  # gün/tema havuzu son 6 bölümde tükendi → geniş kurgu (tekrar olmasın)
        kurgu = next(k for k in ('situations', 'battle', 'ranked', 'room') if k != last_k); theme = None
        one_room = rnd.choice(bloop.ROOMS) if kurgu == 'room' else None
        items = plan_episode(hist, rnd, kurgu, theme)
    if kurgu == 'theme' and len(items) < 9:            # az durumlu tema → yemek teması (en geniş)
        theme = 'food'; items = plan_episode(hist, rnd, kurgu, theme) or items
    if HALLOWEEN and kurgu == 'room':
        one_room = 'spooky'
    print(f'kurgu: {kurgu} {theme or one_room or ""} · çerçeve: {fmt}', flush=True)
    n = len(items)
    out = HERE / 'output' / f'episode-{n_ep}'
    out.mkdir(parents=True, exist_ok=True)
    W8, Y8 = (255, 255, 255), (255, 214, 60)
    parts = []
    n_new = sum(1 for g, _ in items if bloop.GAGS[g].get('debut'))
    c0, c1 = bloop.CAST[items[0][1]]['name'], bloop.CAST[items[min(1, n - 1)][1]]['name']
    room_name = (one_room or '').replace('spooky', 'haunted house').title()
    big = {'situations': f'{n} SITUATIONS', 'day': f'A DAY WITH {c0.upper()}', 'battle': f'{c0.upper()} VS {c1.upper()}',
           'ranked': f'TOP {n} MOST PSYCHO', 'room': f'{room_name.upper()} CHAOS', 'theme': THEMES[theme][0].split(' ')[0].upper() + ' EDITION' if theme else ''}[kurgu]
    sub = {'situations': 'Count how many times you are #2', 'day': 'From 7 AM to midnight. Normal... or psycho?',
           'battle': 'Who is MORE psycho? Keep score!', 'ranked': 'Counting down to the most psycho move',
           'room': f'{n} situations, one {room_name.lower()}', 'theme': f'{n} situations'}[kurgu]
    card_mp4(out / 'intro.mp4', [(f'{A} vs {B}', 380, 120, (120, 235, 130)),
                                 (big + (f'  ·  {n_new} NEW' if n_new else ''), 580, 130, W8),
                                 (sub, 760, 64, Y8)], 3.6)
    parts.append(out / 'intro.mp4')
    teasers = ['What would YOU do?', f'{A.title()}... or {B.title()}?', 'Be honest.', 'Guess what happens next.',
               'This one is personal.', 'We have all been here.', 'Watch the right side.']
    for k, (gag, cast) in enumerate(items, 1):
        print(f'#{k}/{n}: {gag} ({cast})', flush=True)
        title = bloop.GAGS[gag]['title']
        new = bool(bloop.GAGS[gag].get('debut'))
        head = {'day': DAY.get(gag, ''), 'battle': f'ROUND {k}: {bloop.CAST[cast]["name"].upper()}', 'ranked': f'#{n - k + 1}'}.get(kurgu, f'SITUATION #{k}')
        card_mp4(out / f'card{k}.mp4', [(head + ('  ·  NEW!' if new else ''), 400, 110, (255, 120, 170) if new else Y8),
                                         (title, 560, 130, W8),
                                         ('First time on the channel!' if new else teasers[(k - 1) % len(teasers)], 720, 60, (200, 200, 220))])
        room = one_room or ('spooky' if HALLOWEEN and k % 2 else bloop.ROOMS[(k - 1 + n_ep) % len(bloop.ROOMS)])
        if kurgu == 'day':                               # günün saatine göre mekân
            h = datetime.strptime(DAY.get(gag, '12:00 PM'), '%I:%M %p').hour
            room = 'bedroom' if h < 8 or h >= 23 else 'kitchen' if h < 9 or 12 <= h < 14 or 19 <= h < 21 else 'office' if h < 17 else 'living'
        parts += [out / f'card{k}.mp4', scene(out, k, n, gag, cast, rnd.randrange(10 ** 6), room, fmt)]
    names = [bloop.GAGS[g]['name'] for g, _ in items]
    cols = 2 if n <= 14 else 3                          # oy kartı: 24 durum da sığsın
    rows = -(-n // cols)
    gap = min(100, 700 // rows)
    img = Image.new('RGB', (OW, OH), BG)
    bloop.put_text_px(img, {'battle': f'WHO WON: {c0.upper()} OR {c1.upper()}?', 'ranked': 'DO YOU AGREE WITH #1?', 'day': f'WHICH MOMENT IS MOST YOU?'}.get(kurgu, 'WHICH ONE IS MOST YOU?'), OW // 2, 120, 84, Y8, max_w=1800)
    for i, nm in enumerate(names):
        col, row = divmod(i, rows)
        x = OW // 2 + (col - (cols - 1) / 2) * (860 if cols == 2 else 600)
        bloop.put_text_px(img, f'{i + 1}. {nm}', int(x), 250 + row * gap, 52 if cols == 3 else 56, W8)
    bloop.put_text_px(img, 'COMMENT THE NUMBER!', OW // 2, 1000, 70, (120, 235, 130))
    img.save(out / 'outro.png')
    ff('-loop', '1', '-i', str(out / 'outro.png'), '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', '6',
       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(bloop.FPS), '-c:a', 'aac', '-shortest', str(out / 'outro.mp4'))
    parts.append(out / 'outro.mp4')
    lst = out / 'parts.txt'
    lst.write_text(''.join(f"file '{p}'\n" for p in parts))
    final = out / 'episode.mp4'
    ff('-f', 'concat', '-safe', '0', '-i', str(lst), '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
       '-pix_fmt', 'yuv420p', '-r', str(bloop.FPS), '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-ac', '2',
       '-movflags', '+faststart', str(final))
    # küçük resim: 1. sahnenin psycho anı
    ff('-ss', str(bloop.GAG * 0.8), '-i', str(out / 'scene1.mp4'), '-frames:v', '1', str(out / 'thumb_raw.png'))
    th = Image.open(out / 'thumb_raw.png').convert('RGB')
    bloop.put_text_px(th, big, OW // 2, 1000, 100, Y8, max_w=1800)
    th.resize((1280, 720)).save(out / 'thumb.png')
    print(f'bölüm hazır: {final}', flush=True)
    title = {'situations': f'{AB}: {n} Situations 🤪',
             'day': f'A Day With {c0}: {AB} ({n} Moments) ☀️',
             'battle': f'{c0} vs {c1}: Who Is More Psycho? {AB} ⚔️',
             'ranked': f'Top {n} Most Psycho Moves, Ranked 🏆 {AB}',
             'room': f'{room_name} Chaos: {AB} ({n} Situations) 🏠',
             'theme': f'{AB}: {THEMES[theme][0]} ({n} Situations)' if theme else ''}[kurgu]
    title = (title.replace('🤪', '🎃') + ' | Halloween Special') if HALLOWEEN else title + f' | Bloop Bonkers Ep {n_ep}'
    title = title[:100]
    desc = (f'{n} everyday situations, {AB.lower()}, each one shown once'
            + (f' ({sum(1 for g, _ in items if bloop.GAGS[g].get("debut"))} of them brand new, not in any Short yet)' if any(bloop.GAGS[g].get('debut') for g, _ in items) else '') + '. '
            'Which one is MOST you? Comment the number! 👇\n\n'
            + '\n'.join(f'{i + 1}. {bloop.GAGS[g]["title"].title()} ({bloop.CAST[c]["name"]})' for i, (g, c) in enumerate(items))
            + '\n\nNew Bloop Bonkers Shorts every day. Subscribe for more chaos! 🟣\n\n#animation #funny #cartoon')
    tags = ['bloop bonkers', AB.lower(), 'normal vs psycho', 'funny animation', 'cartoon', '3d animation', 'full episode',
            'normal people vs psychopaths', 'funny cartoon'] + [bloop.GAGS[g]['name'].lower() for g, _ in items[:6]]
    if no_upload:
        print('yükleme yok (--no-upload)'); return
    import upload
    privacy = os.environ.get('YT_PRIVACY') or 'private'
    vid = upload.upload(str(final), title, desc, tags, privacy, category='23')
    try:
        upload.set_thumbnail(vid, out / 'thumb.png')
    except Exception as e:
        print('küçük resim:', e)
    print(f'yüklendi: https://youtu.be/{vid} ({privacy})', flush=True)
    try:                                               # "Full Episodes" oynatma listesi (yoksa oluşturulur)
        plf = HERE / 'playlists.json'
        pl = json.loads(plf.read_text()) if plf.exists() else {}
        if 'episodes' not in pl:
            pl['episodes'] = upload.client().playlists().insert(part='snippet,status', body={
                'snippet': {'title': 'Full Episodes 🎬 Normal vs Psycho', 'description': 'Every Bloop Bonkers full episode: '
                            'everyday situations, normal vs psycho, each one shown once. New episodes every day.'},
                'status': {'privacyStatus': 'public'}}).execute()['id']
            plf.write_text(json.dumps(pl, indent=2) + '\n')
        upload.add_to_playlist(pl['episodes'], vid)
    except Exception as e:
        print('playlist:', e)
    hist['videos'].append(dict(id=vid, date=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'), kind='episode',
                               title=title, privacy=privacy, format=fmt, kurgu=kurgu, theme=theme or one_room, items=[list(x) for x in items]))
    HISTORY.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
