"""Haftalık derleme (uzun video): son 7 günün en çok izlenen Shorts'ları, kayıtlı planlarından (history.json:
format/cast/gags/seed) yeniden render edilip "#7 → #1" sırasıyla tek videoda birleştirilir ve normal (uzun) video
olarak yüklenir. 3 dakikayı aşan dikey video Shorts sayılmaz → izlenme süresi YPP'nin 4.000 saatine yazılır.

  python compile.py [--no-upload] [--top 7] [--days 7]
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bloop  # noqa: E402
from PIL import Image  # noqa: E402

HISTORY = HERE / 'history.json'
FF = None


def ff(*args):
    subprocess.run([FF, '-y', '-loglevel', 'error', *args], check=True)


def card(path, big, small, seconds=1.6):
    """Tam ekran başlık kartı (1080x1920) + sessiz ses → mp4. Yazı fontunda emoji yok → emojiler atılır."""
    import re
    strip = lambda t: re.sub('[\U0001F000-\U0001FFFF\u2600-\u27BF\u200d\ufe0f]', '', t).strip()  # noqa: E731
    big, small = strip(big), strip(small)
    img = Image.new('RGB', (bloop.W, bloop.H), (24, 20, 38))
    bloop.put_text_px(img, big, bloop.W // 2, bloop.H // 2 - 80, 170, (255, 214, 60), max_w=980)
    bloop.put_text_px(img, small, bloop.W // 2, bloop.H // 2 + 140, 70, (255, 255, 255), max_w=980)
    png = str(path) + '.png'
    img.save(png)
    ff('-loop', '1', '-i', png, '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', str(seconds),
       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(bloop.FPS), '-c:a', 'aac', '-shortest', str(path))


def top_videos(hist, days, n):
    import upload
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M')
    vids = [v for v in hist['videos'] if v.get('kind', 'short') == 'short' and v.get('date', '') >= since
            and v.get('privacy') == 'public' and v.get('gags')]
    if not vids:
        return []
    stats = {}
    ids = [v['id'] for v in vids]
    for k in range(0, len(ids), 50):
        for it in upload.client().videos().list(part='statistics', id=','.join(ids[k:k + 50])).execute().get('items', []):
            stats[it['id']] = int(it['statistics'].get('viewCount', 0))
    for v in vids:
        v['views'] = stats.get(v['id'], 0)
    return sorted(vids, key=lambda v: -v['views'])[:n]


def main():
    global FF
    import imageio_ffmpeg
    FF = imageio_ffmpeg.get_ffmpeg_exe()
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-upload', action='store_true')
    ap.add_argument('--top', type=int, default=7)
    ap.add_argument('--days', type=int, default=7)
    a = ap.parse_args()
    hist = json.loads(HISTORY.read_text())
    best = top_videos(hist, a.days, a.top)
    if len(best) < 5:
        print(f'derleme için yeterli video yok ({len(best)}), atlandı'); return
    n_comp = sum(1 for v in hist['videos'] if v.get('kind') == 'compilation') + 1
    out = HERE / 'output' / f'compilation-{n_comp}'
    out.mkdir(parents=True, exist_ok=True)
    parts = []
    card(out / 'intro.mp4', 'BEST OF THE WEEK', f'Top {len(best)} most watched · Bloop Bonkers', 2.4)
    parts.append(out / 'intro.mp4')
    order = list(reversed(best))  # #N → #1
    for rank, v in zip(range(len(order), 0, -1), order):
        print(f"#{rank}: {v['title']} ({v['views']} izlenme)", flush=True)
        plan = {k: v[k] for k in ('format', 'cast', 'gags', 'seed')}
        mp4 = bloop.render_video(plan, str(out / f'clip{rank}'))
        card(out / f'rank{rank}.mp4', f'#{rank}', v['title'][:40])
        parts += [out / f'rank{rank}.mp4', Path(mp4)]
    card(out / 'outro.mp4', 'WHICH ONE ARE YOU?', 'New chaos every day', 2.4)
    parts.append(out / 'outro.mp4')
    lst = out / 'parts.txt'
    lst.write_text(''.join(f"file '{p}'\n" for p in parts))
    final = out / 'compilation.mp4'
    ff('-f', 'concat', '-safe', '0', '-i', str(lst), '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
       '-pix_fmt', 'yuv420p', '-r', str(bloop.FPS), '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(final))
    print(f'derleme hazır: {final}', flush=True)
    title = f'Normal vs Psycho & More: Best of the Week #{n_comp} 😂 | Bloop Bonkers Compilation'
    desc = ('The most watched Bloop Bonkers moments of the week, counting down from #'
            f'{len(best)} to #1. Which one are YOU? Comment 1 or 2! 👇\n\n'
            + '\n'.join(f"#{r} {v['title']} https://youtube.com/shorts/{v['id']}"
                        for r, v in zip(range(1, len(best) + 1), best))
            + '\n\nNew Bloop Bonkers Shorts every day. Subscribe for more chaos! 🟣\n\n#animation #funny #cartoon #compilation')
    tags = ['bloop bonkers', 'normal vs psycho', 'funny animation', 'cartoon compilation', '3d animation', 'funny',
            'compilation', 'best of the week']
    if a.no_upload:
        print('yükleme yok (--no-upload)'); return
    import upload
    privacy = os.environ.get('YT_PRIVACY') or 'private'
    vid = upload.upload(str(final), title, desc, tags, privacy, category='23')
    print(f'yüklendi: https://youtu.be/{vid} ({privacy})', flush=True)
    hist['videos'].append(dict(id=vid, date=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'), kind='compilation',
                               title=title, privacy=privacy, items=[v['id'] for v in best]))
    HISTORY.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
