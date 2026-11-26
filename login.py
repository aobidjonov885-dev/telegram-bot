import os
import re
import sys
import json
from telethon.sync import TelegramClient

# python login.py            -> asosiy "sniper" seansi
# python login.py acc2 post  -> qo'shimcha akkaunt, roli: sniper | post | both (bot ishlab turgan bo'lsa ham 1-2 daqiqada o'zi qo'shib oladi)
ACC_FILE = "accounts.json"
CFG_FILE = "config.json"


def load_cfg():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(c):
    tmp = CFG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CFG_FILE)


def get_creds(session):
    # Har bir akkaunt uchun alohida api_id/api_hash: config.json > creds > seans nomi
    c = load_cfg()
    try:
        x = c["creds"][session]
        return int(x["api_id"]), str(x["api_hash"])
    except Exception:
        pass
    print(f"'{session}' akkaunti uchun my.telegram.org dan olingan API ma'lumotlari:")
    api_id = input("api_id: ").strip()
    api_hash = input("api_hash: ").strip()
    if not api_id.isdigit() or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        sys.exit("api_id raqam, api_hash 32 ta harf-raqam bo'lishi kerak.")
    c.setdefault("creds", {})[session] = {"api_id": int(api_id), "api_hash": api_hash}
    save_cfg(c)
    return int(api_id), api_hash


def read_accounts():
    if not os.path.exists(ACC_FILE):
        return {}
    try:
        with open(ACC_FILE) as f:
            return json.load(f)
    except Exception:
        sys.exit(f"{ACC_FILE} o'qilmadi (buzilgan). Tekshiring yoki {ACC_FILE}.bak dan tiklang.")


def write_accounts(data):
    tmp = ACC_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    if os.path.exists(ACC_FILE):
        try:
            import shutil
            shutil.copy2(ACC_FILE, ACC_FILE + ".bak")
        except OSError:
            pass
    os.replace(tmp, ACC_FILE)


session = sys.argv[1] if len(sys.argv) > 1 else "sniper"
if not re.fullmatch(r"[A-Za-z0-9_]+", session):
    sys.exit("Seans nomi faqat harf, raqam va _ dan iborat bo'lishi kerak.")

ROLE = sys.argv[2] if len(sys.argv) > 2 else "both"
if ROLE not in ("sniper", "post", "both"):
    sys.exit("Rol: sniper, post yoki both bo'lishi kerak. Masalan: python login.py acc2 post")

_known = set(read_accounts()) | ({"sniper"} if os.path.exists("sniper.session") else set())
if session not in _known and len(_known) >= 5:
    sys.exit("Limit: ko'pi bilan 5 ta akkaunt (istalgan rolda).")
_roles = {s: (m.get("role") if isinstance(m, dict) else "both") or "both" for s, m in read_accounts().items()}
_n_s = sum(r in ("sniper", "both") for k, r in _roles.items() if k != session)
_n_p = sum(r in ("post", "both") for k, r in _roles.items() if k != session)
if ROLE in ("sniper", "both") and _n_s >= 5:
    sys.exit("Sniper o'rinlari to'lgan (5/5).")
if ROLE in ("post", "both") and _n_p >= 5:
    sys.exit("Avto post o'rinlari to'lgan (5/5).")

API_ID, API_HASH = get_creds(session)

# Telefon raqam, SMS/Telegram kodi va (bo'lsa) 2 bosqichli parol so'raladi
with TelegramClient(session, API_ID, API_HASH) as client:
    me = client.get_me()
    label = (me.first_name or "").strip()
    if me.username:
        label += f" @{me.username}"
    print("Kirildi:", label or session)

try:
    os.chmod(session + ".session", 0o600)
except OSError:
    pass

if session != "sniper":
    data = read_accounts()
    old = data.get(session, {})
    data[session] = {"label": label or session, "claimed": old.get("claimed"), "role": ROLE}
    write_accounts(data)
    print("accounts.json ga qo'shildi. Bot ishlab turgan bo'lsa, 1-2 daqiqada o'zi ulaydi.")
