#!/usr/bin/env python3
"""Durum dosyalarını çakışmasız gönder: başka iş aynı anda history.json'a yazdıysa iki tarafın kayıtlarını birleştirir.
python3 tools/push_state.py "commit mesajı" history.json [playlists.json ...]
(2026-10-19: 'git pull --rebase' çakışması bir bölümün kaydını kaybettirdi → tekrar engeli bozuldu.)"""
import json, subprocess, sys, time
from pathlib import Path

msg, files = sys.argv[1], [Path(f) for f in sys.argv[2:] if Path(f).exists()]
def load(f):
    try: return json.loads(f.read_text())
    except Exception: return None   # JSON değil → bizim halimiz yazılır
raw = {f: f.read_bytes() for f in files}
ours = {f: load(f) for f in files}


def sh(*a, check=True): return subprocess.run(a, check=check, capture_output=True, text=True)


def merge(theirs, mine):
    if isinstance(theirs, dict) and isinstance(mine, dict):
        out = dict(theirs)
        for k, v in mine.items(): out[k] = merge(theirs[k], v) if k in theirs else v
        return out
    if isinstance(theirs, list) and isinstance(mine, list):
        key = lambda x: x.get('id') if isinstance(x, dict) and 'id' in x else json.dumps(x, sort_keys=True)
        seen = {key(x) for x in theirs}
        return theirs + [x for x in mine if key(x) not in seen]
    return mine


for attempt in range(5):
    sh('git', 'fetch', '-q', 'origin', 'main'); sh('git', 'reset', '-q', '--hard', 'origin/main')
    for f, mine in ours.items():
        base = load(f) if f.exists() else None
        if mine is None or base is None: f.write_bytes(raw[f]); continue
        f.write_text(json.dumps(merge(base, mine), indent=2, ensure_ascii=False) + '\n')
    sh('git', 'add', *map(str, files))
    if sh('git', 'diff', '--cached', '--quiet', check=False).returncode == 0: print('değişiklik yok'); break
    sh('git', 'commit', '-q', '-m', msg)
    if sh('git', 'push', '-q', 'origin', 'HEAD:main', check=False).returncode == 0: print('✓ gönderildi'); break
    time.sleep(5 + attempt * 5)
else:
    sys.exit('gönderilemedi')
