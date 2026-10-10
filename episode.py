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


def overlay_png(path, k, n, title, cast, y0, pw):
    """Tam kare şeffaf katman: üstte başlık, panellerin köşesinde 1. NORMAL / 2. PSYCHOPATH rozetleri
    (dikey karedeki rozet, VS kesimi yüzünden sağ panelde yarım kalıyordu)."""
    img = Image.new('RGBA', (OW, OH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, OW, 190], fill=BG + (255,))
    bloop.put_text_px(img, f'#{k}  {strip(title)}', OW // 2, 80, 84, (255, 255, 255), max_w=1500)
    bloop.put_text_px(img, f'{cast.upper()}  ·  {k}/{n}', OW // 2, 160, 40, (255, 214, 60))
    A, B, _ = bloop.FORMATS['psycho']
    for x, txt, c in ((OW // 2 - pw - 15, f'1. {A}', (60, 190, 90)), (OW // 2 + 15, f'2. {B}', (225, 50, 60))):
        spr = bloop.text_spr(txt, 40, (255, 255, 255))
        d.rounded_rectangle([x + 16, y0 + 16, x + 16 + spr.width + 26, y0 + 16 + spr.height + 18], radius=14,
                            fill=c, outline=bloop.DARK, width=4)
        img.paste(spr, (x + 29, y0 + 25), spr)
    img.save(path)


def scene(out, k, n, gag, cast, seed, room='living'):
    """Tek gag'i dikey render eder, yalnız gag penceresini (intro/outro yok) yatay düzene çevirir:
    NORMAL solda, PSYCHO sağda, üstte başlık."""
    plan = dict(format='psycho', cast=cast, gags=[gag], room=room, seed=seed)
    mp4 = bloop.render_video(plan, str(out / f'raw{k}'))
    T, PH, cut, top = bloop.TOP, bloop.PH, 58, 100   # alt 58: VS rozeti; üst 100: dikey karenin rozetleri
    ph = PH - cut - top
    pw, phs = 930, round(930 * ph / bloop.W)         # panel ölçeği
    y0 = 190 + (OH - 190 - phs) // 2
    hdr = out / f'hdr{k}.png'
    overlay_png(hdr, k, n, bloop.GAGS[gag]['title'], bloop.CAST[cast]['name'], y0, pw)
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


def plan_episode(hist, rnd):
    month = datetime.now(timezone.utc).month
    gags = [k for k, g in bloop.GAGS.items() if month in g.get('months', range(1, 13))]
    rnd.shuffle(gags)
    for first in ('cookie', 'icecream'):             # en çok izlenen durumla aç
        if first in gags:
            gags.remove(first); gags.insert(0, first); break
    if 'gift' in gags:                               # kapanış: kutu içinde kutu
        gags.remove('gift'); gags.append('gift')
    casts = list(bloop.CAST)
    rnd.shuffle(casts)
    return [(g, casts[i % len(casts)]) for i, g in enumerate(gags)]


def main():
    global FF
    import imageio_ffmpeg
    FF = imageio_ffmpeg.get_ffmpeg_exe()
    no_upload = '--no-upload' in sys.argv
    hist = json.loads(HISTORY.read_text())
    rnd = random.Random()
    n_ep = sum(1 for v in hist['videos'] if v.get('kind') == 'episode') + 1
    items = plan_episode(hist, rnd)
    n = len(items)
    out = HERE / 'output' / f'episode-{n_ep}'
    out.mkdir(parents=True, exist_ok=True)
    W8, Y8 = (255, 255, 255), (255, 214, 60)
    parts = []
    card_mp4(out / 'intro.mp4', [('NORMAL vs PSYCHO', 380, 170, (120, 235, 130)),
                                 (f'{n} SITUATIONS', 580, 150, W8),
                                 ('Count how many times YOU are the psycho', 760, 64, Y8)], 3.6)
    parts.append(out / 'intro.mp4')
    teasers = ['What would YOU do?', 'Normal... or psycho?', 'Be honest.', 'Guess what happens next.',
               'This one is personal.', 'We have all been here.', 'Watch the right side.']
    for k, (gag, cast) in enumerate(items, 1):
        print(f'#{k}/{n}: {gag} ({cast})', flush=True)
        title = bloop.GAGS[gag]['title']
        card_mp4(out / f'card{k}.mp4', [(f'SITUATION #{k}', 400, 110, Y8), (title, 560, 130, W8),
                                         (teasers[(k - 1) % len(teasers)], 720, 60, (200, 200, 220))])
        parts += [out / f'card{k}.mp4', scene(out, k, n, gag, cast, rnd.randrange(10 ** 6), bloop.ROOMS[(k - 1) % len(bloop.ROOMS)])]
    names = [bloop.GAGS[g]['name'] for g, _ in items]
    half = (n + 1) // 2
    img = Image.new('RGB', (OW, OH), BG)                # iki sütunlu oy kartı
    bloop.put_text_px(img, lines[0][0], OW // 2, 120, 84, Y8)
    for i, nm in enumerate(names):
        col, row = divmod(i, half)
        bloop.put_text_px(img, f'{i + 1}. {nm}', OW // 2 + (-430 if col == 0 else 430), 260 + row * 100, 56, W8)
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
    bloop.put_text_px(th, f'{n} SITUATIONS', OW // 2, 1000, 110, Y8)
    th.resize((1280, 720)).save(out / 'thumb.png')
    print(f'bölüm hazır: {final}', flush=True)
    title = f'Normal vs Psycho: {n} Situations 🤪 | Bloop Bonkers Full Episode {n_ep}'
    desc = (f'{n} everyday situations, normal vs psycho, every one brand new in this episode. '
            'Which one was the MOST psycho? Comment the number! 👇\n\n'
            + '\n'.join(f'{i + 1}. {bloop.GAGS[g]["title"].title()} ({bloop.CAST[c]["name"]})' for i, (g, c) in enumerate(items))
            + '\n\nNew Bloop Bonkers Shorts every day. Subscribe for more chaos! 🟣\n\n#animation #funny #cartoon')
    tags = ['bloop bonkers', 'normal vs psycho', 'funny animation', 'cartoon', '3d animation', 'full episode',
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
    hist['videos'].append(dict(id=vid, date=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'), kind='episode',
                               title=title, privacy=privacy, items=[list(x) for x in items]))
    HISTORY.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
