#!/usr/bin/env python3
"""Bloop Bonkers video motoru: 3B görünümlü orijinal karakterler, ikiye bölünmüş ekran "A vs B" Shorts.

Telif yok: karakterler, sahne, müzik ve efektlerin hepsi kodla üretilir.
Bir video = plan (format + karakter + gag listesi + müzik tohumu). Planı run.py seçer.

  .venv/bin/python bloop.py --preview 3,9 [--gags soda,balloon] [--cast zip] [--format level]
"""
import math, os, random, subprocess, sys, wave
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, S = 1080, 1920, 30, 2
TOP, PH = 170, 875
FONT = os.path.join(HERE, 'fonts', 'LuckiestGuy-Regular.ttf')
INTRO, GAG, OUTRO, NDUR = 1.4, 8.0, 3.2, 3.2
SR = 44100

DARK = (28, 22, 40)
HANDC = (250, 250, 255)
ANT = (255, 215, 60)
KETCHUP = (215, 30, 30)
COOKIE = (205, 140, 70)
PINK = (255, 150, 195)
R = 150
CX, GY = 320, 800
FLOOR, TX0, TX1, TTOP = 600, 640, 1030, 540

CAST = {
    'bloop': dict(name='Bloop', color=(125, 80, 235), shoe=(255, 150, 30), acc='antenna'),
    'zip': dict(name='Zip', color=(255, 196, 40), shoe=(60, 140, 255), acc='spikes'),
    'grumbo': dict(name='Grumbo', color=(70, 185, 90), shoe=(150, 75, 40), acc='unibrow'),
    'mimi': dict(name='Mimi', color=(255, 125, 185), shoe=(125, 90, 225), acc='bow'),
    'pip': dict(name='Pip', color=(70, 175, 240), shoe=(255, 95, 95), acc='glasses'),
    'chonk': dict(name='Chonk', color=(255, 145, 60), shoe=(70, 70, 95), acc='cap'),
}

# (üst etiket, alt etiket, kapanış sorusu)
FORMATS = {
    'psycho': ('NORMAL', 'PSYCHOPATH', 'WHICH ONE ARE YOU?'),
    'level': ('LEVEL 1', 'LEVEL 100', 'WHAT LEVEL ARE YOU?'),
    'expect': ('EXPECTATION', 'REALITY', 'SO TRUE?'),
    # 'mom' (Mom watching vs not) kaldırıldı: çocuk davranışı teması, kanal 13+ kitleye yönelik
    'boss': ('BOSS WATCHING', 'BOSS NOT WATCHING', 'BE HONEST...'),
    'public': ('IN PUBLIC', 'AT HOME', 'WHICH ONE ARE YOU?'),
    'clock': ('ME AT 8 AM', 'ME AT 3 AM', 'WHICH ONE ARE YOU?'),
}

CHAR = dict(CAST['bloop'])
PLAN = {}


def configure(plan):
    global PLAN, CHAR
    PLAN = plan
    CHAR = dict(CAST[plan['cast']])


# ---------------------------------------------------------------- yardımcılar
def clamp(x, a=0.0, b=1.0): return a if x < a else b if x > b else x
def seg(t, a, b): return clamp((t - a) / (b - a))
def sm(u): u = clamp(u); return u * u * (3 - 2 * u)
def lerp(a, b, u): return a + (b - a) * u
def lerpc(c1, c2, u): return tuple(int(round(lerp(a, b, u))) for a, b in zip(c1, c2))
def lp(a, b, u): return (lerp(a[0], b[0], u), lerp(a[1], b[1], u))
def back(u):
    u = clamp(u); c = 1.7; v = u - 1
    return 1 + (c + 1) * v ** 3 + c * v ** 2
def spring(t, amp=1.0, f=9.0, damp=6.0):
    return amp * math.exp(-damp * t) * math.sin(f * t) if t > 0 else 0.0
def rotv(x, y, ang):  # saat yönünde (ekran koordinatı)
    a = math.radians(ang)
    return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
def L(v): return int(round(v * S))
def box(x0, y0, x1, y1): return [L(x0), L(y0), L(x1), L(y1)]


# ---------------------------------------------------------------- 3B sprite'lar
LIGHT = np.array([-0.45, -0.6, 0.66]); LIGHT /= np.linalg.norm(LIGHT)
HALF = LIGHT + np.array([0, 0, 1.0]); HALF /= np.linalg.norm(HALF)


@lru_cache(64)
def sphere_base(color, spec=0.5):
    n = 640
    y, x = np.mgrid[0:n, 0:n].astype(float)
    x = (x + 0.5) / n * 2 - 1; y = (y + 0.5) / n * 2 - 1
    d = x * x + y * y; z = np.sqrt(np.clip(1 - d, 0, 1))
    lam = np.clip(x * LIGHT[0] + y * LIGHT[1] + z * LIGHT[2], 0, 1)
    shade = 0.40 + 0.68 * lam
    rim = np.clip(1 - z, 0, 1) ** 3 * 0.15
    bounce = np.clip(y, 0, 1) * (1 - z) * 0.22
    sp = np.clip(x * HALF[0] + y * HALF[1] + z * HALF[2], 0, 1) ** 60 * spec
    c = np.array(color, float) / 255
    rgb = c * shade[..., None] + (bounce + rim)[..., None] * np.array([1.0, 0.95, 0.9]) * c + sp[..., None]
    a = np.clip((1 - np.sqrt(d)) * n * 0.5, 0, 1)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 1) * 255, a * 255]).astype(np.uint8))


def sphere(color, w, h, spec=0.5):
    return sphere_base(tuple(color), spec).resize((max(1, L(w)), max(1, L(h))), Image.BILINEAR)


@lru_cache(None)
def cyl(color, w, h, rad=0, spec=0.35):
    pw, ph = L(w), L(h)
    x = (np.arange(pw) + 0.5) / pw * 2 - 1
    z = np.sqrt(np.clip(1 - x * x, 0, 1))
    lam = np.clip(x * LIGHT[0] + z * LIGHT[2] + 0.25, 0, 1)
    shade = 0.42 + 0.6 * lam
    sp = np.clip(x * HALF[0] + z * HALF[2], 0, 1) ** 30 * spec
    row = np.clip(np.array(color, float) / 255 * shade[:, None] + sp[:, None], 0, 1)
    vy = np.linspace(1.06, 0.9, ph)[:, None, None]
    rgb = np.clip(row[None, :, :] * vy, 0, 1) * 255
    m = Image.new('L', (pw, ph), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, pw - 1, ph - 1], radius=L(rad), fill=255)
    im = Image.fromarray(rgb.astype(np.uint8)).convert('RGBA'); im.putalpha(m)
    return im


@lru_cache(None)
def shadow_base():
    m = Image.new('L', (256, 128), 0); ImageDraw.Draw(m).ellipse([24, 24, 232, 104], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(14))
    im = Image.new('RGBA', (256, 128), (0, 0, 0, 0)); im.putalpha(m.point(lambda a: int(a * 0.4)))
    return im


def put(img, spr, cx, cy):
    img.paste(spr, (int(round(cx * S - spr.width / 2)), int(round(cy * S - spr.height / 2))), spr)
def put_sphere(img, color, cx, cy, w, h, spec=0.5): put(img, sphere(color, w, h, spec), cx, cy)
def put_rot(img, spr, cx, cy, ang):
    put(img, spr.rotate(-ang, resample=Image.BICUBIC, expand=True) if ang else spr, cx, cy)
def put_shadow(img, cx, cy, w, h):
    put(img, shadow_base().resize((max(1, L(w)), max(1, L(h))), Image.BILINEAR), cx, cy)
def fade(spr, k):
    s = spr.copy(); s.putalpha(spr.getchannel('A').point(lambda a: int(a * k))); return s
def scaled(spr, s):
    return spr.resize((max(1, int(spr.width * s)), max(1, int(spr.height * s))), Image.BILINEAR)


def particles(img, seed, t0, tt, n, origin, vx, vy, g, colors, size, life=2.0, emit=0.0):
    """Basit fizik parçacıkları. emit>0 ise parçacıklar emit saniye boyunca sırayla çıkar."""
    rnd = random.Random(seed)
    for k in range(n):
        te = t0 + (emit * k / n if emit else 0)
        c = rnd.choice(colors); ux, uy = rnd.uniform(*vx), rnd.uniform(*vy); s = rnd.uniform(*size)
        age = tt - te
        if 0 <= age < life:
            x = origin[0] + ux * age; y = origin[1] + uy * age + 0.5 * g * age * age
            if -60 < y < PH + 60: put_sphere(img, c, x, y, s, s, 0.6)


# ---------------------------------------------------------------- yazı
@lru_cache(None)
def font(sz): return ImageFont.truetype(FONT, sz)


@lru_cache(None)
def text_spr(txt, sz, fill, stroke=DARK):
    sw = max(2, sz // 9); f = font(sz); bb = f.getbbox(txt, stroke_width=sw)
    im = Image.new('RGBA', (bb[2] - bb[0] + 6, bb[3] - bb[1] + 6), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((3 - bb[0], 3 - bb[1]), txt, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke)
    return im


def put_text_px(img, txt, x, y, sz, fill, scale=1.0, rot=0, max_w=None):
    if scale <= 0.02: return
    spr = text_spr(txt, sz, fill)
    if max_w and spr.width > max_w: scale *= max_w / spr.width
    if scale != 1: spr = scaled(spr, scale)
    if rot: spr = spr.rotate(-rot, resample=Image.BICUBIC, expand=True)
    img.paste(spr, (int(x - spr.width / 2), int(y - spr.height / 2)), spr)


def put_text(img, txt, cx, cy, sz, fill, scale=1.0, rot=0, max_w=None):
    put_text_px(img, txt, L(cx), L(cy), L(sz), fill, scale, rot, L(max_w) if max_w else None)


# ---------------------------------------------------------------- sahne
ROOMS = ('living', 'kitchen', 'bedroom', 'office')
FLOORS = {'living': (196, 138, 88), 'kitchen': (214, 204, 186), 'bedroom': (176, 120, 150), 'office': (150, 152, 165)}


@lru_cache(None)
def background(wall, room='living'):
    w, h = L(W), L(PH)
    yy = np.arange(h)[:, None] / S; xx = np.arange(w)[None, :] / S
    k = 0.84 + 0.2 * (yy / FLOOR)
    if room == 'bedroom':      # puantiyeli duvar kâğıdı
        stripe = ((((xx + 30 * ((yy // 60) % 2)) % 60 - 30) ** 2 + ((yy % 60) - 30) ** 2) < 49) * 0.06
    elif room == 'office':
        stripe = 0.0 * xx
    elif room == 'kitchen':    # alt duvarda fayans
        stripe = ((yy > 380) & (((xx % 70) < 3) | ((yy % 70) < 3))) * -0.12
    else:
        stripe = ((xx // 60) % 2 == 0) * 0.035
    rgb_w = np.array(wall, float) * (k + stripe)[..., None]
    fy = np.clip((yy - FLOOR) / (PH - FLOOR), 0, 1)
    rgb_f = np.array(FLOORS.get(room, FLOORS['living']), float) * (0.8 + 0.28 * fy)[..., None] * np.ones_like(xx)[..., None]
    rgb = np.where((yy < FLOOR)[..., None], rgb_w, rgb_f)
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert('RGBA')
    d = ImageDraw.Draw(img)
    for y in (628, 662, 706, 760, 826):
        d.line(box(0, y, W, y), fill=(150, 100, 60), width=L(2))
    d.rectangle(box(0, FLOOR - 18, W, FLOOR + 2), fill=(246, 240, 232))
    d.line(box(0, FLOOR + 2, W, FLOOR + 2), fill=(170, 150, 130), width=L(3))
    d.rounded_rectangle(box(660, 60, 960, 330), radius=L(14), fill=(250, 250, 248))
    for i in range(0, 250):
        d.line(box(676, 76 + i, 944, 76 + i), fill=lerpc((120, 190, 250), (205, 235, 255), i / 250))
    for cx_, cy_, s in ((740, 150, 1.0), (880, 230, 0.7)):
        for dx, dy, r in ((-30, 8, 26), (0, 0, 36), (32, 8, 26)):
            d.ellipse(box(cx_ + dx * s - r * s, cy_ + dy * s - r * s, cx_ + dx * s + r * s, cy_ + dy * s + r * s), fill=(255, 255, 255))
    if room == 'office':       # pencerede şehir
        for k_, (bx, bh) in enumerate(((690, 120), (740, 170), (800, 90), (850, 150), (905, 110))):
            d.rectangle(box(bx, 326 - bh, bx + 44, 326), fill=(150, 165, 190))
            for wy in range(int(326 - bh + 12), 316, 26):
                d.rectangle(box(bx + 10, wy, bx + 18, wy + 10), fill=(255, 240, 170)); d.rectangle(box(bx + 26, wy, bx + 34, wy + 10), fill=(255, 240, 170))
    d.rectangle(box(806, 76, 814, 314), fill=(250, 250, 248)); d.rectangle(box(676, 195, 944, 203), fill=(250, 250, 248))
    if room == 'kitchen':      # üst dolap
        for x0 in (40, 190):
            d.rounded_rectangle(box(x0, 50, x0 + 140, 260), radius=L(8), fill=(245, 245, 240), outline=(170, 160, 150), width=L(3))
            d.rounded_rectangle(box(x0 + 110, 140, x0 + 120, 190), radius=L(4), fill=(150, 150, 160))
    elif room == 'bedroom':    # yıldızlı poster
        d.rounded_rectangle(box(70, 80, 250, 300), radius=L(6), fill=(60, 50, 110))
        for sx_, sy_, r_ in ((120, 140, 10), (200, 120, 7), (160, 220, 14), (220, 260, 6), (100, 270, 8)):
            d.ellipse(box(sx_ - r_, sy_ - r_, sx_ + r_, sy_ + r_), fill=(255, 230, 120))
        d.ellipse(box(170, 140, 230, 200), fill=(250, 245, 220)); d.ellipse(box(188, 132, 244, 188), fill=(60, 50, 110))
    elif room == 'office':     # kitaplık
        d.rectangle(box(50, 60, 280, 340), fill=(130, 90, 60))
        for shelf in (60, 150, 240):
            d.rectangle(box(50, shelf + 82, 280, shelf + 90), fill=(100, 65, 40))
            x = 62
            for j in range(7):
                bw = 22 + (j * 7) % 13; bh = 58 + (j * 11) % 20
                d.rectangle(box(x, shelf + 82 - bh, x + bw, shelf + 82), fill=[(200, 70, 70), (70, 120, 200), (240, 190, 60), (90, 170, 110), (160, 100, 190)][(j + shelf) % 5])
                x += bw + 5
    else:
        d.rounded_rectangle(box(60, 90, 240, 240), radius=L(6), fill=(120, 80, 50))
        d.rectangle(box(74, 104, 226, 226), fill=(170, 220, 240))
        d.polygon([(L(74), L(226)), (L(130), L(150)), (L(170), L(200)), (L(200), L(170)), (L(226), L(226))], fill=(90, 170, 90))
        d.ellipse(box(180, 118, 210, 148), fill=(255, 210, 60))
    put_shadow(img, (TX0 + TX1) / 2, GY + 6, 470, 46)
    for x in (TX0 + 30, TX1 - 30):
        put(img, cyl((120, 72, 40), 26, 250, 6), x, 690)
    d.rounded_rectangle(box(TX0 - 12, TTOP - 10, TX1 + 12, TTOP + 14), radius=L(10), fill=(212, 148, 92))
    d.rounded_rectangle(box(TX0 - 12, TTOP + 8, TX1 + 12, TTOP + 40), radius=L(8), fill=(150, 90, 50))
    d.line(box(TX0 - 4, TTOP + 10, TX1 + 4, TTOP + 10), fill=(230, 175, 120), width=L(3))
    return img


def bg(wall, v):
    room = PLAN.get('room', 'living') if PLAN else 'living'
    return background(wall if v == 'N' else lerpc(wall, (110, 45, 90), 0.3), room).copy()


# ---------------------------------------------------------------- karakter
def hand_default(i, cx=CX, gy=GY, sx=1.0, sy=1.0):
    cy = gy - 26 - R * sy
    return (cx - R * sx - 24, cy + 52) if i == 0 else (cx + R * sx + 24, cy + 52)


def mouth_y(sy=1.0): return GY - 26 - R * sy + 52 * sy
def head_top(sy=1.0): return GY - 26 - 2 * R * sy


def draw_char(img, cx, gy, o):
    t = o.get('t', 0.0)
    b = math.sin(t * 3.4) * 0.018
    sx = o.get('sx', 1.0) * (1 - b); sy = o.get('sy', 1.0) * (1 + b)
    col = o.get('color', CHAR['color']); acc = CHAR['acc']
    rx, ry = R * sx, R * sy; cy = gy - 26 - ry
    put_shadow(img, cx, gy + 2, rx * 2.4, 52)
    for s in (-1, 1): put_sphere(img, CHAR['shoe'], cx + s * 58, gy - 18, 96, 52, 0.6)
    d = ImageDraw.Draw(img)
    if acc == 'antenna':
        ang = math.sin(t * 4.1) * 8 + o.get('ant', 0)
        tipx = cx + math.sin(math.radians(ang)) * 72; tipy = cy - ry - math.cos(math.radians(ang)) * 72 + 10
        d.line(box(cx, cy - ry + 14, tipx, tipy), fill=lerpc(col, (0, 0, 0), 0.4), width=L(7))
        put_sphere(img, ANT, tipx, tipy, 36, 36, 0.7)
    elif acc == 'spikes':
        for a in (-38, -12, 14, 40):
            px, py = rotv(0, -ry - 18, a)
            put_rot(img, sphere(lerpc(col, (255, 120, 0), 0.35), 46, 96, 0.5), cx + px * 0.95, cy + py * 0.95, a + math.sin(t * 5 + a) * 4)
    put_sphere(img, col, cx, cy, 2 * rx, 2 * ry, 0.45)
    d = ImageDraw.Draw(img)
    if acc == 'cap':
        capc = (40, 95, 205)
        d.chord(box(cx - 0.8 * rx, cy - ry - 16, cx + 0.8 * rx, cy - ry + 112 * sy), 180, 360, fill=capc, outline=DARK, width=L(5))
        d.rounded_rectangle(box(cx + 0.1 * rx, cy - ry + 36 * sy, cx + 1.05 * rx, cy - ry + 60 * sy), radius=L(10),
                            fill=lerpc(capc, (0, 0, 0), 0.25), outline=DARK, width=L(4))
        d.ellipse(box(cx - 12, cy - ry - 26, cx + 12, cy - ry - 4), fill=lerpc(capc, (255, 255, 255), 0.3))
    puff = o.get('puff', 0.0)
    for s in (-1, 1):
        if puff > 0.02:
            put_sphere(img, lerpc(col, (255, 255, 255), 0.12), cx + s * 74 * sx, cy + 40 * sy, 84 * puff, 74 * puff, 0.4)
        else:
            put(img, fade(sphere((255, 110, 160), 46, 26, 0.0), 0.45), cx + s * 92 * sx, cy + 30 * sy)
    eyes = o.get('eyes', 'normal'); look = o.get('look', (0.0, 0.0))
    blink = o.get('blink', 1.0)
    if (t % 3.3) < 0.12 and eyes != 'crazy': blink = min(blink, 0.08)
    es = o.get('eye_s', 1.0)
    rnd = random.Random(int(t * FPS) * 7 + 3)
    br = o.get('brow')
    for side in (-1, 1):
        ex = cx + side * 50 * sx; ey = cy - 28 * sy
        if eyes == 'happy':
            d.arc(box(ex - 30, ey - 18, ex + 30, ey + 30), 200, 340, fill=DARK, width=L(9))
            continue
        erx, ery, pr, jx, jy = 36 * es, 48 * es, 17, 0.0, 0.0
        bl = blink
        if eyes == 'crazy':
            k = 1.22 if side == 1 else 1.02
            erx *= k; ery *= k; pr = 8
            jx, jy = rnd.uniform(-2.5, 2.5), rnd.uniform(-2.5, 2.5)
            if side == -1 and (t % 1.7) < 0.1: bl = 0.55
        if eyes == 'sleepy': bl = min(bl, 0.4)
        e_ry = max(3, ery * bl)
        d.ellipse(box(ex - erx, ey - e_ry, ex + erx, ey + e_ry), fill=(255, 255, 255), outline=DARK, width=L(4))
        if eyes == 'crazy':
            for vy in (-0.4, 0.3):
                x0 = ex + side * erx * 0.95; y0 = ey + vy * e_ry
                d.line(box(x0, y0, x0 - side * 14, y0 + 6), fill=(230, 60, 70), width=L(2))
        if bl > 0.3:
            px = ex + look[0] * (erx - pr - 6) + jx; py = ey + look[1] * (e_ry - pr - 6) + jy + 3
            d.ellipse(box(px - pr, py - pr, px + pr, py + pr), fill=DARK)
            if pr > 10:
                hx, hy = px - pr * 0.45, py - pr * 0.45
                d.ellipse(box(hx - 5, hy - 5, hx + 5, hy + 5), fill=(255, 255, 255))
        if acc == 'bow':  # kirpikler
            for k in (0, 1, 2):
                a = math.radians(-150 + k * 25) if side == -1 else math.radians(-30 - k * 25)
                x0, y0 = ex + math.cos(a) * erx, ey + math.sin(a) * e_ry
                d.line(box(x0, y0, x0 + math.cos(a) * 14, y0 + math.sin(a) * 14), fill=DARK, width=L(4))
        if br:
            top = ey - e_ry - 12
            if br == 'angry': p0, p1 = (ex - side * 26, top + 8), (ex + side * 34, top - 14)
            else: p0, p1 = (ex - side * 26, top - 12), (ex + side * 34, top + 2)
            d.line(box(p0[0], p0[1], p1[0], p1[1]), fill=DARK, width=L(10))
    if acc == 'glasses':
        gy_ = cy - 28 * sy
        for side in (-1, 1):
            ex = cx + side * 50 * sx
            d.ellipse(box(ex - 50 * es, gy_ - 54 * es, ex + 50 * es, gy_ + 54 * es), outline=DARK, width=L(9))
        d.line(box(cx - 4 * sx, gy_ - 6, cx + 4 * sx, gy_ - 6), fill=DARK, width=L(9))
    if acc == 'unibrow' and not br and eyes != 'happy':
        yb = cy - 28 * sy - 48 * es - 16
        d.line([(L(cx - 88 * sx), L(yb + 6)), (L(cx), L(yb - 4)), (L(cx + 88 * sx), L(yb + 6))], fill=DARK, width=L(13), joint='curve')
    if acc == 'bow':
        bx, by = cx + 70 * sx, cy - ry * 0.82
        for s in (-1, 1): put_rot(img, sphere((235, 50, 90), 58, 40, 0.6), bx + s * 30, by, s * 20)
        put_sphere(img, (255, 80, 120), bx, by, 26, 26, 0.6)
        d = ImageDraw.Draw(img)
    m = o.get('mouth', 'smile'); mx, my = cx, cy + 52 * sy; ma = o.get('mo', 1.0)
    if m == 'smile':
        d.arc(box(mx - 42, my - 34, mx + 42, my + 22), 25, 155, fill=DARK, width=L(8))
    elif m == 'flat':
        d.line(box(mx - 24, my, mx + 24, my), fill=DARK, width=L(8))
    elif m == 'open':
        w = 32 + 20 * ma; h = 12 + 52 * ma
        d.ellipse(box(mx - w, my - h * 0.4, mx + w, my + h * 0.75), fill=(110, 25, 40), outline=DARK, width=L(5))
        if h > 28:
            d.chord(box(mx - w * 0.55, my + h * 0.28, mx + w * 0.55, my + h * 1.0), 180, 360, fill=(240, 110, 130))
    elif m == 'grin':
        w = 76 * ma; ey0, ey1 = my - 40, my + 46; ecy, ery_ = (ey0 + ey1) / 2, (ey1 - ey0) / 2
        d.chord(box(mx - w, ey0, mx + w, ey1), 0, 180, fill=(255, 255, 255), outline=DARK, width=L(5))
        d.line(box(mx - w + 12, ecy + 20, mx + w - 12, ecy + 20), fill=DARK, width=L(3))
        for dx in range(-56, 57, 19):
            if abs(dx) < w - 8:
                yb = ecy + ery_ * math.sqrt(max(0, 1 - (dx / w) ** 2)) - 3
                d.line(box(mx + dx, ecy + 2, mx + dx, yb), fill=DARK, width=L(3))
    elif m == 'o':
        s = 1 + 0.3 * ma
        d.ellipse(box(mx - 14 * s, my - 6 * s, mx + 14 * s, my + 22 * s), fill=(110, 25, 40), outline=DARK, width=L(4))
    elif m == 'chew':
        k = abs(math.sin(t * 16))
        d.ellipse(box(mx - 26, my - 2 - 6 * k, mx + 26, my + 10 + 8 * k), fill=(110, 25, 40), outline=DARK, width=L(4))
    hs = o.get('hands', [None, None]); bob = math.sin(t * 3.4 + 1) * 5
    dflt = [(cx - rx - 24, cy + 52 + bob), (cx + rx + 24, cy + 52 - bob)]
    for i in (0, 1):
        p = hs[i] if hs[i] is not None else dflt[i]
        put_sphere(img, HANDC, p[0], p[1], 74, 68, 0.55)
    return dict(cy=cy, mx=mx, my=my, ry=ry)


def hand(img, p): put_sphere(img, HANDC, p[0], p[1], 74, 68, 0.55)


# ---------------------------------------------------------------- çekiç (saat + balkabağı)
@lru_cache(None)
def hammer_spr(lh):
    half = lh + 140
    im = Image.new('RGBA', (L(2 * half), L(2 * half)), (0, 0, 0, 0)); c = half
    put(im, cyl((240, 190, 95), 30, lh + 30, 12), c, c - lh / 2 + 15)
    put(im, cyl((220, 45, 50), 130, 250, 22).rotate(90, expand=True), c, c - lh)
    for s in (-1, 1): put(im, cyl((255, 200, 40), 138, 30, 10).rotate(90, expand=True), c + s * 122, c - lh)
    return im


HPIV = (CX + R + 30, GY - 26 - R - 20)


def hammer_angle(tt, tgt, rise, imps):
    """Çekiç açısı: rise'da arkadan yükselir, her imps anında hedefe iner; None = görünmez."""
    dx, dy = tgt[0] - HPIV[0], tgt[1] - HPIV[1]
    lh = int(math.hypot(dx, dy)); th = math.degrees(math.atan2(dx, -dy))
    if tt < rise: return None, lh
    if tt < rise + 0.5: return lerp(-170, -30, back(seg(tt, rise, rise + 0.5))), lh
    i1 = imps[0]
    if tt < i1 - 0.15: return -30 + math.sin(tt * 60) * 2, lh
    if tt < i1: return lerp(-30, th, seg(tt, i1 - 0.15, i1) ** 2), lh
    for k, imp in enumerate(imps):
        nxt = imps[k + 1] if k + 1 < len(imps) else None
        if nxt is None or tt < nxt - 0.35:
            return th - spring(tt - imp, 6, 20, 6), lh
        if tt < nxt - 0.1: return lerp(th, th - 55, sm(seg(tt, nxt - 0.35, nxt - 0.1))), lh
        if tt < nxt: return lerp(th - 55, th, seg(tt, nxt - 0.1, nxt) ** 2), lh
    return th, lh


def draw_hammer(img, ang, lh):
    if ang is not None:
        put_rot(img, hammer_spr(lh), HPIV[0], HPIV[1], ang); hand(img, HPIV)


# ---------------------------------------------------------------- gag: kurabiye
PLX = 840


@lru_cache(None)
def cookie_front(bites):
    sz = 100; n = L(sz)
    im = sphere(COOKIE, sz, sz, 0.25).copy(); d = ImageDraw.Draw(im)
    rnd = random.Random(5)
    for _ in range(9):
        a = rnd.uniform(0, 6.28); rr = rnd.uniform(0, 0.33) * n
        x = n / 2 + math.cos(a) * rr; y = n / 2 + math.sin(a) * rr; s = rnd.uniform(5, 9) * S
        d.ellipse([x - s, y - s, x + s, y + s], fill=(80, 45, 25, 255))
    a = im.getchannel('A'); da = ImageDraw.Draw(a)
    for bx, by in ((0.02, 0.42), (0.08, 0.8), (0.1, 0.08), (0.42, 0.5))[:bites]:
        rr = 0.3 * n; da.ellipse([bx * n - rr, by * n - rr, bx * n + rr, by * n + rr], fill=0)
    im.putalpha(Image.fromarray(np.minimum(np.array(a), np.array(im.getchannel('A')))))
    return im


def draw_plate_stack(img, n):
    put_sphere(img, (245, 245, 250), PLX, TTOP - 4, 250, 46, 0.6)
    for i in range(n):
        put_sphere(img, COOKIE, PLX, TTOP - 22 - i * 24, 124, 40, 0.3)


def gag_cookie(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    my = mouth_y()
    if v == 'N':
        hd = hand_default(1); top = (PLX, TTOP - 22 - 5 * 24); hm = (CX + 128, my + 24)
        if tt < 0.5: hr = lp(hd, top, sm(seg(tt, 0, 0.5)))
        elif tt < 2.75: hr = lp(top, hm, sm(seg(tt, 0.5, 0.9)))
        else: hr = lp(hm, hd, sm(seg(tt, 2.75, 3.1)))
        bt = [1.1, 1.6, 2.1, 2.6]
        bites = sum(1 for b in bt if tt >= b)
        mouth, mo = 'smile', 1.0
        for b in bt:
            if b - 0.18 <= tt < b: mouth, mo = 'open', 0.6
            elif b <= tt < b + 0.35: mouth = 'chew'
        o.update(hands=[None, hr], mouth=mouth, mo=mo, look=(0.9, 0.1) if tt < 0.9 else (0.6, 0.3))
        if tt > 2.8: o.update(eyes='happy')
        draw_plate_stack(img, 6 if tt < 0.5 else 5)
        draw_char(img, CX, GY, o)
        if tt >= 0.5 and bites < 4:
            put(img, cookie_front(bites), hr[0] - 32, hr[1] - 42); hand(img, hr)
        for b in bt:
            particles(img, int(b * 10), b, tt, 5, (CX + 40, my), (-80, 140), (-260, -60), 2200, [COOKIE], (11, 15), 0.6)
    else:
        Ls = [0.6 + i * 0.36 for i in range(6)]; FL = 0.32
        launched = sum(1 for a in Ls if tt >= a)
        arrived = [a + FL for a in Ls if tt >= a + FL]
        g = 0.065 * len(arrived)
        wob = spring(tt - arrived[-1], 0.07, 22, 5) if arrived else 0.0
        burp = spring(tt - 3.0, 0.12, 20, 4) if tt >= 3.0 else 0.0
        sx = 1 + g + wob + burp; sy = 1 + g * 0.8 - wob * 0.6 - burp * 0.6
        mouth, mo = 'grin', 1.0
        if 0.45 <= tt < 2.75: mouth = 'open'
        if 3.0 <= tt < 3.45: mouth, mo = 'open', 0.8
        eyes = 'happy' if 3.5 <= tt < 4.3 else 'crazy'
        o.update(sx=sx, sy=sy, mouth=mouth, mo=mo, eyes=eyes, brow='angry', look=(0.9, 0.05) if tt < 2.6 else (0, 0))
        draw_plate_stack(img, 6 - launched)
        info = draw_char(img, CX, GY, o)
        for i, a in enumerate(Ls):
            u = (tt - a) / FL
            if 0 <= u < 1:
                st = (PLX, TTOP - 22 - (5 - i) * 24)
                x = lerp(st[0], CX, u); y = lerp(st[1], info['my'] + 10, u) - 170 * math.sin(math.pi * u)
                put_rot(img, scaled(cookie_front(0), lerp(1, 0.55, u)), x, y, 720 * u)
        if 3.0 <= tt < 4.3:
            put_text(img, 'BURP!', CX + 250, info['my'] - 170, 100, (140, 230, 90), scale=back(seg(tt, 3.0, 3.2)), rot=-12)
        if 3.0 <= tt < 3.4: shake = 14 * (1 - seg(tt, 3.0, 3.4))
    return shake


# ---------------------------------------------------------------- gag: çalar saat
CLX = 840


@lru_cache(None)
def clock_spr():
    im = Image.new('RGBA', (L(220), L(230)), (0, 0, 0, 0))
    for s in (-1, 1): put_sphere(im, (60, 60, 72), 110 + s * 50, 212, 36, 30)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box(100, 22, 120, 60), radius=L(4), fill=(70, 70, 80))
    for s in (-1, 1): put_sphere(im, (255, 205, 50), 110 + s * 54, 62, 76, 64, 0.7)
    put_sphere(im, (225, 45, 55), 110, 135, 172, 172, 0.5)
    put_sphere(im, (255, 255, 250), 110, 138, 130, 130, 0.15)
    d = ImageDraw.Draw(im)
    for k in range(12):
        a = k * math.pi / 6; r0, r1 = (48, 58) if k % 3 == 0 else (52, 58)
        d.line(box(110 + math.cos(a) * r0, 138 + math.sin(a) * r0, 110 + math.cos(a) * r1, 138 + math.sin(a) * r1), fill=DARK, width=L(3))
    d.line(box(110, 138, 110, 96), fill=DARK, width=L(6)); d.line(box(110, 138, 140, 150), fill=DARK, width=L(6))
    d.ellipse(box(103, 131, 117, 145), fill=(225, 45, 55))
    return im


def draw_clock(img, f=1.0, ring_t=None, jit=1.0):
    spr = clock_spr(); rot = dx = 0.0
    if ring_t is not None:
        rot = math.sin(ring_t * 75) * 7 * jit; dx = math.sin(ring_t * 53) * 4 * jit
    if f < 0.999:
        spr = spr.resize((int(spr.width * (1 + (1 - f) * 0.7)), max(2, int(spr.height * f))), Image.BILINEAR)
    put_rot(img, spr, CLX + dx, TTOP + 2 - spr.height / S / 2, rot)
    if ring_t is not None and jit > 0.5:
        idx = int(ring_t / 0.14) % 2
        put_text(img, 'RING!', CLX + (-95 if idx else 95), TTOP - 285, 62, (255, 230, 60), rot=-15 if idx else 15)


def gag_alarm(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    if v == 'N':
        hd = hand_default(1); top = (CLX, TTOP - 238); press = (CLX, TTOP - 220)
        if tt < 0.6: hr = hd
        elif tt < 1.1: hr = lp(hd, top, sm(seg(tt, 0.6, 1.1)))
        elif tt < 1.35: hr = lp(top, press, math.sin(math.pi * seg(tt, 1.1, 1.35)))
        else: hr = lp(top, hd, sm(seg(tt, 1.35, 1.8)))
        f = 1 - 0.08 * math.sin(math.pi * seg(tt, 1.15, 1.35))
        eyes, mouth, mo = 'sleepy', 'flat', 1.0
        if 1.4 <= tt < 2.3: mouth, mo = 'open', 0.3 + 0.7 * math.sin(math.pi * seg(tt, 1.4, 2.3))
        if tt >= 2.3: eyes, mouth = 'happy', 'smile'
        draw_clock(img, f, t if 0 <= t < 1.2 else None)
        o.update(hands=[None, hr], eyes=eyes, mouth=mouth, mo=mo, look=(1, -0.3))
        draw_char(img, CX, GY, o)
    else:
        imp1, imp2 = 1.5, 3.05
        f = 1.0
        if tt >= imp1: f = 0.28 + spring(tt - imp1, 0.08, 26, 7)
        if tt >= imp2: f = 0.13 + spring(tt - imp2, 0.05, 26, 7)
        ang, lh = hammer_angle(tt, (CLX, TTOP - 105), 0.6, [imp1, imp2])
        if t < 0.4: eyes, mouth, brow = 'sleepy', 'flat', None
        else: eyes, mouth, brow = ('happy' if tt > 3.6 else 'crazy'), 'grin', 'angry'
        ring_t = t if 0 <= t < imp1 else (t if 2.35 <= t < 2.6 else None)
        draw_clock(img, f, ring_t, 1.0 if t < imp1 else 0.3)
        if 2.35 <= t < 2.9: put_text(img, 'ring...', CLX + 60, TTOP - 120, 42, (255, 230, 60), rot=10)
        particles(img, 11, imp1, tt, 9, (CLX, TTOP - 40), (-380, 460), (-950, -480), 2400,
                  [(150, 150, 165), (255, 205, 50), (225, 45, 55), (60, 60, 72)], (18, 40))
        o.update(hands=[None, HPIV if ang is not None else None], eyes=eyes, mouth=mouth, brow=brow, look=(1, -0.2))
        draw_char(img, CX, GY, o)
        draw_hammer(img, ang, lh)
        if imp1 <= tt < 2.2: put_text(img, 'SMASH!', CLX - 20, TTOP - 330, 96, (255, 90, 70), scale=back(seg(tt, imp1, imp1 + 0.2)), rot=-8)
        if imp2 <= tt < 3.8: put_text(img, 'BONK!', CLX - 20, TTOP - 330, 96, (255, 200, 60), scale=back(seg(tt, imp2, imp2 + 0.2)), rot=8)
        if imp1 <= tt < imp1 + 0.35: shake = 18 * (1 - seg(tt, imp1, imp1 + 0.35))
        if imp2 <= tt < imp2 + 0.35: shake = 22 * (1 - seg(tt, imp2, imp2 + 0.35))
    return shake


# ---------------------------------------------------------------- gag: ketçap
PFX = 820
BREST = (985, TTOP - 115)


@lru_cache(None)
def fries_spr():
    im = Image.new('RGBA', (L(300), L(170)), (0, 0, 0, 0))
    put_sphere(im, (245, 245, 250), 150, 140, 262, 44, 0.6)
    rnd = random.Random(3)
    for _ in range(13):
        put_rot(im, cyl((250, 200, 70), 18, 82, 6), rnd.uniform(85, 215), rnd.uniform(100, 118), rnd.uniform(-32, 32))
    return im


@lru_cache(None)
def bottle_spr():
    im = Image.new('RGBA', (L(100), L(290)), (0, 0, 0, 0))
    put(im, cyl((250, 250, 250), 26, 22, 6), 50, 38)
    put(im, cyl((250, 250, 250), 52, 34, 10), 50, 60)
    put(im, cyl(KETCHUP, 84, 192, 34), 50, 168)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box(12, 140, 88, 200), radius=L(8), fill=(255, 250, 235))
    lab = text_spr('KETCHUP', L(15), KETCHUP, (255, 250, 235))
    im.paste(lab, (L(50) - lab.width // 2, L(170) - lab.height // 2), lab)
    return im


def nozzle(c, ang):
    v = rotv(0, -117, ang); return (c[0] + v[0], c[1] + v[1])


def gag_ketchup(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1); grab = (BREST[0] - 48, BREST[1] + 30)
    put(img, fries_spr(), PFX, TTOP - 75)
    if v == 'N':
        over = (PFX - 40, TTOP - 250)
        if tt < 0.5: bc, ang = BREST, 0.0
        elif tt < 2.1: u = sm(seg(tt, 0.5, 1.0)); bc, ang = lp(BREST, over, u), 150 * u
        elif tt < 2.6: u = sm(seg(tt, 2.1, 2.6)); bc, ang = lp(over, BREST, u), 150 * (1 - u)
        else: bc, ang = BREST, 0.0
        if tt < 0.5: hr = lp(hd, grab, sm(seg(tt, 0, 0.5)))
        elif tt < 2.6: off = rotv(-48, 30, ang); hr = (bc[0] + off[0], bc[1] + off[1])
        else: hr = lp(grab, hd, sm(seg(tt, 2.6, 2.9)))
        nz = nozzle(over, 150)
        for i, d0 in enumerate((1.15, 1.5, 1.85)):
            dt = tt - d0; ox = (-30, 12, 44)[i]
            if dt >= 0.22: put_sphere(img, KETCHUP, nz[0] + ox, TTOP - 70, 30, 18, 0.7)
            elif dt >= 0: put_sphere(img, KETCHUP, nz[0] + ox * dt / 0.22, nz[1] + 1500 * dt * dt + 10, 16, 22, 0.7)
        o.update(hands=[None, hr], look=(1, 0.3), eyes='happy' if tt > 2.7 else 'normal')
        draw_char(img, CX, GY, o)
        put_rot(img, bottle_spr(), bc[0], bc[1], ang); hand(img, hr)
    else:
        fill = sm(seg(tt, 1.3, 3.0))
        sx, sy = 1 + 0.12 * fill, 1 + 0.06 * fill
        if tt >= 3.3: sx += spring(tt - 3.3, 0.1, 20, 5); sy -= spring(tt - 3.3, 0.06, 20, 5)
        my = mouth_y(sy); above = (CX + 4, my - 227)
        tossed = False
        if tt < 0.5: bc, ang = BREST, 0.0
        elif tt < 1.1: u = sm(seg(tt, 0.5, 1.1)); bc, ang = lp(BREST, above, u), 180 * u
        elif tt < 3.0: bc, ang = (above[0] + math.sin(tt * 40) * 2, above[1]), 180.0
        else:
            dt = tt - 3.0; tossed = True
            bc, ang = (above[0] + 700 * dt, above[1] - 500 * dt + 1400 * dt * dt), 180 + 900 * dt
        if tt < 0.5: hr = lp(hd, grab, sm(seg(tt, 0, 0.5)))
        elif tt < 3.0: off = rotv(-48, 30, ang); hr = (bc[0] + off[0], bc[1] + off[1])
        else: hr = None
        mouth, mo = 'grin', 1.0
        if 1.0 <= tt < 3.05: mouth, mo = 'open', 0.8 + 0.2 * math.sin(tt * 20)
        if 3.3 <= tt < 3.7: mouth, mo = 'open', 0.7
        eyes = 'happy' if 3.3 <= tt < 4.3 else 'crazy'
        o.update(sx=sx, sy=sy, color=lerpc(CHAR['color'], (232, 45, 45), fill), hands=[None, hr],
                 mouth=mouth, mo=mo, eyes=eyes, brow='angry', look=(1, 0.2) if tt < 1.0 else (0, -1))
        info = draw_char(img, CX, GY, o)
        if 1.1 <= tt < 3.0:
            nz = nozzle(bc, 180); d = ImageDraw.Draw(img)
            pts = [(L(nz[0] + math.sin(tt * 30 + k) * 3), L(lerp(nz[1], info['my'], k / 8))) for k in range(9)]
            d.line(pts, fill=KETCHUP, width=L(22), joint='curve')
            d.line([(x - L(4), y) for x, y in pts], fill=(255, 110, 100), width=L(4))
        if not tossed or bc[1] < PH + 200:
            put_rot(img, bottle_spr(), bc[0], bc[1], ang)
        if hr is not None: hand(img, hr)
        if 3.3 <= tt < 4.4:
            put_text(img, 'AHHH!', CX + 250, info['cy'] - 120, 100, (255, 120, 90), scale=back(seg(tt, 3.3, 3.5)), rot=-10)
    return shake


# ---------------------------------------------------------------- gag: pasta
CKX = 840
CAKE_C = (CKX, TTOP - 106)
CANDLES = (78, 120, 162)


@lru_cache(None)
def cake_spr():
    im = Image.new('RGBA', (L(240), L(240)), (0, 0, 0, 0))
    put(im, cyl((150, 90, 60), 210, 92, 22), 120, 182)
    for x, hh in ((30, 40), (62, 30), (96, 46), (140, 34), (176, 44), (210, 30)):
        put_sphere(im, PINK, x, 146 + hh / 2, 24, hh, 0.5)
    put_sphere(im, PINK, 120, 138, 226, 60, 0.6)
    for i, x in enumerate(CANDLES):
        put(im, cyl(((120, 200, 255), (255, 240, 120), (150, 230, 150))[i], 14, 54, 5), x, 108)
        ImageDraw.Draw(im).line(box(x, 74, x, 81), fill=DARK, width=L(3))
    return im


def flames(img, k, t):
    if k <= 0.02: return
    for x in CANDLES:
        fx, fy = CAKE_C[0] + x - 120, CAKE_C[1] - 52
        fl = 1 + 0.14 * math.sin(t * 23 + x)
        put_sphere(img, (255, 160, 40), fx, fy - 4 * k, 18 * k, 34 * k * fl, 0.2)
        put_sphere(img, (255, 245, 190), fx, fy, 8 * k, 16 * k * fl, 0.0)


def wind(img, a, b, t, n=4, spread=22, w=6, speed=900):
    d = ImageDraw.Draw(img)
    dx, dy = b[0] - a[0], b[1] - a[1]; dist = math.hypot(dx, dy); ux, uy = dx / dist, dy / dist
    for i in range(n):
        off = (i - (n - 1) / 2) * spread
        for j in range(3):
            s = (t * speed + j * dist / 3 + i * 47) % dist
            x0, y0 = a[0] + ux * s - uy * off, a[1] + uy * s + ux * off
            d.line(box(x0, y0, x0 + ux * 60, y0 + uy * 60), fill=(235, 245, 255), width=L(w))


@lru_cache(None)
def splat_spr():
    im = Image.new('RGBA', (L(W), L(PH)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    rnd = random.Random(21); c = (540, 430)
    blobs = [(c[0], c[1], 340)]
    for _ in range(30):
        a = rnd.uniform(0, 6.28); r = rnd.uniform(200, 420); s = rnd.uniform(40, 150)
        blobs.append((c[0] + math.cos(a) * r, c[1] + math.sin(a) * r * 0.85, s))
    for _ in range(40):
        a = rnd.uniform(0, 6.28); r = rnd.uniform(420, 620); s = rnd.uniform(8, 30)
        blobs.append((c[0] + math.cos(a) * r, c[1] + math.sin(a) * r, s))
    for x, y, s in blobs: d.ellipse(box(x - s, y - s, x + s, y + s), fill=PINK + (255,))
    for x, y, s in blobs[:20]:
        d.ellipse(box(x - s * 0.75, y - s * 0.75, x, y), fill=(255, 200, 222, 255))
    for _ in range(14):
        put_sphere(im, (150, 90, 60), c[0] + rnd.uniform(-300, 300), c[1] + rnd.uniform(-240, 240), rnd.uniform(30, 70), rnd.uniform(26, 56), 0.3)
    for i, col in enumerate(((120, 200, 255), (255, 240, 120), (150, 230, 150))):
        put_rot(im, cyl(col, 30, 120, 10), c[0] - 150 + i * 150, c[1] - 120 + i * 40, (-30, 15, 50)[i])
    return im


DRIPS = [(x, 430 + math.sqrt(max(0, 330 ** 2 - (x - 540) ** 2)) * 0.95 - 20, w, sp)
         for x, w, sp in ((290, 34, 180), (380, 46, 120), (470, 30, 210), (560, 52, 90), (650, 36, 160), (740, 42, 140))]


def confetti(img, seed, t0, tt, origin):
    dt = tt - t0
    if dt < 0: return
    rnd = random.Random(seed); d = ImageDraw.Draw(img)
    for _ in range(36):
        c = rnd.choice([(255, 80, 80), (255, 210, 60), (90, 200, 255), (120, 230, 120), (240, 120, 255)])
        vx, vy, sp = rnd.uniform(-520, 420), rnd.uniform(-1100, -500), rnd.uniform(5, 14)
        x = origin[0] + vx * dt + math.sin(dt * sp) * 12; y = origin[1] + vy * dt + 1300 * dt * dt
        if y < PH:
            pts = [rotv(px, py, math.degrees(dt * sp)) for px, py in ((-9, -5), (9, -5), (9, 5), (-9, 5))]
            d.polygon([(L(x + px), L(y + py)) for px, py in pts], fill=c)


def gag_cake(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    my = mouth_y()
    if v == 'N':
        puff, sx, mouth, mo = 0.0, 1.0, 'smile', 1.0
        if 0.3 <= tt < 0.9: u = sm(seg(tt, 0.3, 0.9)); puff, sx, mouth = u, 1 + 0.07 * u, 'flat'
        elif 0.9 <= tt < 1.6: u = sm(seg(tt, 0.9, 1.6)); puff, sx, mouth = 1 - u, 1.07 - 0.07 * u, 'o'
        hands = [None, None]; eyes = 'normal'
        if tt >= 1.7: eyes, mouth, mo = 'happy', 'open', 0.55
        if 1.8 <= tt < 3.0:
            sep = 18 + 55 * abs(math.sin(math.pi * (tt - 1.8) / 0.3)); cy = GY - 26 - R
            hands = [(CX - sep - 20, cy + 95), (CX + sep + 20, cy + 95)]
        put(img, cake_spr(), *CAKE_C)
        flames(img, 1 - sm(seg(tt, 0.95, 1.35)), gt)
        o.update(puff=puff, sx=sx, mouth=mouth, mo=mo, eyes=eyes, hands=hands, look=(1, -0.5))
        draw_char(img, CX, GY, o)
        if 0.9 <= tt < 1.55: wind(img, (CX + 50, my), (CAKE_C[0] - 40, CAKE_C[1] - 50), tt)
        if tt >= 1.35:
            for x in CANDLES:
                for j in range(3):
                    age = tt - 1.35 - j * 0.15
                    if 0 < age < 1.2:
                        s = 26 + 40 * age
                        put(img, fade(sphere((200, 200, 210), s, s, 0.1), 0.7 * (1 - age / 1.2)),
                            CAKE_C[0] + x - 120 + math.sin(age * 6 + x) * 10, CAKE_C[1] - 60 - age * 130)
        confetti(img, 7, 1.7, tt, (CAKE_C[0], CAKE_C[1] - 80))
        if tt >= 1.7: put_text(img, 'YAY!', 560, 240, 96, (120, 230, 120), scale=back(seg(tt, 1.7, 1.9)), rot=-8)
    else:
        u = sm(seg(tt, 0.1, 1.6))
        if tt < 1.6:
            sx, sy, puff, mouth = 1 + 0.75 * u, 1 + 0.45 * u, 1.3 * u, 'flat'
            shake = 5 * u
        else:
            k = max(0.0, 1 - (tt - 1.6) / 0.15)
            sx = 1 + 0.75 * k + spring(tt - 1.75, 0.08, 18, 5); sy = 1 + 0.45 * k; puff = 0.0
            mouth = 'o' if tt < 2.2 else 'grin'
        eyes = 'happy' if tt >= 4.0 else 'crazy'
        o.update(sx=sx, sy=sy, puff=puff, mouth=mouth, mo=1.0, eyes=eyes, brow='angry', look=(1, -0.5))
        if tt < 1.62:
            put(img, cake_spr(), *CAKE_C); flames(img, 1.0, gt)
        draw_char(img, CX, GY, o)
        if 1.6 <= tt < 2.1:
            wind(img, (CX + 60, mouth_y(sy)), (CAKE_C[0] + 60, CAKE_C[1] - 60), tt, n=7, spread=34, w=10, speed=1800)
        if 1.62 <= tt < 2.1:
            u2 = seg(tt, 1.62, 2.1)
            pos = lp(CAKE_C, (540, 430), u2 ** 1.5)
            put_rot(img, scaled(cake_spr(), 1 + 6 * u2 * u2), pos[0], pos[1], 540 * u2)
        if tt >= 2.1:
            off = sm(seg(tt, 3.8, 4.6)) * (PH + 80)
            if off < PH + 60:
                put(img, splat_spr(), W / 2, PH / 2 + off); d = ImageDraw.Draw(img)
                for x, y0, w, sp in DRIPS:
                    ln = min(sp * (tt - 2.1), 380); y = y0 + off
                    d.rectangle(box(x - w / 2, y, x + w / 2, y + ln), fill=PINK)
                    d.ellipse(box(x - w / 2, y + ln - w / 2, x + w / 2, y + ln + w / 2), fill=PINK)
            if tt < 2.9:
                put_text(img, 'SPLAT!', 540, 180, 120, (255, 255, 255), scale=back(seg(tt, 2.1, 2.3)), rot=-6)
        if 2.1 <= tt < 2.5: shake = 24 * (1 - seg(tt, 2.1, 2.5))
    return shake


# ---------------------------------------------------------------- gag: gazoz
CANP = (850, TTOP - 66)
SODA = (150, 85, 40)


@lru_cache(None)
def can_spr():
    im = Image.new('RGBA', (L(80), L(140)), (0, 0, 0, 0))
    put(im, cyl((40, 120, 230), 70, 124, 16), 40, 74)
    put_sphere(im, (205, 205, 215), 40, 16, 62, 14, 0.8)
    lab = text_spr('FIZZ', L(20), (255, 255, 255))
    im.paste(lab, (L(40) - lab.width // 2, L(80) - lab.height // 2), lab)
    return im


def gag_soda(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1); my = mouth_y()
    if v == 'N':
        sip = (CX + 112, my - 20)
        if tt < 0.5: cp, ang = CANP, 0.0
        elif tt < 2.3:
            cp = lp(CANP, sip, sm(seg(tt, 0.5, 0.9)))
            ang = -40 * sm(seg(tt, 0.9, 1.1)) * (1 - sm(seg(tt, 2.0, 2.2)))
        elif tt < 2.8: cp, ang = lp(sip, CANP, sm(seg(tt, 2.3, 2.8))), 0.0
        else: cp, ang = CANP, 0.0
        off = rotv(40, 24, ang)
        if tt < 0.5: hr = lp(hd, (CANP[0] + 40, CANP[1] + 24), sm(seg(tt, 0, 0.5)))
        elif tt < 2.8: hr = (cp[0] + off[0], cp[1] + off[1])
        else: hr = lp((CANP[0] + 40, CANP[1] + 24), hd, sm(seg(tt, 2.8, 3.1)))
        mouth = 'o' if 1.05 <= tt < 2.05 else 'smile'
        o.update(hands=[None, hr], mouth=mouth, eyes='happy' if 1.1 <= tt < 2.0 or tt > 2.9 else 'normal', look=(1, 0))
        draw_char(img, CX, GY, o)
        put_rot(img, can_spr(), cp[0], cp[1], ang); hand(img, hr)
        if 2.1 <= tt < 3.0: put_text(img, 'AHH~', CX + 40, 300, 70, (120, 200, 255), scale=back(seg(tt, 2.1, 2.3)), rot=-6)
    else:
        sp = (CX + 205, GY - 26 - R - 30)
        if tt < 0.5: cp, ang = CANP, 0.0
        elif tt < 0.8: cp, ang = lp(CANP, sp, sm(seg(tt, 0.5, 0.8))), 0.0
        elif tt < 1.7: cp, ang = (sp[0] + math.sin(tt * 47) * 18, sp[1] + math.sin(tt * 45) * 45), math.sin(tt * 45) * 22
        else: cp, ang = sp, 0.0
        off = rotv(40, 24, ang)
        hr = lp(hd, (CANP[0] + 40, CANP[1] + 24), sm(seg(tt, 0, 0.5))) if tt < 0.5 else (cp[0] + off[0], cp[1] + off[1])
        soak = sm(seg(tt, 2.2, 3.0)) * 0.45
        eyes = 'happy' if tt > 3.4 else 'crazy'
        mouth = 'open' if 1.7 <= tt < 2.4 else 'grin'
        o.update(hands=[None, hr], mouth=mouth, mo=1.0, eyes=eyes, brow='angry' if tt < 1.7 else None,
                 color=lerpc(CHAR['color'], SODA, soak), look=(1, -0.6) if tt > 1.7 else (1, 0))
        info = draw_char(img, CX, GY, o)
        put_rot(img, can_spr(), cp[0], cp[1], ang); hand(img, hr)
        top = (sp[0], sp[1] - 62)
        particles(img, 3, 1.72, tt, 70, top, (-260, 160), (-1500, -1000), 1900,
                  [SODA, (190, 120, 60), (255, 250, 240)], (16, 34), life=1.6, emit=1.2)
        if tt > 2.4:
            particles(img, 4, 2.4, tt, 14, (CX, info['cy'] - info['ry']), (-160, 160), (0, 60), 700, [SODA], (12, 20), life=1.6, emit=1.2)
        if 1.72 <= tt < 2.7: put_text(img, 'FIZZ!', 640, 150, 110, (120, 200, 255), scale=back(seg(tt, 1.72, 1.9)), rot=-10)
        if 1.72 <= tt < 2.0: shake = 10
    return shake


# ---------------------------------------------------------------- gag: dondurma
SCOOP = (150, 230, 190)


@lru_cache(None)
def cone_spr():
    im = Image.new('RGBA', (L(90), L(170)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.polygon([(L(10), L(66)), (L(80), L(66)), (L(45), L(166))], fill=(225, 170, 100))
    for k in range(-3, 5):
        d.line(box(10 + k * 16, 66, 45 + k * 16 - 30, 166), fill=(185, 125, 60), width=L(2))
        d.line(box(80 - k * 16, 66, 45 - k * 16 + 30, 166), fill=(185, 125, 60), width=L(2))
    mask = Image.new('L', im.size, 0)
    ImageDraw.Draw(mask).polygon([(L(10), L(66)), (L(80), L(66)), (L(45), L(166))], fill=255)
    im.putalpha(mask)
    return im


def draw_cone(img, c, scoop):
    put(img, cone_spr(), c[0], c[1])
    if scoop > 0.05:
        put_sphere(img, SCOOP, c[0], c[1] - 30 - 30 * (1 - scoop), 92 * scoop, 84 * scoop, 0.6)


def gag_icecream(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    my = mouth_y(); rest = (CX + 175, my + 15); lick = (CX + 98, my + 40)
    if v == 'N':
        hp = rest; scoop = 1.0; mouth = 'smile'
        for k, li in enumerate((0.6, 1.3, 2.0)):
            if li - 0.25 <= tt < li: hp = lp(rest, lick, sm(seg(tt, li - 0.25, li))); mouth = 'open'
            elif li <= tt < li + 0.3: hp = lp(lick, rest, sm(seg(tt, li, li + 0.3)))
            if tt >= li: scoop = 1 - 0.15 * (k + 1)
        o.update(hands=[None, hp], mouth=mouth, mo=0.5, eyes='happy' if tt > 2.3 else 'normal', look=(1, 0.2))
        draw_char(img, CX, GY, o)
        draw_cone(img, (hp[0] - 4, hp[1] - 25), scoop); hand(img, hp)
        if tt >= 2.3: put_text(img, 'YUM!', 560, 260, 96, SCOOP, scale=back(seg(tt, 2.3, 2.5)), rot=-8)
    else:
        bite = (CX + 62, my + 38)
        if tt < 0.3: hp = rest
        elif tt < 0.55: hp = lp(rest, bite, sm(seg(tt, 0.3, 0.55)))
        elif tt < 0.9: hp = lp(bite, rest, sm(seg(tt, 0.55, 0.9)))
        elif 3.0 <= tt < 3.25: hp = lp(rest, bite, sm(seg(tt, 3.0, 3.25)))
        else: hp = rest
        scoop = 1.0 if tt < 0.55 else 0.0
        frz = sm(seg(tt, 1.3, 1.6)) * (1 - sm(seg(tt, 3.8, 4.7)))
        shiver = math.sin(tt * 70) * 4 * frz
        mouth, mo = 'grin', 1.0
        if 0.35 <= tt < 0.55: mouth = 'open'
        elif 0.55 <= tt < 1.2 or 3.25 <= tt < 3.8: mouth = 'chew'
        elif frz > 0.3: mo = 0.85 + 0.15 * math.sin(tt * 40)
        eyes = 'happy' if tt > 4.0 else 'crazy'
        o.update(hands=[None, hp], mouth=mouth, mo=mo, eyes=eyes, color=lerpc(CHAR['color'], (175, 225, 255), frz * 0.85),
                 look=(1, 0.2) if tt < 1.3 else (0, -0.8))
        info = draw_char(img, CX + shiver, GY, o)
        if tt < 3.25: draw_cone(img, (hp[0] - 4, hp[1] - 25), scoop)
        hand(img, hp)
        if frz > 0.05:
            for k in range(8):
                a = tt * 1.5 + k * 0.785
                put(img, fade(sphere((235, 248, 255), 22, 22, 0.9), frz), CX + math.cos(a) * 200, info['cy'] + math.sin(a) * 170)
        if 1.3 <= tt < 3.0:
            put_text(img, 'BRAIN FREEZE!', 560, 270, 86, (175, 225, 255), scale=back(seg(tt, 1.3, 1.5)), rot=-5, max_w=1000)
        if 3.25 <= tt < 3.5: shake = 6
    return shake


# ---------------------------------------------------------------- gag: balon
BALLOON = (235, 60, 75)


def draw_balloon(img, c, r, string_to=None):
    if string_to:
        ImageDraw.Draw(img).line(box(c[0], c[1] + r, string_to[0], string_to[1]), fill=(90, 90, 100), width=L(3))
    put_sphere(img, BALLOON, c[0], c[1], 1.84 * r, 2 * r, 0.8)
    put_sphere(img, BALLOON, c[0], c[1] + r + 4, 18, 14, 0.4)


def gag_balloon(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    my = mouth_y()
    if v == 'N':
        breaths = ((0.2, 0.6), (0.8, 1.2), (1.4, 1.8))
        r = 12 + sum(20 * sm(seg(tt, a, b)) for a, b in breaths)
        puff = max([math.sin(math.pi * seg(tt, a, b)) for a, b in breaths] + [0])
        o.update(puff=puff * 0.9, mouth='o' if tt < 1.9 else 'smile', eyes='happy' if tt > 2.4 else 'normal', look=(1, 0))
        if tt >= 1.9:
            hp = lp(hand_default(1), (CX + 200, my - 40), sm(seg(tt, 1.9, 2.3)))
            o['hands'] = [None, hp]
        draw_char(img, CX, GY, o)
        if tt < 1.9:
            draw_balloon(img, (CX + 30 + r * 0.92, my - 4), r)
        else:
            c = lp((CX + 30 + r * 0.92, my - 4), (CX + 250, 270 + math.sin(gt * 3) * 12), sm(seg(tt, 1.9, 2.5)))
            draw_balloon(img, c, r, string_to=hp)
            hand(img, hp)
    else:
        u = seg(tt, 0.2, 2.6)
        popped = tt >= 2.65
        r = 12 + 330 * u ** 1.3 + math.sin(tt * 30) * 4 * u
        soot = 0.55 if popped else 0.0
        knock = -spring(tt - 2.65, 40, 12, 4) if popped else 0.0
        o.update(puff=0 if popped else 0.6 + 0.6 * u, mouth='grin' if popped and tt > 3.3 else ('flat' if popped else 'o'),
                 eyes='happy' if tt > 4.0 else ('normal' if popped else 'crazy'), brow=None if popped else 'angry',
                 color=lerpc(CHAR['color'], (55, 50, 60), soot), look=(0, 0) if popped else (1, 0))
        draw_char(img, CX + knock, GY, o)
        if not popped:
            draw_balloon(img, (CX + 30 + r * 0.92, mouth_y() - 4), r)
            shake = 6 * u * u
        particles(img, 9, 2.65, tt, 16, (CX + 330, 400), (-900, 900), (-1100, 300), 1500, [BALLOON], (20, 46), life=1.5)
        if popped and tt < 3.6:
            put_text(img, 'POP!', 600, 300, 150, (255, 230, 60), scale=back(seg(tt, 2.65, 2.85)), rot=-8)
        if 2.65 <= tt < 3.0: shake = 26 * (1 - seg(tt, 2.65, 3.0))
    return shake


# ---------------------------------------------------------------- gag: balkabağı (Ekim)
PKX = 845
PK = (245, 130, 30)


@lru_cache(None)
def pumpkin_spr(stage, lit):
    im = Image.new('RGBA', (L(220), L(180)), (0, 0, 0, 0))
    put(im, cyl((95, 120, 40), 18, 40, 6), 112, 30)
    for dx, w in ((-55, 90), (55, 90), (-28, 100), (28, 100), (0, 104)):
        put_sphere(im, lerpc(PK, (200, 90, 10), 0.2 if abs(dx) > 40 else 0), 110 + dx, 104, w, 140, 0.4)
    d = ImageDraw.Draw(im); hole = (255, 200, 70) if lit else (70, 35, 10)
    if stage >= 1:
        for s in (-1, 1): d.polygon([(L(110 + s * 42), L(70)), (L(110 + s * 18), L(102)), (L(110 + s * 62), L(102))], fill=hole)
    if stage >= 2: d.polygon([(L(110), L(108)), (L(100), L(124)), (L(120), L(124))], fill=hole)
    if stage >= 3:
        pts = [(60, 134), (75, 146), (90, 136), (105, 150), (120, 136), (135, 150), (150, 136), (162, 134), (140, 160), (80, 160)]
        d.polygon([(L(x), L(y)) for x, y in pts], fill=hole)
    return im


def gag_pumpkin(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    pc = (PKX, TTOP - 86)
    if v == 'N':
        cuts = (1.2, 1.6, 2.0)
        stage = sum(1 for c in cuts if tt >= c); lit = tt >= 2.4
        at = (PKX - 115, TTOP - 110)
        if tt < 0.9: hr = lp(hand_default(1), at, sm(seg(tt, 0.4, 0.9)))
        elif tt < 2.15: hr = (at[0] + math.sin(tt * 30) * 10, at[1] + math.cos(tt * 23) * 12)
        else: hr = lp(at, hand_default(1), sm(seg(tt, 2.15, 2.5)))
        if lit:
            put(img, fade(sphere((255, 210, 90), 330, 280, 0.0), 0.35 + 0.1 * math.sin(gt * 9)), pc[0], pc[1])
        put(img, pumpkin_spr(stage, lit), *pc)
        o.update(hands=[None, hr], eyes='happy' if lit else 'normal', mouth='open' if lit else 'smile', mo=0.5, look=(1, -0.1))
        draw_char(img, CX, GY, o)
        if lit: put_text(img, 'SPOOKY!', 560, 250, 90, (255, 170, 50), scale=back(seg(tt, 2.4, 2.6)), rot=-8)
    else:
        imp = 1.3
        ang, lh = hammer_angle(tt, (PKX, TTOP - 80), 0.4, [imp])
        smashed = tt >= imp
        if not smashed: put(img, pumpkin_spr(0, False), *pc)
        else:
            put_sphere(img, PK, PKX, TTOP - 8, 300 + spring(tt - imp, 30, 20, 6), 34, 0.3)
        particles(img, 5, imp, tt, 14, (PKX, TTOP - 60), (-500, 500), (-1000, -400), 2300, [PK, (220, 110, 20)], (24, 50))
        particles(img, 6, imp, tt, 18, (PKX, TTOP - 60), (-420, 420), (-900, -300), 2300, [(250, 240, 210)], (8, 12))
        hat = None
        if smashed:
            u = seg(tt, imp, imp + 1.1)
            ht = (CX + 8, head_top() - 12)
            hat = (lerp(PKX, ht[0], u), lerp(TTOP - 150, ht[1], u) - 380 * math.sin(math.pi * u), 720 * u if u < 1 else 0)
        o.update(hands=[None, HPIV if ang is not None else None], eyes='happy' if tt > 3.2 else 'crazy',
                 mouth='grin', brow=None if tt > 3.2 else 'angry', look=(1, 0) if tt < 2 else (0, -1),
                 ant=-25 if tt > imp + 1.1 else 0)
        draw_char(img, CX, GY, o)
        if hat:
            spr = Image.new('RGBA', (L(110), L(80)), (0, 0, 0, 0))
            put_sphere(spr, PK, 55, 56, 110, 46, 0.4); put(spr, cyl((95, 120, 40), 18, 40, 6), 57, 22)
            put_rot(img, spr, hat[0], hat[1], hat[2])
        draw_hammer(img, ang, lh)
        if imp <= tt < 2.1: put_text(img, 'SMASH!', PKX - 20, TTOP - 330, 96, (255, 140, 40), scale=back(seg(tt, imp, imp + 0.2)), rot=-8)
        if imp <= tt < imp + 0.35: shake = 20 * (1 - seg(tt, imp, imp + 0.35))
    return shake


# ---------------------------------------------------------------- gag kataloğu

# ================================================================ yeni gag'ler (2026-10-08): çeşitlilik, tekrar azaltma
# ---------------------------------------------------------------- gag: kahve
COFFEE = (95, 60, 35)
MUGP = (850, TTOP - 44)
POTP = (975, TTOP - 70)


@lru_cache(None)
def mug_spr():
    im = Image.new('RGBA', (L(110), L(100)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse(box(62, 22, 104, 70), outline=(235, 235, 240), width=L(9))
    put(im, cyl((245, 245, 248), 70, 84, 12), 42, 54)
    put_sphere(im, COFFEE, 42, 16, 62, 14, 0.5)
    return im


@lru_cache(None)
def pot_spr(level):
    im = Image.new('RGBA', (L(110), L(170)), (0, 0, 0, 0))
    put(im, cyl((205, 225, 240), 90, 130, 30, spec=0.6), 55, 100)
    d = ImageDraw.Draw(im)
    if level > 0.02:
        h = 110 * level
        d.rounded_rectangle(box(14, 160 - h, 96, 158), radius=L(18), fill=COFFEE)
    d.rectangle(box(30, 26, 80, 38), fill=(40, 40, 46))
    d.ellipse(box(95, 70, 112, 130), outline=(40, 40, 46), width=L(7))
    return im


def gag_coffee(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1); my = mouth_y()
    if v == 'N':
        sip = (CX + 112, my - 18)
        if tt < 0.5: cp, ang = MUGP, 0.0
        elif tt < 2.3:
            cp = lp(MUGP, sip, sm(seg(tt, 0.5, 0.9)))
            ang = -35 * sm(seg(tt, 0.9, 1.1)) * (1 - sm(seg(tt, 2.0, 2.2)))
        elif tt < 2.8: cp, ang = lp(sip, MUGP, sm(seg(tt, 2.3, 2.8))), 0.0
        else: cp, ang = MUGP, 0.0
        hr = lp(hd, (MUGP[0] + 44, MUGP[1] + 20), sm(seg(tt, 0, 0.5))) if tt < 0.5 else \
            ((cp[0] + 44, cp[1] + 20) if tt < 2.8 else lp((MUGP[0] + 44, MUGP[1] + 20), hd, sm(seg(tt, 2.8, 3.1))))
        put(img, pot_spr(0.8), *POTP)
        o.update(hands=[None, hr], mouth='o' if 1.05 <= tt < 2.05 else 'smile',
                 eyes='happy' if 1.1 <= tt < 2.0 or tt > 2.6 else 'sleepy' if tt < 0.9 else 'normal', look=(1, 0))
        draw_char(img, CX, GY, o)
        put_rot(img, mug_spr(), cp[0], cp[1], ang); hand(img, hr)
        if 2.1 <= tt < 3.0: put_text(img, 'MMM~', CX + 60, 300, 72, (230, 190, 140), scale=back(seg(tt, 2.1, 2.3)), rot=-6)
    else:
        above = (CX + 4, my - 230)
        drink = 1.0 <= tt < 2.4
        if tt < 0.5: pp, ang, lvl = POTP, 0.0, 0.8
        elif tt < 1.0: pp, ang, lvl = lp(POTP, above, sm(seg(tt, 0.5, 1.0))), 175 * sm(seg(tt, 0.5, 1.0)), 0.8
        elif tt < 2.4: pp, ang, lvl = (above[0] + math.sin(tt * 40) * 2, above[1]), 175.0, 0.8 * (1 - seg(tt, 1.0, 2.4))
        else:
            dt = tt - 2.4; pp, ang, lvl = (above[0] - 600 * dt, above[1] - 400 * dt + 1500 * dt * dt), 175 - 700 * dt, 0.0
        hr = lp(hd, (POTP[0] - 50, POTP[1] + 30), sm(seg(tt, 0, 0.5))) if tt < 0.5 else \
            ((pp[0] - 50, pp[1] + 30) if tt < 2.4 else None)
        hyper = sm(seg(tt, 2.4, 2.7))
        # 3.3-4.3: ışık hızında sağa fırlayıp soldan geri gelir
        if 3.3 <= tt < 3.7: cx = lerp(CX, 1400, seg(tt, 3.3, 3.7) ** 2)
        elif 3.7 <= tt < 4.2: cx = lerp(-400, CX, sm(seg(tt, 3.7, 4.2)))
        else: cx = CX + math.sin(tt * 90) * 7 * hyper
        o.update(hands=[None, hr], mouth='open' if drink else 'grin', mo=1.0, eyes='crazy' if tt > 0.3 else 'sleepy',
                 brow='angry' if tt > 0.3 else None, eye_s=1.0 + 0.25 * hyper, look=(1, -0.4) if drink else (0, 0),
                 color=lerpc(CHAR['color'], (230, 120, 60), 0.25 * hyper))
        info = draw_char(img, cx, GY, o)
        if drink:
            d = ImageDraw.Draw(img); nz = (pp[0], pp[1] + 80)
            d.line([(L(nz[0] + math.sin(tt * 30 + k) * 3), L(lerp(nz[1], info['my'], k / 6))) for k in range(7)],
                   fill=COFFEE, width=L(18), joint='curve')
        if tt < 3.3 or pp[1] < PH + 200:
            put_rot(img, pot_spr(round(lvl, 1)), pp[0], pp[1], ang)
        if hr is not None: hand(img, hr)
        if hyper > 0.5 and not (3.3 <= tt < 4.2):
            d = ImageDraw.Draw(img)
            for k in range(6):
                a = k * 1.05 + tt * 3
                x0, y0 = CX + math.cos(a) * 230, info['cy'] + math.sin(a) * 200
                d.line(box(x0, y0, x0 + math.cos(a) * 40, y0 + math.sin(a) * 40), fill=(255, 220, 90), width=L(6))
        if 3.3 <= tt < 4.2: wind(img, (CX - 300, info['cy']), (CX + 500, info['cy']), tt, n=6, spread=40, w=9, speed=2400)
        if 2.5 <= tt < 3.4: put_text(img, 'MAXIMUM POWER!', 540, 250, 84, (255, 200, 60), scale=back(seg(tt, 2.5, 2.7)), rot=-6, max_w=1000)
        if 3.3 <= tt < 3.6: shake = 12
    return shake


# ---------------------------------------------------------------- gag: sakız
GUM = (255, 120, 190)


def gag_gum(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    if v == 'N':
        r = 8 + 40 * sm(seg(tt, 1.0, 2.2)) if tt < 2.3 else 0
        mouth = 'chew' if tt < 1.0 else ('o' if tt < 2.3 else 'smile')
        o.update(mouth=mouth, eyes='happy' if tt > 2.5 else 'normal', look=(0.2, 0.3))
        info = draw_char(img, CX, GY, o)
        if r:
            put_sphere(img, GUM, CX + 6, info['my'] + 8, 2 * r, 1.9 * r, 0.8)
        if 2.3 <= tt < 2.6: put_text(img, 'pop', CX + 120, info['my'] - 60, 50, GUM, scale=back(seg(tt, 2.3, 2.45)))
        if tt >= 2.3:
            for k, (dx, dy) in enumerate(((-30, 10), (34, 4), (0, 30))):
                put_sphere(img, GUM, CX + dx, info['my'] + dy, 26, 18, 0.5)
    else:
        grow = sm(seg(tt, 0.8, 3.0)); r = 8 + 250 * grow
        lift = 360 * sm(seg(tt, 2.2, 3.7)) if tt < 3.9 else 360 * (1 - sm(seg(tt, 3.9, 4.3))) + spring(tt - 4.3, -30, 18, 6)
        popped = tt >= 3.9
        o.update(mouth='chew' if tt < 0.8 else ('o' if not popped else 'grin'), eyes='crazy', brow='angry' if tt < 2.2 else None,
                 look=(0, -0.8) if 2.2 <= tt < 3.9 else (0.2, 0.3), sy=1.0 + spring(tt - 4.3, -0.15, 20, 5) if tt > 4.3 else 1.0)
        info = draw_char(img, CX, GY - max(lift, 0), o)
        if not popped:
            put_sphere(img, GUM, CX + 6, info['my'] + 10 - r * 0.9, 2 * r, 1.9 * r, 0.85)
            if 2.4 <= tt < 3.8: put_text(img, 'WHEEE!', 640, 200, 100, GUM, scale=back(seg(tt, 2.4, 2.6)), rot=-8)
        else:
            particles(img, 12, 3.9, tt, 18, (CX, info['my'] - 200), (-700, 700), (-900, 200), 1500, [GUM], (24, 50), life=1.2)
            for dx, dy, s in ((-70, -60, 60), (60, -90, 50), (-20, 10, 70), (80, 30, 44), (-90, 40, 40)):
                put_sphere(img, GUM, CX + dx, info['cy'] + dy, s, s * 0.7, 0.5)
            if tt < 4.5: put_text(img, 'POP!', 600, 280, 140, (255, 230, 60), scale=back(seg(tt, 3.9, 4.05)), rot=-8)
        if 3.9 <= tt < 4.2: shake = 22
    return shake


# ---------------------------------------------------------------- gag: patlamış mısır
POT2 = (850, TTOP - 50)
CORN = [(255, 248, 225), (255, 236, 170), (250, 225, 140)]


def gag_popcorn(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    my = mouth_y(); hd = hand_default(1)
    if v == 'N':
        put_sphere(img, (210, 120, 60), 850, TTOP - 10, 230, 60, 0.4)            # kâse
        for k in range(14):
            rnd = random.Random(k); put_sphere(img, rnd.choice(CORN), 850 + rnd.uniform(-90, 90), TTOP - 40 + rnd.uniform(-14, 6), 30, 26, 0.3)
        grabs = (0.6, 1.5, 2.4)
        hr, mouth = hd, 'smile'
        for g in grabs:
            if g - 0.35 <= tt < g: hr = lp(hd, (850, TTOP - 60), sm(seg(tt, g - 0.35, g)))
            elif g <= tt < g + 0.3: hr = lp((850, TTOP - 60), (CX + 90, my + 10), sm(seg(tt, g, g + 0.3))); mouth = 'open'
            elif g + 0.3 <= tt < g + 0.6: hr = lp((CX + 90, my + 10), hd, sm(seg(tt, g + 0.3, g + 0.6))); mouth = 'chew'
        o.update(hands=[None, hr], mouth=mouth, mo=0.5, eyes='happy' if tt > 2.9 else 'normal', look=(1, 0.3))
        draw_char(img, CX, GY, o)
        if any(g <= tt < g + 0.3 for g in grabs): put_sphere(img, CORN[0], hr[0] - 10, hr[1] - 30, 26, 22, 0.3)
    else:
        put(img, cyl((70, 70, 80), 160, 90, 18), *POT2)
        lid_t = tt - 1.0
        if lid_t < 0:
            put_sphere(img, (90, 90, 100), POT2[0], POT2[1] - 50, 170, 34, 0.7)
        elif lid_t < 1.5:
            put_rot(img, sphere((90, 90, 100), 170, 34, 0.7), POT2[0] + 300 * lid_t, POT2[1] - 50 - 900 * lid_t + 1400 * lid_t ** 2, 600 * lid_t)
        particles(img, 21, 1.0, tt, 130, (POT2[0], POT2[1] - 40), (-520, 260), (-1600, -900), 1900, CORN, (14, 24), life=2.2, emit=2.4)
        pile = sm(seg(tt, 1.6, 4.0))
        if pile > 0.01:
            put_sphere(img, CORN[1], 600, GY + 10, 900 * pile, 90 * pile, 0.3)
        o.update(mouth='open' if 1.2 <= tt < 3.6 else 'grin', mo=1.0, eyes='crazy', brow='angry',
                 look=(0.6, -0.9) if tt > 1.0 else (1, 0), hands=[(CX - 200, mouth_y() - 120), (CX + 200, mouth_y() - 120)] if 1.2 <= tt < 3.6 else [None, None])
        draw_char(img, CX, GY, o)
        if 1.0 <= tt < 2.6: put_text(img, 'POP POP POP!', 560, 210, 92, (255, 230, 120), scale=back(seg(tt, 1.0, 1.2)), rot=-6, max_w=980)
        if 1.0 <= tt < 1.25: shake = 10
    return shake


# ---------------------------------------------------------------- gag: diş macunu
PASTE = (225, 250, 250)
FOAM = (245, 252, 255)


@lru_cache(None)
def tube_spr():
    im = Image.new('RGBA', (L(60), L(170)), (0, 0, 0, 0))
    put(im, cyl((70, 150, 230), 52, 120, 10), 30, 100)
    put(im, cyl((250, 250, 250), 22, 26, 6), 30, 28)
    ImageDraw.Draw(im).rectangle(box(6, 150, 54, 162), fill=(60, 130, 210))
    return im


@lru_cache(None)
def brush_spr():
    im = Image.new('RGBA', (L(40), L(200)), (0, 0, 0, 0))
    put(im, cyl((120, 210, 140), 16, 170, 8), 20, 110)
    d = ImageDraw.Draw(im)
    for k in range(5):
        d.rectangle(box(8 + k * 5, 4, 10 + k * 5, 26), fill=(255, 255, 255))
    return im


def gag_toothpaste(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    my = mouth_y()
    hl, hr = (CX - 200, my + 20), (CX + 200, my + 20)
    if v == 'N':
        brushing = 1.4 <= tt < 2.8
        if brushing: hr = (CX + 60 + math.sin(tt * 40) * 18, my + 10)
        o.update(hands=[hl, hr], mouth='grin' if brushing else 'smile', mo=0.7,
                 eyes='happy' if tt > 2.9 else 'normal', look=(0.6, 0.4))
        draw_char(img, CX, GY, o)
        put_rot(img, tube_spr(), hl[0], hl[1] - 60, 30 if 0.6 <= tt < 1.2 else 0); hand(img, hl)
        put_rot(img, brush_spr(), hr[0] - 10, hr[1] - 70, -70 if brushing else 0)
        if 0.9 <= tt < 1.4: put_sphere(img, PASTE, hr[0] - 10, hr[1] - 160, 22, 16, 0.6)
        hand(img, hr)
        if brushing:
            for k in range(3): put_sphere(img, FOAM, CX + 40 + k * 18, my + 12 + (k % 2) * 8, 18, 16, 0.4)
        if tt > 2.9: put_text(img, 'SHINY!', 560, 250, 90, (130, 220, 255), scale=back(seg(tt, 2.9, 3.1)), rot=-6)
    else:
        squeeze = sm(seg(tt, 0.6, 2.0))
        foam = sm(seg(tt, 2.0, 2.8))
        o.update(hands=[hl, hr], mouth='grin', eyes='crazy', brow='angry', look=(1, 0.5),
                 sx=1.0 + 0.05 * math.sin(tt * 30) * (0.5 <= tt < 2.0))
        draw_char(img, CX, GY, o)
        put_rot(img, scaled(tube_spr(), 1 - 0.4 * squeeze), hl[0], hl[1] - 60, 40 * (tt > 0.4)); hand(img, hl)
        if squeeze > 0.01:  # tüpten çıkan uzun macun şeridi: masaya, odaya dolanır
            d = ImageDraw.Draw(img)
            n = int(40 * squeeze) + 2
            pts = [(L(hl[0] + 60 + k * 18), L(hl[1] - 120 + 90 * math.sin(k * 0.6 + tt * 2))) for k in range(n)]
            d.line(pts, fill=PASTE, width=L(22), joint='curve')
            d.line(pts, fill=(140, 230, 230), width=L(6), joint='curve')
        if foam > 0.01:
            rnd = random.Random(5)
            for k in range(int(70 * foam)):
                x = rnd.uniform(-50, W + 50); y = rnd.uniform(GY - 420 * foam, GY + 80); s = rnd.uniform(50, 130)
                put_sphere(img, FOAM, x, y, s, s * 0.9, 0.3)
        if 2.0 <= tt < 3.0: put_text(img, 'FOAM PARTY!', 540, 230, 100, (130, 220, 255), scale=back(seg(tt, 2.0, 2.2)), rot=-6)
        if 2.0 <= tt < 2.3: shake = 12
        if tt > 3.2:  # köpükten kafası çıkar, köpük sakallı sırıtma
            info = draw_char(img, CX, GY, dict(o, eyes='happy'))
            for dx, dy in ((-40, 70), (0, 90), (40, 70), (-70, 50), (70, 50)):
                put_sphere(img, FOAM, CX + dx, info['my'] + dy - 20, 60, 50, 0.3)
    return shake


# ---------------------------------------------------------------- gag: sandviç
LAYERS = [(235, 195, 130), (120, 200, 90), (250, 210, 80), (230, 80, 70), (240, 160, 160)]
SAND = (840, TTOP - 8)


def stack(img, n, x=SAND[0], base=SAND[1], s=1.0):
    d = ImageDraw.Draw(img)
    put_sphere(img, (245, 245, 250), x, base + 4, 250 * s, 40 * s, 0.6)
    for k in range(n):
        c = LAYERS[0] if k in (0, n - 1) else LAYERS[1 + (k % 4)]
        y = base - 10 * s - k * 17 * s
        d.rounded_rectangle(box(x - 105 * s, y - 14 * s, x + 105 * s, y + 4 * s), radius=L(9 * s), fill=c)
        d.line(box(x - 100 * s, y - 13 * s, x + 100 * s, y - 13 * s), fill=lerpc(c, (255, 255, 255), 0.35), width=L(3))


def gag_sandwich(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    my = mouth_y(); hd = hand_default(1)
    if v == 'N':
        n = min(3, 1 + int(tt / 0.4)) if tt < 1.4 else 3
        if tt < 1.6:
            stack(img, n)
            hr = hd
        else:
            hr = lp((SAND[0], SAND[1] - 40), (CX + 120, my + 10), sm(seg(tt, 1.6, 2.0)))
            stack(img, 0)
        o.update(hands=[None, hr], mouth='open' if 2.0 <= tt < 2.2 else ('chew' if 2.2 <= tt < 2.7 else 'smile'),
                 mo=0.6, eyes='happy' if tt > 2.7 else 'normal', look=(1, 0.3))
        draw_char(img, CX, GY, o)
        if tt >= 1.6:
            stack(img, 3, hr[0] - 40, hr[1] - 10, 0.45)
            hand(img, hr)
    else:
        n = 3 + int(30 * sm(seg(tt, 0.2, 2.4)))
        eat = sm(seg(tt, 3.0, 3.5))
        puff = 1.4 * sm(seg(tt, 3.3, 3.6)) * (1 - sm(seg(tt, 4.1, 4.4)))
        o.update(mouth='open' if 2.9 <= tt < 3.5 else ('chew' if 3.5 <= tt < 4.1 else 'grin'), mo=1.0, eyes='crazy',
                 brow='angry', puff=puff, look=(1, -0.9) if tt < 2.9 else (0, 0))
        info = draw_char(img, CX, GY, o)
        if eat < 1:  # kule masadan ağzına uçar ve küçülür
            x = lerp(SAND[0], CX, eat); base = lerp(SAND[1], info['my'] + 40, eat)
            stack(img, n, x, base, 1 - 0.75 * eat)
        if 1.0 <= tt < 2.9: put_text(img, f'{n} LAYERS', 330, 260, 72, (255, 220, 120), rot=-6)
        if 4.0 <= tt < 4.8: put_text(img, 'ONE BITE.', 560, 260, 100, (255, 220, 120), scale=back(seg(tt, 4.0, 4.2)), rot=-6)
        if 2.2 <= tt < 2.9: shake = 4
    return shake


# ---------------------------------------------------------------- gag: hediye
GIFT = (235, 70, 90)
RIBBON = (255, 215, 80)
GIFTP = (845, TTOP)


def gift_box(img, cx, base, s, lid_dy=0.0, ribbon=True, col=GIFT):
    w, h = 190 * s, 150 * s
    put(img, cyl(col, w, h, 10 * s), cx, base - h / 2)
    d = ImageDraw.Draw(img)
    if ribbon:
        d.rectangle(box(cx - 14 * s, base - h, cx + 14 * s, base), fill=RIBBON)
    lid_y = base - h - 14 * s - lid_dy
    put(img, cyl(lerpc(col, (255, 255, 255), 0.15), w + 20 * s, 34 * s, 8 * s), cx, lid_y)
    if ribbon:
        d.rectangle(box(cx - 14 * s, lid_y - 17 * s, cx + 14 * s, lid_y + 17 * s), fill=RIBBON)
        for sgn in (-1, 1):
            put_rot(img, sphere(RIBBON, 60 * s, 34 * s, 0.6), cx + sgn * 28 * s, lid_y - 26 * s, sgn * 25)


def gag_gift(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    if v == 'N':
        lid = 160 * sm(seg(tt, 1.2, 1.8))
        gift_box(img, *GIFTP, 1.0, lid_dy=lid, ribbon=tt < 1.0)
        if tt >= 1.8:  # oyuncak ayı kutudan çıkar
            up = 80 * back(seg(tt, 1.8, 2.2))
            put_sphere(img, (200, 140, 90), GIFTP[0], GIFTP[1] - 150 - up + 40, 110, 100, 0.4)
            for sgn in (-1, 1): put_sphere(img, (200, 140, 90), GIFTP[0] + sgn * 40, GIFTP[1] - 190 - up + 40, 36, 36, 0.4)
        hr = lp(hand_default(1), (GIFTP[0] - 30, GIFTP[1] - 180), sm(seg(tt, 0.3, 0.8))) if tt < 1.9 else \
            lp((GIFTP[0] - 30, GIFTP[1] - 180), hand_default(1), sm(seg(tt, 1.9, 2.2)))
        o.update(hands=[None, hr], mouth='open' if tt > 2.0 else 'smile', mo=0.5, eyes='happy' if tt > 2.0 else 'normal', look=(1, -0.2))
        draw_char(img, CX, GY, o)
        if tt > 2.1: put_text(img, 'AWW!', 560, 260, 96, (255, 170, 190), scale=back(seg(tt, 2.1, 2.3)), rot=-6)
        confetti(img, 31, 2.0, tt, (GIFTP[0], GIFTP[1] - 200))
    else:
        rips = (1.0, 2.0, 3.0)
        level = sum(1 for r in rips if tt >= r)
        s = (1.0, 0.68, 0.45, 0.26)[level]
        jig = math.sin(tt * 50) * 6 if any(r - 0.5 <= tt < r for r in rips) else 0
        if tt < 3.8:
            gift_box(img, GIFTP[0] + jig, GIFTP[1], s, col=(GIFT, (90, 160, 240), (120, 210, 120), (240, 180, 60))[level])
        else:  # en içteki kutu açılır: tek bir şeker
            put_sphere(img, (255, 120, 200), GIFTP[0], GIFTP[1] - 20, 40, 30, 0.8)
        for k, r in enumerate(rips):
            particles(img, 40 + k, r, tt, 26, (GIFTP[0], GIFTP[1] - 120 * s), (-600, 600), (-900, -200), 1600,
                      [(GIFT, (90, 160, 240), (120, 210, 120))[k], RIBBON], (18, 34), life=1.3)
        hands = [(GIFTP[0] - 120 + jig, GIFTP[1] - 120 * s), (GIFTP[0] + 120 - jig, GIFTP[1] - 120 * s)] if 0.4 < tt < 3.8 else [None, None]
        reveal = tt >= 3.8
        o.update(hands=hands, mouth='flat' if 3.8 <= tt < 4.3 else 'grin', eyes='normal' if 3.8 <= tt < 4.3 else 'crazy',
                 brow=None if reveal else 'angry', look=(1, 0.2))
        draw_char(img, CX, GY, o)
        if 1.0 <= tt < 3.6:
            put_text(img, ('ANOTHER BOX?!', 'AGAIN?!', 'SERIOUSLY?!')[min(level - 1, 2)], 560, 230, 88, (255, 230, 120),
                     scale=back(seg(tt, rips[min(level - 1, 2)], rips[min(level - 1, 2)] + 0.2)), rot=-6, max_w=980)
        if reveal: put_text(img, '...ONE CANDY.', 560, 250, 92, (255, 170, 210), scale=back(seg(tt, 3.8, 4.0)), rot=-6, max_w=980)
        if any(r <= tt < r + 0.2 for r in rips): shake = 9
    return shake


GAGS = {
    'cookie': dict(title='EATING A COOKIE', name='Cookie', wall=(250, 215, 160), fn=gag_cookie,
                   N=[(0.5, 'pop'), (1.1, 'crunch'), (1.6, 'crunch'), (2.1, 'crunch'), (2.6, 'crunch'), (2.85, 'pop')],
                   P=[(0.0, 'sting')] + [(0.6 + i * 0.36, 'whoosh_s') for i in range(6)]
                     + [(0.92 + i * 0.36, 'gulp') for i in range(6)] + [(3.0, 'burp')]),
    'alarm': dict(title='ALARM CLOCK', name='Alarm Clock', wall=(185, 212, 240), fn=gag_alarm,
                  N=[(0.0, 'ring', 1.2), (1.2, 'click'), (1.4, 'yawn'), (2.3, 'pop')],
                  P=[(0.0, 'ring', 1.5), (0.4, 'sting'), (0.6, 'whoosh'), (1.35, 'whoosh_s'), (1.5, 'smash'),
                     (1.7, 'boing'), (2.35, 'ring_weak'), (2.95, 'whoosh_s'), (3.05, 'bonk')]),
    'ketchup': dict(title='KETCHUP', name='Ketchup', wall=(205, 235, 190), fn=gag_ketchup,
                    N=[(0.5, 'pop'), (1.15, 'squirt'), (1.5, 'squirt'), (1.85, 'squirt'), (2.7, 'pop')],
                    P=[(0.0, 'sting'), (1.1, 'slurp', 1.9), (3.0, 'whoosh'), (3.3, 'ahh')]),
    'cake': dict(title='BIRTHDAY CAKE', name='Birthday Cake', wall=(245, 205, 225), fn=gag_cake,
                 N=[(0.9, 'blow', 0.6), (1.7, 'pop'), (1.7, 'horn'), (2.1, 'clap'), (2.4, 'clap'), (2.7, 'clap')],
                 P=[(0.0, 'sting'), (0.1, 'inhale', 1.5), (1.6, 'blow', 0.5), (1.65, 'whoosh'), (2.1, 'splat')]),
    'soda': dict(title='OPENING A SODA', name='Soda', wall=(200, 225, 250), fn=gag_soda,
                 N=[(0.5, 'pop'), (1.0, 'psst'), (1.1, 'slurp', 0.9), (2.1, 'ahh')],
                 P=[(0.0, 'sting'), (0.8, 'rattle', 0.9), (1.72, 'psst'), (1.72, 'fizz', 1.6), (3.4, 'pop')]),
    'icecream': dict(title='ICE CREAM', name='Ice Cream', wall=(255, 230, 200), fn=gag_icecream,
                     N=[(0.6, 'lick'), (1.3, 'lick'), (2.0, 'lick'), (2.3, 'pop')],
                     P=[(0.0, 'sting'), (0.55, 'crunch'), (0.75, 'gulp'), (1.3, 'freeze'), (3.25, 'crunch'), (3.6, 'gulp')]),
    'balloon': dict(title='BLOWING A BALLOON', name='Balloon', wall=(215, 240, 235), fn=gag_balloon,
                    N=[(0.2, 'blow', 0.4), (0.8, 'blow', 0.4), (1.4, 'blow', 0.4), (1.9, 'boing'), (2.4, 'pop')],
                    P=[(0.0, 'sting'), (0.2, 'blow', 2.4), (2.65, 'bang'), (3.3, 'boing')]),
    'pumpkin': dict(title='HALLOWEEN PUMPKIN', name='Pumpkin', wall=(120, 95, 150), fn=gag_pumpkin, months=(9, 10),
                    N=[(1.2, 'carve'), (1.6, 'carve'), (2.0, 'carve'), (2.4, 'ding')],
                    P=[(0.0, 'sting'), (0.4, 'whoosh'), (1.15, 'whoosh_s'), (1.3, 'smash'), (2.4, 'boing')]),
}

GAGS.update({
    'coffee': dict(title='MORNING COFFEE', name='Coffee', wall=(240, 222, 200), fn=gag_coffee,
                   N=[(0.5, 'pop'), (1.0, 'slurp', 1.0), (2.1, 'ahh')],
                   P=[(0.0, 'sting'), (1.0, 'slurp', 1.4), (2.4, 'whoosh'), (3.3, 'whoosh'), (3.7, 'whoosh'), (4.2, 'boing')]),
    'gum': dict(title='BUBBLE GUM', name='Bubble Gum', wall=(232, 218, 246), fn=gag_gum,
                N=[(0.2, 'crunch'), (1.0, 'blow', 1.2), (2.3, 'pop')],
                P=[(0.0, 'sting'), (0.8, 'blow', 2.2), (2.4, 'boing'), (3.9, 'bang'), (4.3, 'boing')]),
    'popcorn': dict(title='POPCORN', name='Popcorn', wall=(250, 232, 195), fn=gag_popcorn,
                    N=[(0.6, 'crunch'), (1.5, 'crunch'), (2.4, 'crunch')],
                    P=[(0.0, 'sting'), (1.0, 'bang')] + [(1.05 + i * 0.13, 'pop') for i in range(18)]),
    'toothpaste': dict(title='BRUSHING TEETH', name='Toothpaste', wall=(205, 236, 242), fn=gag_toothpaste,
                       N=[(0.9, 'squirt'), (1.4, 'rattle', 1.4), (2.9, 'ding')],
                       P=[(0.0, 'sting'), (0.6, 'squirt'), (1.2, 'squirt'), (2.0, 'splat'), (2.1, 'fizz', 1.5)]),
    'sandwich': dict(title='MAKING A SANDWICH', name='Sandwich', wall=(236, 226, 205), fn=gag_sandwich,
                     N=[(0.4, 'pop'), (0.8, 'pop'), (1.2, 'pop'), (2.0, 'crunch'), (2.3, 'crunch')],
                     P=[(0.0, 'sting')] + [(0.2 + i * 0.08, 'pop') for i in range(27)] + [(3.0, 'whoosh'), (3.5, 'gulp'), (4.0, 'burp')]),
    'gift': dict(title='OPENING A GIFT', name='Gift', wall=(215, 230, 250), fn=gag_gift,
                 N=[(0.8, 'rattle', 0.4), (1.2, 'whoosh'), (1.8, 'pop'), (2.0, 'horn')],
                 P=[(0.0, 'sting'), (1.0, 'bang'), (2.0, 'bang'), (3.0, 'bang'), (3.8, 'ding')]),
})


# ================================================================ 2026-10-10 yeni gag'ler (20'ye çıkış)
def tri(img, pts, fill):
    ImageDraw.Draw(img).polygon([(L(x), L(y)) for x, y in pts], fill=fill, outline=DARK)


# ---------------------------------------------------------------- gag: pizza
CRUST, CHEESE, PEPP = (225, 160, 80), (250, 205, 90), (200, 50, 45)
PIZ = (835, TTOP - 22)


def draw_pizza(img, cx, cy, w, fold=0.0, missing=0):
    """fold 0 → düz pizza, 1 → taco gibi ikiye katlanmış (yarım ay)."""
    h = 70 * (1 - fold) + 150 * fold
    if fold < 0.5:
        put_sphere(img, CRUST, cx, cy, w, h, 0.3)
        put_sphere(img, CHEESE, cx, cy - 6, w - 30, h - 22, 0.2)
        for k, (dx, dy) in enumerate(((-70, -6), (0, -14), (70, -4), (-30, 10), (40, 12))):
            if k >= missing: put_sphere(img, PEPP, cx + dx * w / 260, cy + dy, 34, 14, 0.4)
        if missing:
            tri(img, [(cx, cy - 6), (cx + w / 2 - 6, cy - 14), (cx + w / 2 - 6, cy + 16)], (40, 30, 50))
    else:
        d = ImageDraw.Draw(img)
        d.chord(box(cx - w / 2, cy - h, cx + w / 2, cy + h * 0.2), 180, 360, fill=CRUST, outline=DARK, width=L(4))
        d.chord(box(cx - w / 2 + 16, cy - h + 18, cx + w / 2 - 16, cy + h * 0.2 - 6), 180, 360, fill=CHEESE)
        for dx in (-60, 0, 60): put_sphere(img, PEPP, cx + dx * w / 260, cy - h * 0.45, 30, 22, 0.4)


def gag_pizza(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1); my = mouth_y()
    if v == 'N':
        took = tt >= 0.7
        draw_pizza(img, *PIZ, 260, missing=1 if took else 0)
        if tt < 0.7: hr = lp(hd, (PIZ[0] + 60, PIZ[1] - 10), sm(seg(tt, 0.2, 0.7)))
        elif tt < 1.1: hr = lp((PIZ[0] + 60, PIZ[1] - 10), (CX + 120, my), sm(seg(tt, 0.7, 1.1)))
        elif tt < 2.4: hr = (CX + 120, my)
        else: hr = lp((CX + 120, my), hd, sm(seg(tt, 2.4, 2.8)))
        bites = int(clamp((tt - 1.2) / 0.4, 0, 3)) if tt > 1.2 else 0
        o.update(hands=[None, hr], mouth='chew' if 1.2 <= tt < 2.4 else 'smile',
                 eyes='happy' if tt > 2.4 else 'normal', look=(1, 0.2))
        draw_char(img, CX, GY, o)
        if took and tt < 2.4 and bites < 3:
            s = 1 - bites * 0.3
            tri(img, [(hr[0] - 10, hr[1] - 30), (hr[0] + 90 * s, hr[1] - 50), (hr[0] + 90 * s, hr[1] - 6)], CHEESE)
        hand(img, hr)
        if 1.3 <= tt < 2.3: put_text(img, 'mmm', CX + 160, 330, 60, CRUST, scale=back(seg(tt, 1.3, 1.5)), rot=-6)
    else:
        fold = sm(seg(tt, 0.9, 1.5))
        lift = sm(seg(tt, 0.3, 0.9))
        pc = lp(PIZ, (CX + 30, my - 40), sm(seg(tt, 1.5, 2.1)))
        if tt < 0.3: pc = PIZ
        eaten = sm(seg(tt, 2.2, 3.2))
        hands = [None, None] if tt < 0.3 else [(pc[0] - 130, pc[1] + 10), (pc[0] + 130, pc[1] + 10)]
        o.update(hands=hands, mouth='open' if 1.9 <= tt < 3.2 else ('grin' if tt >= 3.2 else 'smile'), mo=1.0,
                 eyes='crazy', brow='angry' if tt < 3.2 else None, look=(1, 0) if tt < 1.5 else (0, 0.4),
                 puff=sm(seg(tt, 2.4, 3.0)) * (1 - sm(seg(tt, 3.6, 4.2))))
        draw_char(img, CX, GY, o)
        if eaten < 0.98:
            draw_pizza(img, pc[0], pc[1] - lift * 20, 260 * (1 - eaten * 0.9), fold=fold)
            for h_ in hands:
                if h_: hand(img, h_)
        if 1.0 <= tt < 2.3: put_text(img, 'PIZZA TACO!', 600, 200, 110, CHEESE, scale=back(seg(tt, 1.0, 1.2)), rot=-7, max_w=980)
        if 3.4 <= tt < 4.8: put_text(img, 'ONE BITE.', 620, 220, 110, (255, 255, 255), scale=back(seg(tt, 3.4, 3.6)), rot=6)
        if 3.2 <= tt < 3.45: shake = 12
    return shake


# ---------------------------------------------------------------- gag: telefon şarjı
PHONE = (850, TTOP - 95)


def draw_phone(img, cx, cy, pct, col_bar=None, plugged=False):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box(cx - 52, cy - 92, cx + 52, cy + 92), radius=L(18), fill=(30, 30, 40), outline=DARK, width=L(4))
    d.rounded_rectangle(box(cx - 42, cy - 80, cx + 42, cy + 80), radius=L(10), fill=(60, 70, 100))
    d.rounded_rectangle(box(cx - 26, cy - 40, cx + 26, cy + 50), radius=L(6), outline=(255, 255, 255), width=L(4))
    d.rectangle(box(cx - 10, cy - 50, cx + 10, cy - 40), fill=(255, 255, 255))
    f = clamp(pct / 100)
    col = col_bar or ((230, 60, 60) if pct < 20 else (90, 210, 110))
    if f > 0: d.rectangle(box(cx - 20, cy + 44 - 82 * f, cx + 20, cy + 44), fill=col)
    if plugged:
        d.line(box(cx, cy + 92, cx, TTOP + 10), fill=(240, 240, 240), width=L(8))
        d.line(box(cx, TTOP + 10, TX1 + 40, TTOP + 10), fill=(240, 240, 240), width=L(8))


def gag_phone(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1)
    if v == 'N':
        plugged = tt >= 1.0
        pct = 3 + (8 * sm(seg(tt, 1.2, 3.0)) if plugged else 0)
        draw_phone(img, *PHONE, pct, plugged=plugged)
        hr = lp(hd, (PHONE[0], PHONE[1] + 110), sm(seg(tt, 0.4, 0.9))) if tt < 1.0 else lp((PHONE[0], PHONE[1] + 110), hd, sm(seg(tt, 1.0, 1.4)))
        o.update(hands=[None, hr], mouth='smile', eyes='happy' if tt > 1.6 else 'normal', look=(1, -0.1))
        draw_char(img, CX, GY, o); hand(img, hr)
        put_text(img, f'{int(pct)}%', PHONE[0], PHONE[1] - 150, 60, (230, 60, 60) if pct < 20 else (90, 210, 110))
        if 1.6 <= tt < 3.2: put_text(img, 'charging...', 560, 300, 54, (255, 255, 255), scale=back(seg(tt, 1.6, 1.8)), rot=-4)
    else:
        pct = 99 if tt < 3.2 else 100
        draw_phone(img, *PHONE, pct, plugged=True)
        lean = sm(seg(tt, 0.2, 0.8)) * 120 * (1 - sm(seg(tt, 3.2, 3.4)))
        jump = 260 * math.sin(math.pi * clamp((tt - 3.3) / 0.7)) if 3.3 <= tt < 4.0 else 0
        o.update(mouth='flat' if tt < 3.2 else 'open', mo=1.0, eyes='crazy', brow='angry' if tt < 3.2 else None,
                 look=(1, -0.3), eye_s=1.0 + 0.25 * sm(seg(tt, 0.8, 3.0)),
                 hands=[(CX + lean - 190, GY - 420), (CX + lean + 190, GY - 420)] if tt >= 3.3 else [None, None])
        draw_char(img, CX + lean, GY - jump, o)
        put_text(img, f'{pct}%', PHONE[0], PHONE[1] - 150, 66 if tt < 3.2 else 90, (90, 210, 110),
                 scale=1.0 + (0.3 * math.sin(tt * 30) if tt >= 3.2 else 0))
        if 1.0 <= tt < 3.2:
            dots = '.' * (1 + int((tt - 1.0) / 0.5) % 3)
            put_text(img, 'WAITING' + dots, 560, 250, 70, (255, 255, 255))
        if tt >= 3.2:
            confetti(img, 31, 3.2, tt, (PHONE[0], PHONE[1] - 120))
            put_text(img, '100%!!!', 560, 230, 140, (255, 230, 60), scale=back(seg(tt, 3.2, 3.4)), rot=-8)
            if tt < 3.5: shake = 14
    return shake


# ---------------------------------------------------------------- gag: bitki sulama
POT = (860, TTOP - 50)
LEAF = (70, 170, 80)


def draw_plant(img, size, flower=0.0):
    put(img, cyl((200, 100, 60), 120, 100, 14), POT[0], POT[1] + 30)
    d = ImageDraw.Draw(img)
    top = POT[1] - 20 - 120 * size
    d.line(box(POT[0], POT[1] - 10, POT[0], top), fill=(60, 140, 60), width=L(10 + 8 * min(size, 3)))
    n = 2 + int(size * 3)
    for k in range(n):
        y = POT[1] - 30 - (POT[1] - 30 - top) * (k + 1) / (n + 1)
        s = -1 if k % 2 else 1
        put_rot(img, sphere(LEAF, 90 + 20 * min(size, 3), 40 + 8 * min(size, 3), 0.4), POT[0] + s * (50 + 10 * min(size, 3)), y, s * 25)
    if flower > 0:
        fs = 40 + 70 * flower * min(size, 2.5)
        for a in range(0, 360, 60):
            px, py = rotv(0, -fs * 0.6, a)
            put_sphere(img, (255, 120, 170), POT[0] + px, top + py, fs * 0.7, fs * 0.7, 0.4)
        put_sphere(img, (255, 215, 60), POT[0], top, fs * 0.6, fs * 0.6, 0.5)
    return top


def gag_plant(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1)
    if v == 'N':
        grow = sm(seg(tt, 1.6, 2.6))
        draw_plant(img, 0.5 + 0.3 * grow, flower=sm(seg(tt, 2.3, 2.8)))
        can = lp((CX + 200, GY - 220), (POT[0] - 110, POT[1] - 170), sm(seg(tt, 0.2, 0.8))) if tt < 2.2 else lp((POT[0] - 110, POT[1] - 170), (CX + 200, GY - 220), sm(seg(tt, 2.2, 2.6)))
        ang = 35 * sm(seg(tt, 0.8, 1.0)) * (1 - sm(seg(tt, 1.9, 2.1)))
        put_rot(img, cyl((90, 160, 220), 110, 90, 16), can[0], can[1], ang)
        if 0.9 <= tt < 2.0:
            particles(img, 41, 0.9, tt, 16, (can[0] + 70, can[1] + 20), (20, 80), (0, 150), 1600, [(120, 190, 255)], (10, 16), life=0.5, emit=1.0)
        o.update(hands=[None, (can[0] - 40, can[1] + 20)], mouth='smile', eyes='happy' if tt > 2.6 else 'normal', look=(1, 0))
        draw_char(img, CX, GY, o); hand(img, (can[0] - 40, can[1] + 20))
    else:
        grow = sm(seg(tt, 1.8, 3.6))
        top = draw_plant(img, 0.5 + 4.5 * grow, flower=sm(seg(tt, 3.2, 3.8)))
        bk = (POT[0] - 160, POT[1] - 230)
        ang = 110 * sm(seg(tt, 0.7, 1.1))
        if tt < 2.0:
            put_rot(img, cyl((150, 150, 165), 170, 150, 10), bk[0], bk[1], ang)
        if 0.9 <= tt < 2.0:
            particles(img, 42, 0.9, tt, 90, (bk[0] + 60, bk[1] + 30), (40, 300), (-200, 200), 1800, [(110, 180, 255), (170, 215, 255)], (18, 36), life=0.7, emit=0.9)
        flood = sm(seg(tt, 1.0, 1.8)) * (1 - sm(seg(tt, 2.8, 3.6)))
        if flood > 0.01: put_sphere(img, (110, 180, 255), 560, GY + 6, 1000 * flood, 70 * flood, 0.6)
        o.update(hands=[None, (bk[0] - 70, bk[1] + 40)] if tt < 2.0 else [None, None], mouth='grin' if tt < 3.0 else 'open',
                 mo=1.0, eyes='crazy', brow='angry' if tt < 1.8 else None, look=(1, -0.8) if tt > 2.0 else (1, 0))
        draw_char(img, CX, GY, o)
        if tt < 2.0: hand(img, (bk[0] - 70, bk[1] + 40))
        if 0.9 <= tt < 1.9: put_text(img, 'EXTRA WATER!', 600, 160, 96, (110, 180, 255), scale=back(seg(tt, 0.9, 1.1)), rot=-6, max_w=980)
        if 3.3 <= tt: put_text(img, 'JUNGLE MODE', 520, 240, 110, LEAF, scale=back(seg(tt, 3.3, 3.5)), rot=7, max_w=900)
        if 1.8 <= tt < 3.6: shake = 4
    return shake


# ---------------------------------------------------------------- gag: cips
BAG = (845, TTOP - 90)
CHIP = [(245, 200, 90), (235, 185, 70), (250, 215, 120)]


def draw_bag(img, cx, cy, ang=0.0, s=1.0):
    spr = Image.new('RGBA', (L(200 * s), L(240 * s)), (0, 0, 0, 0))
    d = ImageDraw.Draw(spr)
    d.rounded_rectangle([L(10 * s), L(10 * s), L(190 * s), L(230 * s)], radius=L(20 * s), fill=(220, 50, 60), outline=DARK, width=L(4))
    d.rectangle([L(10 * s), L(10 * s), L(190 * s), L(40 * s)], fill=(190, 35, 45))
    d.ellipse([L(50 * s), L(80 * s), L(150 * s), L(170 * s)], fill=CHIP[0], outline=DARK, width=L(3))
    put_rot(img, spr, cx, cy, ang)


def gag_chips(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1); my = mouth_y()
    if v == 'N':
        draw_bag(img, *BAG)
        if tt < 0.7: hr = lp(hd, (BAG[0], BAG[1] - 90), sm(seg(tt, 0.2, 0.7)))
        elif tt < 1.1: hr = lp((BAG[0], BAG[1] - 90), (CX + 110, my), sm(seg(tt, 0.7, 1.1)))
        else: hr = lp((CX + 110, my), hd, sm(seg(tt, 1.3, 1.7)))
        o.update(hands=[None, hr], mouth='chew' if 1.2 <= tt < 2.6 else 'smile', eyes='happy' if tt > 2.6 else 'normal', look=(1, 0))
        draw_char(img, CX, GY, o)
        if 0.7 <= tt < 1.2: put_sphere(img, CHIP[0], hr[0] - 20, hr[1] - 30, 46, 34, 0.3)
        hand(img, hr)
        if 1.2 <= tt < 2.2: put_text(img, 'crunch', CX + 170, 330, 54, CHIP[1], scale=back(seg(tt, 1.2, 1.4)), rot=-5)
    else:
        bp = lp(BAG, (CX + 40, my - 330), sm(seg(tt, 0.4, 1.0))) if tt >= 0.4 else BAG
        ang = 160 * sm(seg(tt, 0.9, 1.3))
        o.update(mouth='open' if 1.2 <= tt < 3.0 else 'chew' if tt < 3.8 else 'grin', mo=1.0, eyes='crazy', brow='angry',
                 look=(0, -0.9) if tt > 1.0 else (1, 0), puff=sm(seg(tt, 2.4, 3.0)) * (1 - sm(seg(tt, 3.8, 4.4))),
                 hands=[(bp[0] - 110, bp[1] + 30), (bp[0] + 110, bp[1] + 30)] if tt >= 0.4 else [None, None])
        info = draw_char(img, CX, GY, o)
        particles(img, 51, 1.2, tt, 80, (bp[0] - 10, bp[1] + 90), (-120, 120), (100, 300), 1500, CHIP, (24, 40), life=0.6, emit=1.7)
        crumbs = sm(seg(tt, 1.6, 3.0))
        for k in range(int(26 * crumbs)):
            r_ = random.Random(k); put_sphere(img, r_.choice(CHIP), CX + r_.uniform(-330, 420), GY + r_.uniform(-10, 30), 30, 14, 0.2)
        draw_bag(img, bp[0], bp[1], ang)
        if tt >= 0.4:
            hand(img, (bp[0] - 110, bp[1] + 30)); hand(img, (bp[0] + 110, bp[1] + 30))
        if 2.9 <= tt < 4.0: put_text(img, 'CRUNCH!!!', 620, 260, 130, CHIP[1], scale=back(seg(tt, 2.9, 3.1)), rot=-7)
        if 2.9 <= tt < 3.9: shake = 6 + 6 * math.sin(tt * 40)
    return shake


# ---------------------------------------------------------------- gag: limon
LEMON = (255, 225, 50)
GLASSP = (850, TTOP - 75)


def gag_lemon(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1); my = mouth_y()
    if v == 'N':
        gp = lp(GLASSP, (CX + 140, my - 10), sm(seg(tt, 0.5, 1.0))) if tt < 2.2 else lp((CX + 140, my - 10), GLASSP, sm(seg(tt, 2.2, 2.7)))
        put(img, cyl((255, 245, 170), 90, 140, 10), *gp)
        put_sphere(img, LEMON, gp[0] + 30, gp[1] - 70, 50, 30, 0.4)
        hr = lp(hd, (GLASSP[0] - 50, GLASSP[1]), sm(seg(tt, 0.1, 0.5))) if tt < 0.5 else ((gp[0] - 50, gp[1]) if tt < 2.7 else lp((GLASSP[0] - 50, GLASSP[1]), hd, sm(seg(tt, 2.7, 3.1))))
        o.update(hands=[None, hr], mouth='o' if 1.0 <= tt < 2.0 else 'smile', eyes='happy' if 1.0 <= tt < 2.0 or tt > 2.6 else 'normal', look=(1, 0))
        draw_char(img, CX, GY, o); hand(img, hr)
        if 2.0 <= tt < 3.0: put_text(img, 'AHH~', CX + 60, 300, 70, LEMON, scale=back(seg(tt, 2.0, 2.2)), rot=-6)
    else:
        lp_ = lp((GLASSP[0], TTOP - 40), (CX + 90, my), sm(seg(tt, 0.3, 0.8)))
        bitten = tt >= 1.0
        sour = sm(seg(tt, 1.0, 1.3)) * (1 - sm(seg(tt, 3.2, 3.6)))
        o.update(hands=[None, lp_] if tt < 1.3 else [None, None], mouth='flat' if 1.0 <= tt < 3.2 else ('grin' if tt >= 3.2 else 'open'),
                 mo=1.0, eyes='happy' if 1.0 <= tt < 3.2 else 'crazy', brow='angry' if tt < 1.0 else None,
                 sx=1.0 - 0.25 * sour, sy=1.0 + 0.12 * sour, color=lerpc(CHAR['color'], LEMON, 0.55 * sour), look=(1, 0))
        draw_char(img, CX, GY, o)
        if tt < 1.3:
            put_sphere(img, LEMON, lp_[0] + 30, lp_[1] - 10, 120 if not bitten else 90, 90, 0.5); hand(img, lp_)
        if 1.1 <= tt < 3.0: put_text(img, 'SOUR!!!', 620, 200, 150, LEMON, scale=1.0 + 0.08 * math.sin(tt * 40), rot=-8)
        if 3.4 <= tt: put_text(img, '...ANOTHER ONE.', 600, 260, 84, (255, 255, 255), scale=back(seg(tt, 3.4, 3.6)), rot=5, max_w=950)
        if 1.0 <= tt < 3.0: shake = 7
    return shake


# ---------------------------------------------------------------- gag: donut
DONUT, ICING = (215, 150, 80), (255, 140, 190)
DPLATE = (850, TTOP - 30)


def draw_donut(img, cx, cy, s=1.0, bite=0.0):
    put_sphere(img, DONUT, cx, cy, 130 * s, 90 * s, 0.4)
    put_sphere(img, ICING, cx, cy - 6 * s, 112 * s, 72 * s, 0.6)
    put_sphere(img, (40, 30, 50), cx, cy - 4 * s, 36 * s, 24 * s, 0.0)
    for k, (dx, dy) in enumerate(((-30, -20), (20, -26), (34, 4), (-36, 8), (4, 22))):
        put_sphere(img, [(255, 255, 255), (120, 200, 255), (255, 220, 60)][k % 3], cx + dx * s, cy + dy * s, 14 * s, 6 * s, 0.2)


def gag_donut(img, v, t, gt):
    tt = max(t, 0.0); shake = 0.0; o = dict(t=gt)
    hd = hand_default(1); my = mouth_y()
    if v == 'N':
        put_sphere(img, (245, 245, 250), DPLATE[0], DPLATE[1] + 22, 230, 40, 0.5)
        dp = lp(DPLATE, (CX + 140, my), sm(seg(tt, 0.5, 1.0))) if tt < 2.2 else (CX + 140, my)
        s = 1.0 - 0.35 * (tt >= 1.4) - 0.35 * (tt >= 1.9)
        hr = lp(hd, DPLATE, sm(seg(tt, 0.1, 0.5))) if tt < 0.5 else ((dp[0] + 30, dp[1] + 20) if tt < 2.3 else lp((dp[0] + 30, dp[1] + 20), hd, sm(seg(tt, 2.3, 2.7))))
        o.update(hands=[None, hr], mouth='chew' if 1.3 <= tt < 2.6 else 'smile', eyes='happy' if tt > 2.6 else 'normal', look=(1, 0))
        draw_char(img, CX, GY, o)
        if tt < 2.3: draw_donut(img, dp[0], dp[1], s * 0.8)
        hand(img, hr)
    else:
        on = sm(seg(tt, 0.4, 1.2))
        info_y = GY - 26 - R - 28
        eyes_c = [(CX - 50, info_y), (CX + 50, info_y)]
        o.update(mouth='grin' if tt < 2.6 else ('open' if tt < 3.4 else 'chew'), mo=1.0, eyes='crazy', brow='angry' if tt < 2.6 else None,
                 look=(0, 0), hands=[(CX - 175, info_y + 20), (CX + 175, info_y + 20)] if 0.4 <= tt < 2.6 else [None, None])
        draw_char(img, CX, GY, o)
        if tt < 2.6:
            for k, e in enumerate(eyes_c):
                src = (DPLATE[0] - 40 + 80 * k, DPLATE[1])
                p = lp(src, e, on)
                draw_donut(img, p[0], p[1], 0.85)
            if tt >= 0.4:
                hand(img, (CX - 175, info_y + 20)); hand(img, (CX + 175, info_y + 20))
        elif tt < 3.2:
            k = sm(seg(tt, 2.6, 3.2))
            for e in eyes_c:
                p = lp(e, (CX, mouth_y() + 10), k); draw_donut(img, p[0], p[1], 0.85 * (1 - k))
        if 1.2 <= tt < 2.6: put_text(img, 'DONUT GLASSES', 600, 200, 100, ICING, scale=back(seg(tt, 1.2, 1.4)), rot=-6, max_w=960)
        if 3.4 <= tt: put_text(img, 'BREAKFAST.', 620, 240, 110, (255, 255, 255), scale=back(seg(tt, 3.4, 3.6)), rot=6)
        if 2.6 <= tt < 2.9: shake = 9
    return shake


GAGS.update({
    'pizza': dict(title='EATING PIZZA', name='Pizza', wall=(250, 225, 205), fn=gag_pizza,
                  N=[(0.7, 'pop'), (1.2, 'crunch'), (1.6, 'crunch'), (2.0, 'crunch')],
                  P=[(0.0, 'sting'), (1.0, 'whoosh'), (2.2, 'gulp'), (2.6, 'gulp'), (3.2, 'burp')]),
    'phone': dict(title='CHARGING PHONE', name='Phone', wall=(215, 225, 240), fn=gag_phone,
                  N=[(0.9, 'click'), (1.6, 'ding')],
                  P=[(0.0, 'sting'), (1.0, 'rattle', 2.0), (3.2, 'ding'), (3.25, 'horn'), (3.3, 'clap')]),
    'plant': dict(title='WATERING A PLANT', name='Plant', wall=(220, 238, 215), fn=gag_plant,
                  N=[(0.9, 'fizz', 1.0), (2.3, 'pop'), (2.4, 'ding')],
                  P=[(0.0, 'sting'), (0.9, 'splat'), (0.95, 'fizz', 1.0), (1.8, 'boing'), (2.6, 'boing'), (3.3, 'ding')]),
    'chips': dict(title='EATING CHIPS', name='Chips', wall=(245, 228, 200), fn=gag_chips,
                  N=[(0.6, 'rattle', 0.3), (1.2, 'crunch'), (1.6, 'crunch'), (2.0, 'crunch')],
                  P=[(0.0, 'sting'), (0.5, 'rattle', 0.6), (1.2, 'whoosh')] + [(2.9 + i * 0.12, 'crunch') for i in range(8)]),
    'lemon': dict(title='LEMONADE', name='Lemon', wall=(250, 245, 205), fn=gag_lemon,
                  N=[(1.0, 'slurp', 1.0), (2.0, 'ahh')],
                  P=[(0.0, 'sting'), (1.0, 'crunch'), (1.1, 'freeze'), (3.4, 'boing')]),
    'donut': dict(title='DONUT BREAKFAST', name='Donut', wall=(250, 220, 235), fn=gag_donut,
                  N=[(0.5, 'pop'), (1.4, 'crunch'), (1.9, 'crunch')],
                  P=[(0.0, 'sting'), (0.5, 'whoosh'), (1.2, 'boing'), (2.6, 'gulp'), (3.0, 'gulp'), (3.4, 'burp')]),
})


def total(plan=None):
    return INTRO + GAG * len((plan or PLAN)['gags']) + OUTRO


# ---------------------------------------------------------------- kare
def finish_panel(p, shake, gt, dim):
    z = 1.15; cx, cy = L(560), L(470)
    dx = math.sin(gt * 90) * shake * S if shake > 0.5 else 0.0
    dy = math.cos(gt * 77) * shake * S if shake > 0.5 else 0.0
    p = p.transform(p.size, Image.AFFINE, (1 / z, 0, cx - p.width / 2 / z + dx, 0, 1 / z, cy - p.height / 2 / z + dy), resample=Image.BILINEAR)
    p = p.convert('RGB').reduce(S)
    if dim: p = ImageEnhance.Brightness(p).enhance(0.55)
    return p


def outro_panel(v, gt):
    img = bg(GAGS[PLAN['gags'][0]]['wall'], v)
    if v == 'N':
        cy = GY - 26 - R
        draw_char(img, CX, GY, dict(t=gt, eyes='happy', mouth='open', mo=0.5,
                                    hands=[None, (CX + R + 40 + math.sin(gt * 12) * 25, cy - 40)]))
    else:
        draw_char(img, CX, GY, dict(t=gt, eyes='crazy', brow='angry', mouth='grin', look=(-0.2, 0.3)))
        put_rot(img, hammer_spr(300), HPIV[0], HPIV[1], 25 + math.sin(gt * 2) * 3)
        hand(img, HPIV)
    return img


def render_frame(i):
    T = i / FPS
    gags = [GAGS[k] for k in PLAN['gags']]
    A, B, Q = FORMATS[PLAN['format']]
    frame = Image.new('RGB', (W, H), (24, 20, 38))
    if T < INTRO:
        title = f'{A} VS {B}'; tstart = 0.0; g = gags[0]
        for v, y in (('N', TOP), ('P', TOP + PH)):
            img = bg(g['wall'], v); g['fn'](img, v, -1, T); frame.paste(finish_panel(img, 0, T, False), (0, y))
    elif T < INTRO + GAG * len(gags):
        k = int((T - INTRO) // GAG); gl = T - INTRO - k * GAG; g = gags[k]
        title = g['title']; tstart = INTRO + k * GAG
        img = bg(g['wall'], 'N'); sn = g['fn'](img, 'N', min(gl, NDUR), T)
        frame.paste(finish_panel(img, sn if gl < NDUR else 0, T, gl >= NDUR), (0, TOP))
        img = bg(g['wall'], 'P'); sp = g['fn'](img, 'P', gl - NDUR, T)
        frame.paste(finish_panel(img, sp, T, gl < NDUR), (0, TOP + PH))
    else:
        title = Q; tstart = INTRO + GAG * len(gags)
        frame.paste(finish_panel(outro_panel('N', T), 0, T, False), (0, TOP))
        frame.paste(finish_panel(outro_panel('P', T), 0, T, False), (0, TOP + PH))
    d = ImageDraw.Draw(frame)
    put_text_px(frame, title, W // 2, TOP // 2 + 4, 76, (255, 255, 255), scale=back(seg(T, tstart, tstart + 0.25)), max_w=1030)
    for y0, txt, c in ((TOP, f'1. {A}', (60, 190, 90)), (TOP + PH, f'2. {B}', (225, 50, 60))):
        spr = text_spr(txt, 44, (255, 255, 255))
        d.rounded_rectangle([22, y0 + 22, 22 + spr.width + 28, y0 + 22 + spr.height + 20], radius=16, fill=c, outline=DARK, width=4)
        frame.paste(spr, (36, y0 + 32), spr)
    d.rectangle([0, TOP + PH - 5, W, TOP + PH + 5], fill=DARK)
    d.ellipse([W // 2 - 56, TOP + PH - 56, W // 2 + 56, TOP + PH + 56], fill=(255, 210, 50), outline=DARK, width=6)
    put_text_px(frame, 'VS', W // 2, TOP + PH + 2, 54, (255, 255, 255))
    if T < INTRO:
        put_text_px(frame, A, W // 2, TOP + 300, 130, (120, 235, 130), scale=back(seg(T, 0.0, 0.25)), rot=-5, max_w=1000)
        put_text_px(frame, B, W // 2, TOP + PH + 300, 130, (255, 90, 90), scale=back(seg(T, 0.45, 0.7)), rot=5, max_w=1000)
    elif T >= INTRO + GAG * len(gags):
        tt = T - (INTRO + GAG * len(gags)); s = back(seg(tt, 0.1, 0.4)) * (1 + 0.05 * math.sin(tt * 8))
        put_text_px(frame, 'COMMENT', W // 2, TOP + PH - 180, 110, (255, 230, 60), scale=s, rot=-4)
        put_text_px(frame, '1 OR 2!', W // 2, TOP + PH + 170, 130, (255, 255, 255), scale=s, rot=4)
    return frame


def _frame_bytes(i): return render_frame(i).tobytes()


# ---------------------------------------------------------------- ses
rng = np.random.default_rng(1)
def t_arr(d): return np.arange(int(SR * d)) / SR
def noise(d): return rng.uniform(-1, 1, int(SR * d))
def dec(d, k): return np.exp(-t_arr(d) * k)
def lpf(x, k): return np.convolve(x, np.ones(k) / k, mode='same') if k > 1 else x
def bell(d, p=1.0): return np.sin(np.linspace(0, np.pi, int(SR * d))) ** p
def osc(freq, shape='sine'):
    ph = 2 * np.pi * np.cumsum(freq) / SR
    if shape == 'saw': return 2 * ((ph / (2 * np.pi)) % 1) - 1
    return np.sin(ph)
def sweep(f0, f1, d, shape='sine'): return osc(np.geomspace(f0, f1, int(SR * d)), shape)


def sfx(name, dur=None):
    if name == 'pop': x, g = sweep(900, 240, 0.09) * dec(0.09, 35), 0.6
    elif name == 'crunch':
        n = noise(0.18); m = (rng.uniform(0, 1, len(n) // 220 + 1) > 0.45).repeat(220)[:len(n)]
        x, g = lpf(n, 2) * m * dec(0.18, 14), 0.55
    elif name == 'gulp': x, g = sweep(420, 140, 0.16) * bell(0.16), 0.7
    elif name == 'burp':
        s = sweep(95, 70, 0.7, 'saw') * (1 + 0.5 * noise(0.7)); x, g = lpf(s, 18) * bell(0.7, 0.5), 1.0
    elif name == 'ring':
        tt = t_arr(dur); x = (np.sin(2 * np.pi * 1750 * tt) + 0.6 * np.sin(2 * np.pi * 2630 * tt)) * (np.sin(2 * np.pi * 22 * tt) > 0); g = 0.22
    elif name == 'ring_weak':
        x = osc(np.linspace(1500, 1000, int(SR * 0.3))) * (np.sin(2 * np.pi * 18 * t_arr(0.3)) > 0) * dec(0.3, 5); g = 0.12
    elif name == 'click': x, g = np.diff(noise(0.02), prepend=0) * dec(0.02, 200), 0.5
    elif name in ('smash', 'bonk'):
        d = 0.6 if name == 'smash' else 0.35
        th = sweep(110 if name == 'smash' else 160, 40, d) * dec(d, 6)
        nz = lpf(noise(d), 3) * dec(d, 9)
        cl = sum(np.sin(2 * np.pi * f * t_arr(d)) * dec(d, k) for f, k in ((523, 7), (787, 9), (1187, 11)))
        x, g = th + 0.7 * nz + 0.25 * cl, 1.0 if name == 'smash' else 0.85
    elif name in ('whoosh', 'whoosh_s'):
        d = 0.4 if name == 'whoosh' else 0.22; x = lpf(noise(d), 10) * bell(d, 2); g = 0.6 if name == 'whoosh' else 0.3
    elif name == 'squirt': x, g = lpf(noise(0.2), 5) * dec(0.2, 10) + 0.3 * sweep(700, 250, 0.2) * dec(0.2, 15), 0.5
    elif name == 'slurp':
        tt = t_arr(dur); n = lpf(noise(dur), 6) * (0.6 + 0.4 * np.sin(2 * np.pi * 8 * tt))
        s = osc(220 + 70 * np.sin(2 * np.pi * 6 * tt)); x, g = (n * 1.5 + 0.35 * s) * bell(dur, 0.3), 0.55
    elif name == 'ahh':
        tt = t_arr(0.8); f = 170 * (1 - 0.15 * tt / 0.8) + 4 * np.sin(2 * np.pi * 5.5 * tt)
        x, g = lpf(osc(f, 'saw'), 9) * bell(0.8, 0.4), 0.7
    elif name == 'inhale': x, g = lpf(noise(dur), 4) * np.linspace(0, 1, int(SR * dur)) ** 2, 0.6
    elif name == 'blow': x, g = lpf(noise(dur), 12) * bell(dur, 0.5), 0.8
    elif name == 'splat': x, g = sweep(80, 40, 0.5) * dec(0.5, 8) + 3 * lpf(noise(0.5), 20) * dec(0.5, 10), 1.0
    elif name == 'horn':
        tt = t_arr(0.55); x, g = lpf(osc(520 + 30 * np.sin(2 * np.pi * 6 * tt), 'saw'), 5) * bell(0.55, 0.3), 0.3
    elif name == 'clap': x, g = np.diff(noise(0.08), prepend=0) * dec(0.08, 60), 0.45
    elif name == 'sting':
        x = lpf(osc(np.full(int(SR * 0.9), 110.0), 'saw') + osc(np.full(int(SR * 0.9), 55.6), 'saw'), 6) * dec(0.9, 3.5)
        x += 0.5 * np.sin(2 * np.pi * 55 * t_arr(0.9)) * dec(0.9, 3); g = 0.55
    elif name == 'ding':
        x = np.sin(2 * np.pi * 1320 * t_arr(0.9)) * dec(0.9, 5) + 0.4 * np.sin(2 * np.pi * 2640 * t_arr(0.9)) * dec(0.9, 8); g = 0.35
    elif name == 'boing':
        tt = t_arr(0.5); x, g = osc(180 + 300 * tt + 40 * np.sin(2 * np.pi * 18 * tt)) * dec(0.5, 5), 0.4
    elif name == 'yawn':
        tt = t_arr(0.9); f = np.linspace(330, 190, len(tt)) + 6 * np.sin(2 * np.pi * 5 * tt)
        x, g = (osc(f) + 0.3 * lpf(noise(0.9), 8)) * bell(0.9, 0.6), 0.3
    elif name == 'psst': x, g = np.diff(noise(0.25), prepend=0) * dec(0.25, 9), 0.4
    elif name == 'fizz': x, g = np.diff(noise(dur), prepend=0) * (rng.uniform(0, 1, int(SR * dur)) > 0.6) * dec(dur, 1.5), 0.45
    elif name == 'rattle':
        tt = t_arr(dur); x, g = lpf(noise(dur), 3) * (np.sin(2 * np.pi * 15 * tt) > 0.3), 0.45
    elif name == 'lick': x, g = lpf(noise(0.14), 4) * bell(0.14) + 0.4 * sweep(300, 700, 0.14) * bell(0.14), 0.45
    elif name == 'freeze':
        tt = t_arr(1.2); x = sum(np.sin(2 * np.pi * f * (1 - 0.25 * tt / 1.2) * tt) * (0.5 + 0.5 * np.sin(2 * np.pi * (9 + j) * tt))
                                for j, f in enumerate((2100, 2650, 3150, 3700))) * dec(1.2, 2); g = 0.3
    elif name == 'bang': x, g = sweep(150, 40, 0.4) * dec(0.4, 8) + lpf(noise(0.4), 2) * dec(0.4, 14), 1.0
    elif name == 'carve':
        tt = t_arr(0.28); x, g = lpf(noise(0.28), 3) * (0.6 + 0.4 * np.sin(2 * np.pi * 30 * tt)) * bell(0.28), 0.4
    else: raise ValueError(name)
    return x / (np.abs(x).max() + 1e-9) * g


def music(dur, seed):
    rnd = random.Random(seed)
    bpm = rnd.choice([116, 120, 124, 128, 132]); beat = 60 / bpm; key = rnd.randint(-3, 3)
    out = np.zeros(int(SR * dur) + SR)
    def mf(m): return 440 * 2 ** ((m + key - 69) / 12)
    def pluck(f, d, k, bright):
        tt = t_arr(d); return (np.sin(2 * np.pi * f * tt) + bright * np.sin(4 * np.pi * f * tt) + 0.12 * np.sin(6 * np.pi * f * tt)) * np.exp(-tt * k)
    def add(t0, x):
        i0 = int(t0 * SR); out[i0:i0 + len(x)] += x[:max(0, len(out) - i0)]
    prog = rnd.choice([[48, 45, 41, 43], [48, 43, 45, 41], [45, 41, 48, 43], [48, 41, 43, 48]])
    penta = [60, 62, 64, 67, 69, 72, 74, 76]; bright = rnd.uniform(0.2, 0.5)
    motif = [None if rnd.random() < 0.3 else rnd.choice(penta) for _ in range(16)]
    motif2 = [m if (m is None or rnd.random() < 0.6) else rnd.choice(penta) for m in motif]
    for b in range(int(dur / beat) + 1):
        t0 = b * beat; bar = b // 4; root = prog[bar % 4]
        add(t0, 0.9 * pluck(mf(root if b % 2 == 0 else root + 7), 0.35, 7, 0.35))
        if b % 2 == 0: add(t0, 0.8 * sweep(130, 45, 0.18) * dec(0.18, 18))
        else: add(t0, 0.25 * lpf(noise(0.12), 2) * dec(0.12, 30))
        add(t0 + beat / 2, 0.12 * np.diff(noise(0.03), prepend=0) * dec(0.03, 120))
        mot = motif if (bar // 2) % 2 == 0 else motif2
        for h in (0, 1):
            n = mot[(b * 2 + h) % 16]
            if n is not None: add(t0 + h * beat / 2, 0.32 * pluck(mf(n), 0.25, 11, bright))
    out = out[:int(SR * dur)]
    out *= np.clip((dur - t_arr(dur)) / 0.6, 0, 1)
    return out / np.abs(out).max() * 0.22


def build_audio(path):
    tot = total(); n = int(SR * tot); mix = music(tot, PLAN['seed'])
    def place(t0, x):
        i0 = int(t0 * SR); mix[i0:i0 + len(x)] += x[:max(0, n - i0)]
    for t0 in (0.0, 0.45): place(t0, sfx('pop'))
    for k, key in enumerate(PLAN['gags']):
        g = GAGS[key]; base = INTRO + k * GAG
        for ev in g['N']: place(base + ev[0], sfx(ev[1], *ev[2:]))
        for ev in g['P']: place(base + NDUR + ev[0], sfx(ev[1], *ev[2:]))
    place(INTRO + GAG * len(PLAN['gags']), sfx('ding'))
    mix = mix / np.abs(mix).max() * 0.92
    pcm = (np.repeat(mix[:, None], 2, axis=1) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- video
def render_video(plan, out_dir, workers=None):
    configure(plan)
    os.makedirs(out_dir, exist_ok=True)
    wav = os.path.join(out_dir, 'audio.wav'); mp4 = os.path.join(out_dir, 'video.mp4')
    build_audio(wav)
    nf = int(total() * FPS)
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav, '-c:v', 'libx264', '-preset', 'medium',
           '-crf', '19', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', mp4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(workers or os.cpu_count(), initializer=configure, initargs=(plan,)) as pool:
        for i, buf in enumerate(pool.imap(_frame_bytes, range(nf), chunksize=6)):
            p.stdin.write(buf)
            if i % 150 == 0: print(f'  frame {i}/{nf}', flush=True)
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError('ffmpeg failed')
    os.remove(wav)
    return mp4


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


if __name__ == '__main__':
    plan = dict(format=_arg('--format', 'psycho'), cast=_arg('--cast', 'bloop'), seed=1,
                gags=_arg('--gags', 'cookie,alarm,ketchup,cake').split(','))
    out = os.path.join(HERE, 'output', 'preview')
    if '--preview' in sys.argv:
        configure(plan); os.makedirs(out, exist_ok=True)
        for s in _arg('--preview', '3').split(','):
            render_frame(int(float(s) * FPS)).save(os.path.join(out, f'p_{s}.png'))
        print('preview ok')
    else:
        print(render_video(plan, out))
