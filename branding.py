"""Kanal görselleri: branding/profile.png (800x800), banner.png (2560x1440), watermark.png (150x150)."""
import os
from PIL import Image, ImageDraw

import bloop as B

OUT = os.path.join(B.HERE, 'branding')


def char_img(cast, o, size):
    """Karakteri kendi tuvaline çizip yüz/gövde etrafından kırpar."""
    B.configure(dict(cast=cast, format='psycho', gags=['cookie'], seed=1))
    img = Image.new('RGBA', (B.L(600), B.L(600)), (0, 0, 0, 0))
    B.draw_char(img, 300, 560, dict(t=0.5, **o))
    cy = 560 - 26 - B.R
    c = img.crop((B.L(300 - 215), B.L(cy - 250), B.L(300 + 215), B.L(cy + 215 - 35)))
    return c.resize((size, int(size * c.height / c.width)), Image.LANCZOS)


def gradient(w, h, c1, c2):
    im = Image.new('RGB', (w, h)); d = ImageDraw.Draw(im)
    for y in range(h): d.line([(0, y), (w, y)], fill=B.lerpc(c1, c2, y / h))
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    # profil: Bloop, yuvarlak kırpmaya uygun ortalanmış
    pf = gradient(800, 800, (255, 215, 80), (255, 140, 60))
    d = ImageDraw.Draw(pf)
    for r in range(560, 0, -80): d.ellipse([400 - r, 430 - r, 400 + r, 430 + r], outline=(255, 235, 150), width=10)
    ch = char_img('bloop', dict(eyes='crazy', brow='angry', mouth='grin'), 640)
    pf.paste(ch, (80, 800 - ch.height + 40), ch)
    pf.save(os.path.join(OUT, 'profile.png'))
    # banner: güvenli alan ortadaki 1546x423
    bn = gradient(2560, 1440, (120, 70, 225), (60, 30, 130))
    d = ImageDraw.Draw(bn)
    for x in range(-1440, 2560, 120): d.line([(x, 0), (x + 1440, 1440)], fill=(135, 85, 235), width=40)
    B.put_text_px(bn, 'BLOOP BONKERS', 1280, 640, 150, (255, 225, 70), rot=-3)
    B.put_text_px(bn, 'NORMAL vs PSYCHO  •  NEW SHORTS DAILY', 1280, 790, 58, (255, 255, 255))
    for cast, x, o in (('zip', 560, dict(eyes='happy', mouth='open', mo=0.6)),
                       ('bloop', 2010, dict(eyes='crazy', brow='angry', mouth='grin')),
                       ('mimi', 370, dict(eyes='normal', mouth='smile', look=(0.6, 0))),
                       ('grumbo', 2200, dict(mouth='flat', look=(-0.6, 0)))):
        size = 300 if cast in ('zip', 'bloop') else 220
        im = char_img(cast, o, size)
        bn.paste(im, (x - im.width // 2, 930 - im.height if cast in ('zip', 'bloop') else 1000 - im.height), im)
    bn.save(os.path.join(OUT, 'banner.png'))
    wm = Image.new('RGBA', (150, 150), (0, 0, 0, 0)); d = ImageDraw.Draw(wm)
    d.ellipse([4, 4, 146, 146], fill=(230, 40, 50), outline=(255, 255, 255), width=6)
    B.put_text_px(wm, 'SUB', 75, 77, 44, (255, 255, 255))
    wm.save(os.path.join(OUT, 'watermark.png'))
    print('ok', OUT)


if __name__ == '__main__':
    main()
