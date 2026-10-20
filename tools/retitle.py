#!/usr/bin/env python3
"""Video başlığını değiştir (YouTube + history.json). python tools/retitle.py VIDEO_ID 'eski parça' 'yeni parça'"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import upload

vid, old, new = sys.argv[1:4]
api = upload.client(); it = api.videos().list(part='snippet', id=vid).execute()['items'][0]; sn = it['snippet']
if old not in sn['title']: sys.exit(f'başlıkta yok: {sn["title"]}')
sn['title'] = sn['title'].replace(old, new)[:100]
api.videos().update(part='snippet', body={'id': vid, 'snippet': {k: sn[k] for k in ('title', 'description', 'tags', 'categoryId') if k in sn}}).execute()
H = Path(__file__).resolve().parent.parent / 'history.json'; h = json.loads(H.read_text())
for v in h['videos']:
    if v.get('id') == vid: v['title'] = sn['title']
H.write_text(json.dumps(h, indent=2, ensure_ascii=False) + '\n')
print('✓', sn['title'])
