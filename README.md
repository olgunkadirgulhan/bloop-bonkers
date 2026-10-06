# Bloop Bonkers — otomatik animasyon Shorts kanalı (ABD)

Orijinal 3B görünümlü karakterler (Bloop, Zip, Grumbo, Mimi), ikiye bölünmüş ekran "A vs B" gag'leri.
Her şey kodla üretilir (karakter, sahne, müzik, efekt): telif yok.

- `bloop.py` motor: 6 format x 4 karakter x 8 gag (balkabağı sadece Eylül-Ekim), rastgele müzik
- `run.py` plan seçer (son videolarla aynı format/karakter/gag seti tekrar etmez), render eder, yükler, `history.json`'a yazar
- `channel_setup.py` açıklama, banner, filigran, oynatma listeleri; `--delete-old` eski videoları siler
- `branding.py` profil resmi / banner / filigran üretir (`branding/`)

**Takvim:** günde 3 Short, 14:00, 18:00, 23:00 UTC. Saatlik tetiklenir, `.github/slot_guard.py` karar verir.
**Variables:** `YT_PRIVACY` (boş = private, `public` = yayında).

Yerel: `python bloop.py --preview 3,9 --gags soda,cake --cast zip --format level`
