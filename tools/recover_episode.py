#!/usr/bin/env python3
"""Yüklenip geçmişe yazılamayan bölümü (git çakışması vb.) YouTube açıklamasından geri kaydet.
python tools/recover_episode.py VIDEO_ID"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bloop, upload

vid = sys.argv[1]; HIST = Path(__file__).resolve().parent.parent / 'history.json'
hist = json.loads(HIST.read_text())
if any(v['id'] == vid for v in hist['videos']): sys.exit('zaten kayıtlı')
it = upload.client().videos().list(part='snippet,status', id=vid).execute()['items'][0]; sn = it['snippet']
title_to_gag = {g['title'].title(): k for k, g in bloop.GAGS.items()}
name_to_cast = {c['name']: k for k, c in bloop.CAST.items()}
items = []
for m in re.finditer(r'^\d+\. (.+) \((.+?)\)$', sn['description'], re.M):
    g, c = title_to_gag.get(m.group(1)), name_to_cast.get(m.group(2))
    if g and c: items.append([g, c])
    else: print('eşleşmedi:', m.group(0))
kurgu = 'situations' if 'Situations' in sn['title'] else None
rec = dict(id=vid, date=sn['publishedAt'][:16].replace('T', ' '), kind='episode', title=sn['title'],
           privacy=it['status']['privacyStatus'], format=None, kurgu=kurgu, theme=None, items=items, recovered=True)
hist['videos'].append(rec); hist['videos'].sort(key=lambda v: v.get('date', ''))
HIST.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + '\n')
print('kaydedildi:', sn['title'], len(items), 'durum')
