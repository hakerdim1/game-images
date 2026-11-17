# -*- coding: utf-8 -*-
# 1) Сначала пробует скачать готовую картинку из репозитория game-images.
# 2) Если её нет — выдаёт уникальный рендер реального скина CS2 той же модели.
import json, os, re, zipfile, hashlib
import requests
from concurrent.futures import ThreadPoolExecutor

API  = "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/"
REPO = "https://raw.githubusercontent.com/hakerdim1/game-images/main/"
DB_FILE = "cases_200.txt"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
EXTS = ('.png', '.jpg', '.jpeg')

TRANSLIT = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z',
            'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
            'с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch',
            'ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}

def slugify(name):
    out = []
    for ch in name.lower():
        if ch in TRANSLIT: out.append(TRANSLIT[ch])
        elif ch.isalnum(): out.append(ch)
        else: out.append('_')
    return re.sub(r'_+', '_', ''.join(out)).strip('_')

def norm(s):
    s = s.lower().replace('ё', 'е').replace('★', '')
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

RU_MAP = {
    'ак 47': 'weapon_ak47', 'm4a4': 'weapon_m4a1', 'm4a1 s': 'weapon_m4a1_silencer',
    'awp': 'weapon_awp', 'famas': 'weapon_famas', 'galil ar': 'weapon_galilar',
    'nova': 'weapon_nova', 'mag 7': 'weapon_mag7', 'mp9': 'weapon_mp9',
    'mp7': 'weapon_mp7', 'mp5 sd': 'weapon_mp5sd', 'pp bizon': 'weapon_bizon',
    'ump 45': 'weapon_ump45', 'mac 10': 'weapon_mac10', 'p90': 'weapon_p90',
    'm249': 'weapon_m249', 'scar 20': 'weapon_scar20', 'r8 revolver': 'weapon_revolver',
    'glock 18': 'weapon_glock', 'usp s': 'weapon_usp_silencer', 'p250': 'weapon_p250',
    'five seven': 'weapon_fiveseven', 'tec 9': 'weapon_tec9', 'desert eagle': 'weapon_deagle',
    'dual berettas': 'weapon_elite', 'p2000': 'weapon_hkp2000', 'sg 553': 'weapon_sg556',
    'aug': 'weapon_aug', 'ssg 08': 'weapon_ssg08', 'negev': 'weapon_negev',
    'sawed off': 'weapon_sawedoff', 'xm1014': 'weapon_xm1014',
    'керамбит': 'weapon_knife_karambit', 'нож бабочка': 'weapon_knife_butterfly',
    'штык нож': 'weapon_bayonet', 'штык нож m9': 'weapon_knife_m9_bayonet',
    'складной нож': 'weapon_knife_flip', 'медвежий нож': 'weapon_knife_ursus',
    'нож охотника': 'weapon_knife_tactical', 'нож кукри': 'weapon_knife_kukri',
    'клинки теней': 'weapon_knife_push', 'нож стилет': 'weapon_knife_widowmaker',
    'нож наваха': 'weapon_knife_gypsy_jackknife', 'коготь': 'weapon_knife_talon',
}

print("Скачиваю API CS2 (EN)...")
bw = requests.get(API + 'base_weapons.json', headers=HEADERS, timeout=60).json()
skins = requests.get(API + 'skins.json', headers=HEADERS, timeout=120).json()
crates = requests.get(API + 'crates.json', headers=HEADERS, timeout=60).json()
print(f"ОК: {len(bw)} моделей, {len(skins)} скинов, {len(crates)} кейсов")

# Пул картинок на каждую модель: базовый рендер + все реальные скины этой модели
weapon_images = {}
for w in bw:
    if w.get('image'):
        weapon_images.setdefault(w['id'], []).append(w['image'])
for sk in skins:
    wid = (sk.get('weapon') or {}).get('id')
    if wid and sk.get('image'):
        weapon_images.setdefault(wid, []).append(sk['image'])

gloves_imgs = [sk['image'] for sk in skins
               if (('Gloves' in (sk.get('name') or '')) or ('Hand Wraps' in (sk.get('name') or '')))
               and sk.get('image')]
crate_imgs = [c['image'] for c in crates if c.get('image') and 'weapon_cases' in c['image']]

db = json.load(open(DB_FILE, encoding='utf-8'))
jobs, failed = [], []

def pool_for(nw):
    if 'перчатк' in nw or 'обмотк' in nw:
        return gloves_imgs
    wid = RU_MAP.get(nw)
    return weapon_images.get(wid, []) if wid else []

seen = set()
for cdata in db.values():
    for it in cdata['items']:
        raw = it['name']
        if raw in seen:
            continue
        seen.add(raw)
        slug = slugify(raw)
        # кандидаты: сначала репозиторий (png/jpg/jpeg), потом уникальный рендер из API
        cands = [REPO + slug + e for e in EXTS]
        pool = pool_for(norm(raw.split('|', 1)[0]))
        if pool:
            idx = int(hashlib.md5(raw.encode('utf-8')).hexdigest(), 16) % len(pool)
            cands.append(pool[idx])
        if len(cands) <= len(EXTS):
            failed.append(raw)
            continue
        jobs.append((cands, os.path.join('images', slug + '.png')))

for i, cname in enumerate(db):
    slug = 'case_' + slugify(cname)
    cands = [REPO + slug + e for e in EXTS] + [crate_imgs[i % len(crate_imgs)]]
    jobs.append((cands, os.path.join('images', slug + '.png')))

print(f"К скачиванию: {len(jobs)} файлов")
os.makedirs('images', exist_ok=True)

def fetch(job):
    cands, path = job
    for url in cands:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.ok:
                with open(path, 'wb') as f:
                    f.write(r.content)
                return True
        except Exception:
            pass
    return False

ok = 0
with ThreadPoolExecutor(16) as ex:
    for res in ex.map(fetch, jobs):
        ok += res
print(f"Скачано: {ok}/{len(jobs)}")

with zipfile.ZipFile('images.zip', 'w', zipfile.ZIP_STORED) as z:
    for _, path in jobs:
        if os.path.exists(path):
            z.write(path, os.path.relpath(path))
print("Готово: images.zip")

if failed:
    with open('failed.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(failed))
    print(f"Не распознаны модели: {len(failed)} — список в failed.txt")
else:
    print("Все модели распознаны, failed.txt не нужен.")
