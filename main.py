import os, re, io, json, time, glob, shutil, hmac, hashlib, random, zipfile, asyncio, logging
from collections import deque
from urllib.parse import parse_qsl
import httpx
from datetime import datetime, timezone, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
    WebAppInfo, MenuButtonWebApp, MenuButtonCommands, BotCommand, BotCommandScopeChat,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telethon import TelegramClient, errors, events, utils
from telethon.tl import types as T
from telethon.tl.functions.auth import ResendCodeRequest
from telethon.tl.functions.channels import (
    CreateChannelRequest, UpdateUsernameRequest, DeleteChannelRequest, GetParticipantRequest, JoinChannelRequest,
    GetFullChannelRequest,
)
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.account import (
    CheckUsernameRequest as AccCheck,
    UpdateUsernameRequest as AccUpdate,
)

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.environ.get("TZ_NAME", "Asia/Tashkent"))
except Exception:
    TZ = timezone(timedelta(hours=5))
TZ_LABEL = getattr(TZ, "key", None) or str(TZ)

try:
    from aiohttp import web
except ImportError:   # pip install aiohttp
    web = None

logging.basicConfig(level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING))
log = logging.getLogger("sniper")

TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])   # bot FAQAT shu foydalanuvchi uchun ishlaydi

CHECK_DELAY = 3     # soniya: tekshiruvlar orasida (kamaytirmang!)
MAX_CHECK = 200     # bir martada nechta username tekshirilsin
VERIFY_DELAY = 2        # Telegramdan 'bo'shmi?' deb so'rash orasidagi pauza (soniya)
MAX_VERIFY = 20         # bir xabarda ko'pi bilan nechta username Telegramdan tasdiqlanadi
RESOLVE_DELAY = 3       # akkaunt qidirish orasidagi pauza (soniya)
MAX_RESOLVE = 25        # bir xabarda ko'pi bilan nechta akkaunt qidiriladi
INACTIVE_DAYS = 180     # shuncha kundan ko'p kirmagan akkaunt avtomatik kuzatuvga qo'shiladi
WATCH_LONG_AGO = True   # Telegram "uzoq vaqt oldin" (>1 oy, aniq muddat noma'lum) desa ham kuzatuvga qo'shish
MAX_WATCH = 300         # bir vaqtda ko'pi bilan nechta username
CACHE_TTL = 6 * 3600
CACHE_MAX = 2000
GROUPS_FILE = "groups.json"
SPAM_CHECK_EVERY = 6 * 3600   # @SpamBot orqali akkaunt holatini tekshirish oralig'i
CONF_FILE = "settings.json"
BL_FILE = "blocklist.json"
BL_CHANNEL = "mashka_malumotlari"   # shu kanal postlaridan blok ro'yxati yig'iladi
SYNC_EVERY = 30 * 60               # kanalni yangi postlar uchun tekshirish oralig'i (soniya)
BL_MAX = 100000
POSTS_FILE = "posts.json"
MIN_GAP = 40                  # habarlar (guruhlar) orasidagi eng kam pauza, soniya (Telegram spam-filtri uchun)
MIN_CYCLE = 300               # tsikllar orasidagi eng kam pauza, soniya
POST_HOURLY_CAP = 60          # bitta akkaunt bir soatda ko'pi bilan nechta post yuboradi
SLOW_MAX = 4.0                # FloodWaitdan keyin tekshiruv pauzasi ko'pi bilan shuncha marta uzayadi
SLOW_STEP = 1.5               # har FloodWaitda pauza shuncha marta uzayadi
SLOW_RECOVER = 3600           # shuncha soniya FloodWaitsiz o'tsa, pauza asta-sekin qisqaradi
DEFAULT_GAP = 40              # habarlar orasida (boshlang'ich)
DEFAULT_CYCLE = 10 * 60       # tsikllar orasida (boshlang'ich)
MAX_GROUPS = 40
MAX_TEXTS = 10
WARN_PAUSE = 24 * 3600        # warn olinsa yozmaslik muddati (warn'da muddat bo'lmaydi)
FALLBACK_PAUSE = 6 * 3600     # yozib bo'lmaydi, lekin sababi/muddati aniqlanmasa
FOREVER = 4102444800.0        # muddatsiz cheklov belgisi (2100-yil)
RECHECK_EVERY = 6 * 3600   # soniya: kuzatuvdagilar faolligini avtomatik qayta tekshirish oralig'i
MAINTAIN_EVERY = 60     # soniya: akkauntlarni qayta ulash / accounts.json ni qayta o'qish
WATCH_FILE = "watch.json"
CFG_FILE = "config.json"
ACC_FILE = "accounts.json"     # {session: {label, claimed}}
AUTH_MODES = ("api_id", "api_hash", "phone", "code", "password")
MAX_ACCOUNTS = 5              # havzada ko'pi bilan nechta akkaunt (har biri o'z api_id/api_hash bilan)
SNIPER_SLOTS = 5              # sniper (username tekshirish/egallash) uchun akkaunt o'rinlari
POST_SLOTS = 5                # avto post uchun akkaunt o'rinlari
JOIN_DAILY_CAP = 10           # bitta akkaunt sutkada bot talabi bilan ko'pi bilan nechta kanal/guruhga qo'shiladi
JOIN_DELAY = (8, 25)          # qo'shilishdan oldingi tasodifiy pauza, soniya
GATE_WORDS = ("obuna", "a'zo", "azo", "qo'shil", "qoshil", "подпис", "вступ", "присоед", "join", "subscri", "kanal", "канал", "guruh", "группа")
ROLES = ("sniper", "post", "both")
ROLE_UZ = {"sniper": "🎯 Sniper", "post": "📣 Avto post", "both": "🎯📣 Ikkalasi"}
_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")      # Railway bergan ochiq domen (HTTPS)
# ochiq HTTPS manzil (Telegram faqat HTTPS qabul qiladi)
WEBAPP_URL = (os.environ.get("WEBAPP_URL") or (f"https://{_domain}" if _domain else "")).rstrip("/")
WEB_PORT = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "8080")   # Railway PORT beradi
WEB_HOST = os.environ.get("WEB_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_ON = bool(WEBAPP_URL and web)
# Seans va json fayllar doimiy diskda saqlanadi (Railway Volume ulangan bo'lsa o'zi topiladi)
DATA_DIR = os.environ.get("DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "")
if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.chdir(DATA_DIR)

VALID = re.compile(r"^[a-z][a-z0-9_]{3,30}[a-z0-9]$")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile",
    "Accept-Language": "en-US,en;q=0.9",
}
STATUS_RE = re.compile(
    r'tm-section-header-status\s+tm-status-\w+"[^>]*>\s*([^<]+?)\s*<'
)
STATUS_CLS_RE = re.compile(r'tm-status-(avail|sold|unavail|taken)\b')   # zaxira: sinf nomidan holat
_frag_warned = False
sem = asyncio.Semaphore(3)   # Fragment / t.me ga bir vaqtdagi so'rovlar


# ---------- fayllar (atomik yozish, zaxira nusxa, ruxsatlar) ----------
def secure(path):
    try:
        os.chmod(path, 0o600)
    except Exception as _e:
        log.debug("chmod bajarilmadi: %s", type(_e).__name__)


def harden():
    """Seans va sozlama fayllarini faqat egasi o'qiydigan qiladi."""
    for p in glob.glob("*.session*") + [WATCH_FILE, CFG_FILE, ACC_FILE, GROUPS_FILE, POSTS_FILE, BL_FILE, CONF_FILE]:
        if os.path.exists(p):
            secure(p)


def read_json(path):
    """Fayl yo'q bo'lsa {}. Buzilgan bo'lsa .bak dan o'qiydi; ikkalasi ham buzilgan bo'lsa
    to'xtaydi (jimgina bo'sh ma'lumot bilan ustiga yozib yubormaslik uchun)."""
    found = False
    for p in (path, path + ".bak"):
        if not os.path.exists(p):
            continue
        found = True
        try:
            with open(p) as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.error("%s buzilgan: %s", p, e)
    if found:
        raise RuntimeError(
            f"{path} va uning .bak nusxasi buzilgan. Faylni qo'lda tekshiring, bot to'xtatildi."
        )
    return {}


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    secure(tmp)
    if os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except Exception as _e:
            log.warning(".bak nusxa yaratilmadi: %s", type(_e).__name__)
    os.replace(tmp, path)   # atomik almashtirish


watch = {k: OWNER_ID for k in read_json(WATCH_FILE)}   # {username: OWNER_ID}
cfg = read_json(CFG_FILE)                              # {api_id, api_hash}


meta = {}                    # {username: faollik izohi}  (web sahifa uchun)
seen = {}                    # {username: oxirgi tekshiruv vaqti}
checked = {}                 # {username: faolligi oxirgi marta qachon qayta tekshirilgan}
events = deque(maxlen=50)    # (vaqt, matn)


def log_event(text):
    events.append((time.time(), text))


def save():
    write_json(WATCH_FILE, watch)


# ---------- akkauntlar havzasi (pool) ----------
class Acc:
    def __init__(self, session, label=""):
        self.session = session
        self.label = label
        self.claimed = None
        self.role = "both"   # sniper | post | both
        self.tg_id = None
        self.client = None
        self.auth = False
        self.retry_at = 0.0
        self.hooked = False
        self.spam = None   # {state: ask|until, until, asked}: @SpamBot cheklovi
        self.flood_msg = {}   # {tur: tugash vaqti}: tugaganda egasiga xabar beriladi
        self.sent = deque()   # oxirgi soatdagi post vaqtlari (soatlik limit uchun)
        self.joins = deque()  # oxirgi sutkadagi avto-qo'shilish vaqtlari
        self.join_block = 0.0 # qo'shilish FloodWait tugash vaqti
        self.join_seen = {}   # {username: vaqt}: bir havolaga qayta-qayta qo'shilmaslik
        self.join_lock = asyncio.Lock()
        self.slow = {"check": [1.0, 0.0], "resolve": [1.0, 0.0]}   # {tur: [koeffitsient, oxirgi o'zgarish]}: FloodWaitdan keyin sekinlashtirish
        self.block = {"check": 0.0, "resolve": 0.0, "claim": 0.0, "post": 0.0}   # FloodWait tugash vaqti
        self.last = {"check": 0.0, "resolve": 0.0, "post": 0.0}                   # oxirgi so'rov vaqti


accs = {}         # session -> Acc
removed = set()   # o'chirilgan seanslar (accounts.json dan qayta tiklanmasin)


def sync_accs():
    """accounts.json dagi yangi seanslarni (login.py qo'shgan) havzaga qo'shadi."""
    for s, m in read_json(ACC_FILE).items():
        if s in accs or s in removed or not isinstance(m, dict):
            continue
        a = Acc(s, m.get("label", ""))
        a.claimed = m.get("claimed")
        a.role = m.get("role") if m.get("role") in ROLES else "both"
        a.spam = m.get("spam")
        for k, v in (m.get("block") or {}).items():   # Telegram cheklovi qayta ishga tushsa ham eslab qolinadi
            if k in a.block:
                try:
                    a.block[k] = float(v)
                except (TypeError, ValueError):
                    continue
                if a.block[k] - time.time() >= 600:
                    a.flood_msg[k] = a.block[k]
        accs[s] = a


def save_accs():
    try:
        sync_accs()   # login.py yozgan yangi yozuvlarni yo'qotmaslik uchun
    except Exception as e:
        log.warning("accounts.json o'qilmadi: %s", e)
    now = time.time()
    write_json(ACC_FILE, {
        s: {"label": a.label, "claimed": a.claimed, "role": a.role,
            "block": {k: v for k, v in a.block.items() if v > now},
            "spam": a.spam}
        for s, a in accs.items()
    })


def load_accs():
    sync_accs()
    # login.py yaratgan asosiy seans
    if "sniper" not in accs and os.path.exists("sniper.session"):
        a = Acc("sniper", "asosiy")
        a.claimed = cfg.get("acct_claimed")
        accs["sniper"] = a
    save_accs()


def role_has(a, role):
    return a.role in (role, "both")


def live(role=None):
    ls = [a for a in accs.values() if a.auth and a.client]
    if role:
        ls = [a for a in ls if role_has(a, role)]
    return ls


def slots_used(exclude=None):
    items = [a for a in accs.values() if a is not exclude]
    return (sum(role_has(a, "sniper") for a in items), sum(role_has(a, "post") for a in items))


def role_ok(role, exclude=None):
    """Shu rolli yangi (yoki rolini o'zgartirayotgan) akkaunt uchun o'rin bormi."""
    s_, p_ = slots_used(exclude)
    if role_has_name(role, "sniper") and s_ >= SNIPER_SLOTS:
        return False
    if role_has_name(role, "post") and p_ >= POST_SLOTS:
        return False
    return True


def role_has_name(role, want):
    return role in (want, "both")


def pool_wait(kind, role="sniper"):
    """Barcha akkauntlar bloklangan bo'lsa, eng yaqin ochilishgacha soniya; aks holda 0."""
    ls = live(role)
    if not ls:
        return 0
    now = time.time()
    if any(a.block[kind] <= now for a in ls):
        return 0
    return min(a.block[kind] for a in ls) - now


def slow_factor(a, kind):
    """FloodWaitdan keyin pauza uzayadi, tinch o'tsa asta-sekin avvalgi holatga qaytadi."""
    st = a.slow.get(kind)
    if not st:
        return 1.0
    now = time.time()
    if st[0] > 1.0 and now - st[1] >= SLOW_RECOVER:
        st[0] = max(1.0, st[0] / SLOW_STEP)
        st[1] = now
    return st[0]


async def acquire(kind, delay, role="sniper"):
    """Bloklanmagan va eng kam ishlatilgan akkauntni qaytaradi (so'rovlar orasida delay saqlanadi).
    Hammasi bloklangan bo'lsa None."""
    while True:
        now = time.time()
        cands = [a for a in live(role) if a.block[kind] <= now]
        if not cands:
            return None
        a = min(cands, key=lambda x: x.last[kind])
        slot = max(now, a.last[kind] + delay * slow_factor(a, kind))
        a.last[kind] = slot
        if slot > now:
            await asyncio.sleep(slot - now)
        if a.auth and a.block[kind] <= time.time():
            return a


class PoolBlocked(Exception):
    def __init__(self, seconds):
        self.seconds = seconds


class AccountBusy(Exception):
    pass


class ClaimFailed(Exception):
    pass


DEAD_ERRORS = (errors.AuthKeyUnregisteredError, errors.SessionRevokedError)


def etxt(e):
    """Xato turi + matni (katta harflarda): Telethon xabarlari kodni o'z ichiga olmasligi mumkin."""
    return (type(e).__name__ + " " + str(e)).upper()


def get_creds(session=None):
    """Akkauntning o'z api_id/api_hash si (config.json > creds). Topilmasa eski umumiy kalit/muhit."""
    if session:
        try:
            c = (cfg.get("creds") or {})[session]
            return int(c["api_id"]), str(c["api_hash"])
        except Exception:
            pass
    try:
        return int(cfg["api_id"]), str(cfg["api_hash"])
    except Exception:
        pass
    try:
        return int(os.environ["API_ID"]), os.environ["API_HASH"]
    except Exception:
        return None


async def connect_acc(a):
    """True: kirilgan, False: seans avtorizatsiyadan o'tmadi, None: API ma'lumotlari yo'q.
    Tarmoq xatosida exception ko'taradi."""
    creds = get_creds(a.session)
    if not creds:
        return None
    if a.client is None:
        a.client = TelegramClient(a.session, *creds)
    if not a.client.is_connected():
        await a.client.connect()
    a.auth = await a.client.is_user_authorized()
    if a.auth and a.tg_id is None:
        me = await a.client.get_me()
        a.tg_id = me.id
    if a.auth:
        attach_handlers(a)
    secure(a.session + ".session")
    return a.auth


async def remove_acc(session):
    a = accs.pop(session, None)
    if not a:
        return
    removed.add(session)
    a.auth = False
    if a.client:
        try:
            await a.client.log_out()
        except Exception:
            try:
                await a.client.disconnect()
            except Exception as _e:
                log.debug("disconnect xatosi: %s", type(_e).__name__)
    try:
        os.remove(session + ".session")
    except FileNotFoundError:
        pass
    except OSError as _e:
        log.warning("seans fayli o'chirilmadi: %s", _e)
    if (cfg.get("creds") or {}).pop(session, None) is not None:
        write_json(CFG_FILE, cfg)
    save_accs()


async def dead(a):
    """Seansi yopilgan akkauntni havzadan olib tashlaydi va egasini xabardor qiladi."""
    label = a.label or a.session
    await remove_acc(a.session)
    await notify(app, OWNER_ID, f"⚠️ {label} seansi yopilgan, akkaunt olib tashlandi. 🔑 orqali qayta qo'shing.")


# ---------- kuzatuv ----------
def parse_names(text):
    names = []
    # faqat @ bilan boshlangan so'zlar (email ichidagi @ hisobga olinmaydi)
    for n in re.findall(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]+)", text):
        n = n.lower()
        if n not in names:
            names.append(n)
    return names


last_warn = {}


async def add_watch(name):
    watch[name] = OWNER_ID
    save()


async def drop(name):
    watch.pop(name, None)
    meta.pop(name, None)
    seen.pop(name, None)
    save()


async def notify(app, uid, text, force=False):
    log_event(text.replace("\n", " "))
    if not force and not text.startswith(IMPORTANT) and in_quiet(local_now()):
        quiet_buf.append((time.time(), text))   # jim rejim: muhim bo'lmagan xabarlar keyinroq bitta xabarda
        del quiet_buf[:-100]
        return
    try:
        await app.bot.send_message(uid, text)
    except Exception as e:
        log.warning("xabar yuborilmadi: %s", e)


async def warn(app, uid, key, text, every=600):
    """Bir xil ogohlantirishni 10 daqiqada bir martadan ko'p yubormaydi."""
    if time.time() - last_warn.get(key, 0) > every:
        last_warn[key] = time.time()
        await notify(app, uid, text)


KIND_NOUN = {"check": "username tekshirish", "resolve": "akkaunt qidirish", "claim": "kanal ochish", "post": "guruhga yozish"}
KIND_LABEL = {"check": "username tekshirishni", "resolve": "akkaunt qidirishni", "claim": "kanal ochishni", "post": "guruhga yozishni"}


async def set_block(a, kind, seconds):
    """FloodWait: akkauntni cheklangan deb belgilaydi, faylga yozadi va (uzoq bo'lsa) xabar beradi."""
    a.block[kind] = time.time() + seconds
    stats["floods"] += 1
    if kind in a.slow:
        a.slow[kind][0] = min(a.slow[kind][0] * SLOW_STEP, SLOW_MAX)
        a.slow[kind][1] = time.time()
    if seconds >= 60:
        save_accs()
    if seconds >= 600:
        a.flood_msg[kind] = a.block[kind]
        await warn(
            app, OWNER_ID, f"flood:{a.session}:{kind}",
            f"⏳ {a.label or a.session}: Telegram {KIND_LABEL[kind]} {fmt_wait(seconds)}ga cheklab qo'ydi. "
            "Web sahifada taymer bor.",
            every=3600,
        )


async def claim_with(a, name):
    """Username bo'shaganda kanal ochib o'rnatadi.
    Kanal ochish cheklangan bo'lsa va akkauntda username BO'LMASA, akkaunt usernamesiga o'rnatadi
    (mavjud usernameni hech qachon almashtirmaydi)."""
    c = a.client
    try:
        res = await c(CreateChannelRequest(title=name, about="", broadcast=True))
    except errors.UserRestrictedError:
        if a.claimed:
            raise AccountBusy()
        me = await c.get_me()
        if me.username:
            raise AccountBusy()
        await c(AccUpdate(name))
        a.claimed = name
        save_accs()
        return "akkaunt usernamesi"
    try:
        inp = await c.get_input_entity(res.chats[0])
    except Exception:
        try:
            await c(DeleteChannelRequest(res.chats[0]))
        except Exception as _e:
            log.warning("yetim kanal o'chirilmadi (qo'lda o'chirish kerak bo'lishi mumkin): %s", type(_e).__name__)
        raise
    try:
        await c(UpdateUsernameRequest(inp, name))
    except Exception:
        try:
            await c(DeleteChannelRequest(inp))
        except Exception as _e:
            log.warning("yetim kanal o'chirilmadi (qo'lda o'chirish kerak bo'lishi mumkin): %s", type(_e).__name__)
        raise
    return "kanal"


async def claim(name, first=None):
    """Avval username bo'shaganini aniqlagan akkaunt, keyin qolganlari bilan urinadi.
    Username'ga oid xatolar (band/yaroqsiz) darhol ko'tariladi, akkauntga oid xatolarda
    keyingi akkauntga o'tiladi."""
    order = ([first] if first and first.auth and role_has(first, "sniper") else []) + [a for a in live("sniper") if a is not first]
    err = None
    for a in order:
        if a.block["claim"] > time.time():
            continue
        try:
            return await claim_with(a, name)
        except AccountBusy as e:
            err = e
        except errors.FloodWaitError as e:
            await set_block(a, "claim", e.seconds)
            err = ClaimFailed(f"Telegram kanal ochishni {fmt_wait(e.seconds)}ga cheklagan")
        except DEAD_ERRORS:
            await dead(a)
        except Exception as e:
            t = etxt(e)
            if any(k in t for k in ("OCCUPIED", "PURCHASE", "INVALID")):
                raise
            if "TOOMUCH" in t or "TOO_MUCH" in t:
                err = ClaimFailed(
                    "ommaviy kanallar limiti to'lgan. Eski kanallardan birini yopiq qiling yoki o'chiring"
                )
            else:
                err = ClaimFailed(type(e).__name__)
    if isinstance(err, (AccountBusy, ClaimFailed)):
        raise err
    raise ClaimFailed("hech bir akkaunt bilan egallab bo'lmadi")


async def sniper_cycle(app):
    if not live("sniper") or not watch:
        await asyncio.sleep(3)
        return
    w = pool_wait("check")
    if w > 0:
        await asyncio.sleep(min(w + 1, 60))
        return
    for name in list(watch):
        if name not in watch:
            continue
        a = await acquire("check", CHECK_DELAY)
        if a is None:
            return
        try:
            free = await a.client(AccCheck(name))
            seen[name] = time.time()
            stats["checks"] += 1
            if free:
                where = await claim(name, a)
                stats["claimed"] += 1
                await drop(name)
                await notify(app, OWNER_ID, f"🎉 @{name} egallandi ({where})!\nt.me/{name}")
        except errors.FloodWaitError as e:
            log.warning("FloodWait (%s): %s soniya", a.session, e.seconds)
            await set_block(a, "check", e.seconds)
            continue   # boshqa akkaunt bilan davom etamiz
        except DEAD_ERRORS:
            await dead(a)
            continue
        except AccountBusy:
            await warn(
                app, OWNER_ID, name,
                f"⚠️ @{name} BO'SH, lekin kanal ochish cheklangan va akkaunt usernamesiga "
                "o'rnatib bo'lmaydi (band yoki mavjud usernameni almashtirmayman). "
                "Tezroq o'zingiz oling!",
            )
        except ClaimFailed as e:
            await warn(app, OWNER_ID, f"claim:{name}", f"⚠️ @{name} BO'SH, lekin egallab bo'lmadi: {e}")
        except Exception as e:
            t = etxt(e)
            if "OCCUPIED" in t or "PURCHASE" in t:
                pass  # hali band, Fragment'da sotuvda yoki boshqa birov ulgurdi
            elif "INVALID" in t:
                await drop(name)
                await notify(app, OWNER_ID, f"❌ @{name} yaroqsiz, kuzatuvdan olindi.")
            else:
                log.warning("@%s: %s", name, e)


async def sniper_loop(app):
    while True:
        try:
            await sniper_cycle(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("sniper_loop xatosi")
            await asyncio.sleep(5)


async def maintain_loop(app):
    """Yangi seanslarni (login.py) qo'shadi, ulanmagan akkauntlarni qayta ulaydi."""
    while True:
        await asyncio.sleep(MAINTAIN_EVERY)
        try:
            sync_accs()
        except Exception as e:
            log.warning("accounts.json o'qilmadi: %s", e)
        now = time.time()
        for a in list(accs.values()):
            for k, until in list(a.flood_msg.items()):
                if now < until:
                    continue
                if a.block[k] > now:      # cheklov uzaytirilgan: yangi muddatni kutamiz
                    a.flood_msg[k] = a.block[k]
                else:
                    del a.flood_msg[k]
                    await notify(
                        app, OWNER_ID,
                        f"✅ {a.label or a.session}: {KIND_NOUN[k]} cheklovi tugadi, bot davom etmoqda.",
                    )
        for a in list(accs.values()):
            if a.auth or time.time() < a.retry_at:
                continue
            try:
                ok = await connect_acc(a)
            except Exception as e:
                log.warning("%s qayta ulanmadi: %s", a.session, e)
                a.retry_at = time.time() + 120
                continue
            if ok is False:
                a.retry_at = time.time() + 300
                await warn(
                    app, OWNER_ID, "unauth:" + a.session,
                    f"⚠️ {a.label or a.session} seansi avtorizatsiyadan o'tmadi. Davom etsa, "
                    "📱 Akkauntlar orqali o'chirib, qayta qo'shing.",
                    every=6 * 3600,
                )


# ---------- username tekshiruvchi ----------
async def fragment_status(client, name):
    f = None
    for i in range(3):
        f = await client.get(f"https://fragment.com/username/{name}", follow_redirects=True)
        if f.status_code != 429:
            break
        await asyncio.sleep(2 * (i + 1))
    if f is None or f.status_code != 200:
        return ""
    m = STATUS_RE.search(f.text)
    if m:
        return m.group(1).strip()
    m = STATUS_CLS_RE.search(f.text)
    if m:
        return {"avail": "available", "sold": "sold", "unavail": "unavailable", "taken": "taken"}[m.group(1)]
    global _frag_warned
    if not _frag_warned:
        _frag_warned = True
        log.warning("Fragment sahifasi formati o'zgargan bo'lishi mumkin: holat topilmadi (%s)", name)
    return ""


async def tg_available(name):
    """Telegramning o'zidan so'raydi (account.checkUsername), havzadagi akkauntlar navbat bilan.
    ('free'|'taken'|'sale'|'invalid'|'unknown', izoh)"""
    for _ in range(max(1, len(accs))):
        a = await acquire("check", VERIFY_DELAY)
        if a is None:
            break
        try:
            ok = await a.client(AccCheck(name))
            return ("free", "") if ok else ("taken", "")
        except errors.FloodWaitError as e:
            await set_block(a, "check", e.seconds)
            continue
        except DEAD_ERRORS:
            await dead(a)
            continue
        except Exception as e:
            t = etxt(e)
            if "PURCHASE" in t:
                return "sale", ""
            if "OCCUPIED" in t:
                return "taken", ""
            if "INVALID" in t:
                return "invalid", ""
            return "unknown", type(e).__name__
    return "unknown", f"Telegram tekshiruvni yana {fmt_wait(pool_wait('check'))} cheklagan"


async def check(client, name, verify=None):
    if not VALID.match(name) or "__" in name:
        return f"❌ @{name} — format yaroqsiz"
    try:
        # Veb tekshiruv (Fragment + t.me) — sem faqat shu qism uchun
        async with sem:
            try:
                st = await fragment_status(client, name)
                s = st.lower()

                if s and "unavailable" not in s:
                    if "sold" in s:
                        return f"🔒 @{name} — NFT, sotilgan"
                    if "avail" in s or "auction" in s or "sale" in s:
                        return f"💎 @{name} — Fragment'da sotuvda ({st})"

                r = await client.get(f"https://t.me/{name}")
                if "tgme_page_title" in r.text:
                    return f"👤 @{name} — band (akkaunt bor)"

                if s and "unavailable" not in s and "taken" not in s:
                    return f"❓ @{name} — Fragment holati: {st}"
            finally:
                await asyncio.sleep(0.5)

        # Telegramdan tasdiqlash (sem tashqarisida: kutish boshqa so'rovlarni to'xtatmaydi)
        if verify is None:
            return f"❔ @{name} — ehtimol bo'sh (Telegram bilan tasdiqlanmadi)"
        if verify["left"] <= 0:
            return (f"❔ @{name} — ehtimol bo'sh (bir xabarda faqat {MAX_VERIFY} tasi "
                    "Telegramdan tasdiqlanadi)")
        verify["left"] -= 1
        st2, info = await tg_available(name)
        if st2 == "taken":
            return f"🚫 @{name} — Telegram bo'sh demaydi (band, ban yoki zaxirada)"
        if st2 == "invalid":
            return f"🚫 @{name} — Telegram yaroqsiz deydi (ban yoki zaxirada)"
        if st2 == "sale":
            return f"💎 @{name} — Fragment'da sotuvda (Telegram: sotib olish mumkin)"
        if st2 == "unknown":
            return f"❔ @{name} — ehtimol bo'sh, Telegram tasdiqlamadi ({info})"
        return f"✅ @{name} — BO'SH (Telegram tasdiqladi)"
    except Exception as e:
        return f"⚠️ @{name} — xato: {type(e).__name__}"


# ---------- akkauntga kirish (bot ichida) ----------
async def wipe(msg):
    """Maxfiy ma'lumot yozilgan xabarni chatdan o'chiradi."""
    try:
        await msg.delete()
    except Exception as _e:
        log.warning("maxfiy xabar chatdan o'chirilmadi: %s", type(_e).__name__)


def new_session():
    return f"acc_{int(time.time())}"


async def drop_login(ud, full=False):
    """Tugallanmagan kirishni tozalaydi. full=True: kiritilgan api_id/api_hash ham o'chadi."""
    if full:
        for k in ("api_id", "api_hash", "lrole"):
            ud.pop(k, None)
    lc = ud.pop("lc", None)
    sess = ud.pop("lsess", None)
    if lc:
        try:
            await lc.disconnect()
        except Exception as _e:
            log.debug("disconnect xatosi: %s", type(_e).__name__)
    if sess and sess not in accs:
        try:
            os.remove(sess + ".session")
        except FileNotFoundError:
            pass
        except OSError as _e:
            log.warning("seans fayli o'chirilmadi: %s", _e)
    for k in ("phone", "hash", "lcreds"):
        ud.pop(k, None)


async def begin_login(msg, ctx):
    if len(accs) >= MAX_ACCOUNTS:
        await msg.reply_text(
            f"Akkauntlar limiti to'ldi ({MAX_ACCOUNTS} ta). Yangisini qo'shish uchun "
            "📱 Akkauntlar orqali birortasini o'chiring.",
            reply_markup=menu(),
        )
        return
    await drop_login(ctx.user_data, full=True)
    s_, p_ = slots_used()
    btns = []
    if role_ok("sniper"):
        btns.append([InlineKeyboardButton(f"🎯 Sniper ({s_}/{SNIPER_SLOTS})", callback_data="lrole:sniper")])
    if role_ok("post"):
        btns.append([InlineKeyboardButton(f"📣 Avto post ({p_}/{POST_SLOTS})", callback_data="lrole:post")])
    if role_ok("both"):
        btns.append([InlineKeyboardButton("🎯📣 Ikkalasi ham", callback_data="lrole:both")])
    if not btns:
        await msg.reply_text(
            f"Sniper ({s_}/{SNIPER_SLOTS}) va avto post ({p_}/{POST_SLOTS}) o'rinlari to'lgan. "
            "📱 Akkauntlar orqali birortasini o'chiring.",
            reply_markup=menu(),
        )
        return
    await msg.reply_text(
        f"Akkaunt {len(accs) + 1}/{MAX_ACCOUNTS}. Bu akkaunt nima uchun ishlatiladi?\n"
        "🎯 Sniper: username tekshirish va egallash\n"
        "📣 Avto post: guruhlarga habar yuborish\n"
        "Birini tanlang:",
        reply_markup=InlineKeyboardMarkup(btns),
    )


async def ask_api(msg, ctx, role):
    ctx.user_data["lrole"] = role
    ctx.user_data["mode"] = "api_id"
    await msg.reply_text(
        f"Rol: {ROLE_UZ[role]}.\n"
        "Har bir akkaunt uchun alohida api_id va api_hash kerak: "
        "my.telegram.org → API development tools (shu akkauntning telefon raqami bilan kiring).\n\n"
        "Avval api_id raqamini yuboring."
    )


_CODE_TYPES = {
    "SentCodeTypeApp": "Telegram ilovasi ichiga (rasmiy «Telegram» chati)",
    "SentCodeTypeSms": "SMS orqali",
    "SentCodeTypeCall": "telefon qo'ng'irog'i orqali",
    "SentCodeTypeFlashCall": "qisqa qo'ng'iroq orqali",
    "SentCodeTypeMissedCall": "javobsiz qo'ng'iroq orqali (raqamning oxirgi raqamlari kod)",
    "SentCodeTypeEmailCode": "elektron pochta orqali",
}


def code_where(t):
    return _CODE_TYPES.get(type(t).__name__, "Telegram tanlagan usulda") if t is not None else "noma'lum usulda"


async def _discard_login(lc, session):
    try:
        await lc.log_out()
    except Exception as _e:
        log.debug("log_out xatosi: %s", type(_e).__name__)
    try:
        os.remove(session + ".session")
    except FileNotFoundError:
        pass
    except OSError as _e:
        log.warning("seans fayli o'chirilmadi: %s", _e)


async def register_login(lc, session, role, creds):
    """Kirib bo'lingan klientni havzaga qo'shadi (bot ham, web ham shuni ishlatadi).
    Qaytaradi: (Acc yoki None, xato matni)."""
    me = await lc.get_me()
    if len(accs) >= MAX_ACCOUNTS or not role_ok(role):
        await _discard_login(lc, session)
        return None, f"Akkauntlar limiti to'ldi ({MAX_ACCOUNTS} ta) yoki bu rol uchun o'rin yo'q."
    if any(a.tg_id == me.id for a in accs.values()):
        await _discard_login(lc, session)
        return None, "Bu akkaunt allaqachon qo'shilgan."
    label = (me.first_name or "").strip()
    if me.username:
        label += f" @{me.username}"
    if creds:
        cfg.setdefault("creds", {})[session] = {"api_id": creds[0], "api_hash": creds[1]}
        write_json(CFG_FILE, cfg)
    a = Acc(session, label or session)
    a.role = role
    a.client, a.auth, a.tg_id = lc, True, me.id
    accs[session] = a
    attach_handlers(a)
    removed.discard(session)
    save_accs()
    secure(session + ".session")
    return a, ""


async def finish_login(msg, ctx):
    ud = ctx.user_data
    lc = ud.pop("lc")
    session = ud.pop("lsess")
    for k in ("phone", "hash", "mode"):
        ud.pop(k, None)
    creds = ud.pop("lcreds", None)
    ud.pop("api_id", None)
    ud.pop("api_hash", None)
    role = ud.pop("lrole", "both")
    a, err = await register_login(lc, session, role, creds)
    if not a:
        await msg.reply_text(err, reply_markup=menu())
        return
    await msg.reply_text(
        f"✅ Ulandi: {a.label} ({ROLE_UZ[role]})\n"
        "Telegram → Sozlamalar → Qurilmalar bo'limida yangi seans ko'rinadi.\n"
        f"Havzada jami {len(live())} ta akkaunt (limit {MAX_ACCOUNTS}).",
        reply_markup=menu(),
    )


async def auth_step(update: Update, ctx: ContextTypes.DEFAULT_TYPE, mode):
    msg = update.message
    text = msg.text.strip()
    ud = ctx.user_data

    if mode == "api_id":
        if not text.isdigit():
            await msg.reply_text("api_id faqat raqamlardan iborat. Qayta yuboring.")
            return
        ud["api_id"] = int(text)
        ud["mode"] = "api_hash"
        await msg.reply_text("Endi api_hash ni yuboring (32 ta harf-raqam).")

    elif mode == "api_hash":
        await wipe(msg)
        if not re.fullmatch(r"[0-9a-fA-F]{32}", text) or "api_id" not in ud:
            await msg.reply_text("api_hash 32 ta harf-raqamdan iborat. Qayta yuboring.")
            return
        ud["api_hash"] = text
        ud["mode"] = "phone"
        await msg.reply_text("Qabul qilindi ✅\nEndi shu akkauntning telefon raqamini yuboring (+998901234567).")

    elif mode == "phone":
        await wipe(msg)
        phone = "+" + re.sub(r"\D", "", text)
        if "api_id" not in ud or "api_hash" not in ud:
            ud["mode"] = "api_id"
            await msg.reply_text("API ma'lumotlari yo'q. api_id ni yuboring.")
            return
        creds = (int(ud["api_id"]), str(ud["api_hash"]))
        await drop_login(ud)
        session = new_session()
        client = TelegramClient(session, *creds)
        ud["lc"], ud["lsess"], ud["lcreds"] = client, session, creds
        try:
            await client.connect()
            sent = await client.send_code_request(phone)
        except errors.PhoneNumberInvalidError:
            await drop_login(ud)
            await msg.reply_text("Raqam noto'g'ri. +998901234567 shaklida yuboring.")
            return
        except errors.ApiIdInvalidError:
            await drop_login(ud, full=True)
            ud["mode"] = "api_id"
            await msg.reply_text("api_id/api_hash noto'g'ri ekan. api_id ni qayta yuboring.")
            return
        except errors.FloodWaitError as e:
            await drop_login(ud)
            await msg.reply_text(f"Juda ko'p urinish. {fmt_wait(e.seconds)}dan keyin qayta urining.")
            return
        except Exception as e:
            await drop_login(ud)
            await msg.reply_text(f"Xato: {type(e).__name__}")
            return
        secure(session + ".session")
        ud.update(phone=phone, hash=sent.phone_code_hash, mode="code")
        await msg.reply_text(
            f"Kod yuborildi ✅ — {code_where(getattr(sent, 'type', None))}.\n\n"
            "Kodni raqamlar orasiga bo'sh joy qo'yib yuboring, masalan:\n"
            "1 2 3 4 5\n\n"
            "(Oddiy yozsangiz, Telegram kodni bloklab qo'yadi.)"
        )

    elif mode == "code":
        await wipe(msg)
        lc = ud.get("lc")
        if lc is None or "phone" not in ud or "hash" not in ud:
            ud["mode"] = "phone"
            await msg.reply_text("Seans eskirdi. Telefon raqamni qayta yuboring.")
            return
        code = re.sub(r"\D", "", text)
        try:
            await lc.sign_in(ud["phone"], code, phone_code_hash=ud["hash"])
        except errors.SessionPasswordNeededError:
            ud["mode"] = "password"
            await msg.reply_text("2 bosqichli parolni yuboring.")
            return
        except errors.PhoneCodeInvalidError:
            await msg.reply_text("Kod noto'g'ri. Qayta yuboring (1 2 3 4 5).")
            return
        except errors.PhoneCodeExpiredError:
            await drop_login(ud)
            ud["mode"] = "phone"
            await msg.reply_text(
                "Kod eskirdi yoki bloklandi. Telefon raqamni qayta yuboring, "
                "kodni esa bo'sh joy bilan yozing."
            )
            return
        except errors.FloodWaitError as e:
            await msg.reply_text(f"Juda ko'p urinish. {fmt_wait(e.seconds)}dan keyin qayta urining.")
            return
        except Exception as e:
            await msg.reply_text(f"Xato: {type(e).__name__}")
            return
        await finish_login(msg, ctx)

    elif mode == "password":
        await wipe(msg)
        lc = ud.get("lc")
        if lc is None:
            ud["mode"] = "phone"
            await msg.reply_text("Seans eskirdi. Telefon raqamni qayta yuboring.")
            return
        try:
            await lc.sign_in(password=text)
        except errors.PasswordHashInvalidError:
            await msg.reply_text("Parol noto'g'ri. Qayta yuboring.")
            return
        except errors.FloodWaitError as e:
            await msg.reply_text(f"Juda ko'p urinish. {fmt_wait(e.seconds)}dan keyin qayta urining.")
            return
        except Exception as e:
            await msg.reply_text(f"Xato: {type(e).__name__}")
            return
        await finish_login(msg, ctx)


# ---------- yordamchilar ----------
KB = {
    "🔑 Akkaunt qo'shish": "login",
    "🎯 Kuzatuvga qo'shish": "add",
    "📋 Ro'yxat": "list",
    "🗑 Tozalash": "clear",
    "📱 Akkauntlar": "accs",
    "🌐 Web kuzatuv": "web",
    "📣 Post matni": "ptext",
    "👥 Guruhlar": "groups",
    "⏱ Kechikish": "delay",
    "▶️ Avto post": "ptoggle",
    "🚫 Blok ro'yxati": "bl",
    "⚙️ Sozlamalar": "settings",
}


def menu():
    """Pastdagi doimiy klaviatura (Telegramdagi ⊞ tugmasi bilan ochiladi/yopiladi)."""
    rows = [
        ["🔑 Akkaunt qo'shish", "🎯 Kuzatuvga qo'shish"],
        ["📋 Ro'yxat", "🗑 Tozalash"],
        ["📣 Post matni", "👥 Guruhlar"],
        ["⏱ Kechikish", "▶️ Avto post", "⚙️ Sozlamalar"],
        ["📱 Akkauntlar", "🚫 Blok ro'yxati"] + (["🌐 Web kuzatuv"] if WEB_ON else []),
    ]
    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, is_persistent=True, input_field_placeholder="Xabar"
    )


def fmt_wait(sec):
    sec = int(sec)
    if sec < 60:
        return f"{sec} soniya"
    h, m = sec // 3600, (sec % 3600) // 60
    return f"{h} soat {m} daqiqa" if h else f"{m} daqiqa"


def chunk_lines(lines, limit=4000):
    """Telegram xabar limiti (4096): qatorlar bo'yicha bo'laklarga bo'ladi."""
    chunks, cur = [], ""
    for line in lines:
        line = line[:limit - 1]
        if cur and len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur:
        chunks.append(cur)
    return chunks or ["—"]


async def send_chunks(msg, update, lines):
    chunks = chunk_lines(lines)
    await msg.edit_text(chunks[0].rstrip())
    for ch in chunks[1:]:
        await update.message.reply_text(ch.rstrip())


# ---------- akkaunt faolligi (keshli) ----------
inactive_cache = {}   # username -> (vaqt, uzoq_kirmagan, izoh)


def cache_get(name):
    hit = inactive_cache.get(name)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit
    return None


def cache_put(name, res):
    if len(inactive_cache) >= CACHE_MAX:
        cutoff = time.time() - CACHE_TTL
        for k in [k for k, v in inactive_cache.items() if v[0] < cutoff]:
            del inactive_cache[k]
        if len(inactive_cache) >= CACHE_MAX:
            inactive_cache.clear()
    inactive_cache[name] = (time.time(), *res)


async def pool_entity(name):
    """Username bo'yicha entity: havzadagi akkauntlar navbat bilan, FloodWait bo'lsa keyingisi."""
    for _ in range(max(1, len(accs))):
        a = await acquire("resolve", RESOLVE_DELAY)
        if a is None:
            break
        try:
            return await a.client.get_entity(name)
        except errors.FloodWaitError as e:
            await set_block(a, "resolve", e.seconds)
        except DEAD_ERRORS:
            await dead(a)
    raise PoolBlocked(pool_wait("resolve"))


async def inactive_info(name):
    """(uzoq_kirmagan, izoh). Faqat oddiy akkauntlar uchun; bot/kanal -> False.
    Telegram username qidirishni qattiq cheklaydi, shuning uchun natija keshlanadi
    (topilmadi ham keshlanadi)."""
    hit = cache_get(name)
    if hit:
        return hit[1], hit[2]
    try:
        e = await pool_entity(name)
    except (ValueError, errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
        cache_put(name, (False, ""))
        return False, ""
    res = (False, "")
    if isinstance(e, T.User) and not e.bot and not e.deleted:
        st = e.status
        if st is None or isinstance(st, T.UserStatusEmpty):
            if WATCH_LONG_AGO:
                res = (True, "uzoq vaqt oldin faol bo'lgan (1 oydan ko'p, aniq muddat noma'lum)")
        elif isinstance(st, T.UserStatusOffline):
            wo = st.was_online
            if wo.tzinfo is None:
                wo = wo.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - wo).days
            if days >= INACTIVE_DAYS:
                res = (True, f"oxirgi faollik: {wo:%Y-%m-%d}, {days} kun oldin")
    cache_put(name, res)
    return res


def describe_entity(e):
    """Akkaunt holatini qisqa matnda qaytaradi (tarmoqsiz)."""
    if isinstance(e, T.User):
        if e.bot:
            return "bot (inaktivlik bilan o'chmaydi)"
        st = e.status
        if isinstance(st, T.UserStatusOnline):
            return "akkaunt, hozir onlayn"
        if isinstance(st, T.UserStatusOffline):
            return f"akkaunt, oxirgi faollik: {st.was_online:%Y-%m-%d}"
        if isinstance(st, T.UserStatusRecently):
            return "akkaunt, yaqinda faol (yoki yashirilgan)"
        if isinstance(st, T.UserStatusLastWeek):
            return "akkaunt, 1 hafta ichida faol"
        if isinstance(st, T.UserStatusLastMonth):
            return "akkaunt, 1 oy ichida faol"
        return "akkaunt, uzoq vaqt oldin faol bo'lgan"
    return "kanal/guruh (inaktivlik bilan o'chmaydi)"


def is_active_entity(e):
    """Oddiy akkaunt yaqinda faol bo'lgan bo'lsa True: onlayn, yaqinda, 1 hafta/oy ichida yoki
    oxirgi faollik INACTIVE_DAYS dan yangi. Bot, kanal va guruhlar hisobga olinmaydi."""
    if not isinstance(e, T.User) or e.bot or e.deleted:
        return False
    st = e.status
    if isinstance(st, (T.UserStatusOnline, T.UserStatusRecently, T.UserStatusLastWeek, T.UserStatusLastMonth)):
        return True
    if isinstance(st, T.UserStatusOffline):
        wo = st.was_online
        if wo.tzinfo is None:
            wo = wo.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - wo).days < INACTIVE_DAYS
    return False


async def check_activity(name):
    """(izoh, faolmi). Telegram javob bermasa (None, False)."""
    try:
        e = await pool_entity(name)
    except (ValueError, errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
        return "hozir akkaunt topilmadi", False
    except Exception:
        return None, False
    return describe_entity(e), is_active_entity(e)


async def describe(name):
    """Username kimniki ekanini va oxirgi faolligini qisqa matnda qaytaradi."""
    info, _ = await check_activity(name)
    return info or "holat aniqlanmadi"


# ---------- guruhlarga avto post ----------
posts = read_json(POSTS_FILE) or {}
posts.setdefault("texts", [])
posts.setdefault("on", False)
posts.setdefault("gap", DEFAULT_GAP)          # habarlar orasida (soniya)
posts["gap"] = max(posts["gap"], MIN_GAP)     # eski saqlangan qisqa pauzalar ham 40 soniyagacha ko'tariladi
posts["cycle"] = max(posts.get("cycle", DEFAULT_CYCLE), MIN_CYCLE)
posts.setdefault("cycle", DEFAULT_CYCLE)      # tsikllar orasida (soniya)
posts.setdefault("next_cycle", 0.0)           # keyingi tsikl boshlanish vaqti
posts.setdefault("from", 9)
posts.setdefault("to", 22)
groups = read_json(GROUPS_FILE)    # {chat_id(str): guruh}

PAUSE_UZ = {
    "ban": "ban", "mute": "mute", "warn": "ogohlantirish (warn)",
    "slow": "sekin rejim", "write": "yozish taqiqlangan", "left": "guruhdan chiqarilgan",
}
MOD_RE = {
    "ban": re.compile(r"\bban(?:ned)?\b|\bбан|заблок|забанен|bloklan|taqiqlan", re.I),
    "mute": re.compile(r"\bmut(?:e|ed)?\b|\bмут|ограничен|restrict", re.I),
    "warn": re.compile(r"warn|\bвар[нм]|предупрежд|ogohlantir", re.I),
}
DUR_RE = re.compile(
    r"(\d+)\s*(daq\w*|мин\w*|min(?:ute)?s?|m|soat\w*|hours?|hrs?|час\w*|h|ч|kun\w*|days?|дн\w*|ден|сут\w*|d|hafta\w*|weeks?|нед\w*|soniya\w*|sek\w*|sec(?:ond)?s?|сек\w*|s)\b",
    re.I,
)
GROUP_RE = re.compile(r"(?:https?://)?t\.me/([A-Za-z][A-Za-z0-9_]{3,})|@([A-Za-z][A-Za-z0-9_]{3,})")


def save_posts():
    write_json(POSTS_FILE, posts)


def save_groups():
    write_json(GROUPS_FILE, groups)


def new_group(chat_id, title, session, username=None):
    return {
        "id": chat_id, "title": title or str(chat_id), "user": username, "acc": session,
        "enabled": True, "pause_until": 0.0, "kind": "", "notify_resume": False,
        "next_at": time.time() + random.uniform(30, 300), "last_post": 0.0, "sent": 0, "ti": 0,
    }


def add_group(g):
    groups[str(g["id"])] = g
    save_groups()


def until_from_rights(rights):
    """ChatBannedRights -> cheklov tugash vaqti (epoch). Muddatsiz yoki 366 kundan uzun -> FOREVER."""
    d = getattr(rights, "until_date", None)
    if not d:
        return FOREVER
    ts = d.timestamp()
    return FOREVER if ts - time.time() > 366 * 86400 else ts


def rights_kind(rights):
    """Matn yuborishni to'sadigan cheklov turi: 'ban' | 'mute' | None (faqat media cheklangan bo'lsa)."""
    if getattr(rights, "view_messages", False):
        return "ban"
    if getattr(rights, "send_messages", False) or getattr(rights, "send_plain", False):
        return "mute"
    return None


def parse_duration(text):
    m = DUR_RE.search(text)
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2).lower()
    if u.startswith(("daq", "min", "мин")) or u == "m":
        return n * 60
    if u.startswith(("soat", "hour", "hr", "час")) or u in ("h", "ч"):
        return n * 3600
    if u.startswith(("kun", "day", "дн", "ден", "сут")) or u == "d":
        return n * 86400
    if u.startswith(("hafta", "week", "нед")):
        return n * 7 * 86400
    if u.startswith(("soniya", "sek", "sec", "сек")) or u == "s":
        return n
    return None


def parse_moderation(text):
    """Guruhdagi xabardan (ban/mute/warn) turini va muddatini aniqlaydi. Muddat aytilmasa WARN_PAUSE."""
    t = text.lower()
    for kind in ("ban", "mute", "warn"):
        if MOD_RE[kind].search(t):
            return kind, parse_duration(t) or iv("warn_pause")
    return None, 0


async def member_state(a, ent):
    """'ok' | 'notmember' | (tugash_vaqti, tur) -- akkauntning guruhdagi holati."""
    try:
        r = await a.client(GetParticipantRequest(ent, "me"))
    except errors.UserNotParticipantError:
        return "notmember"
    except Exception as _e:
        log.warning("member_state xatosi: %s", type(_e).__name__)
        return "ok"
    p = r.participant
    if isinstance(p, T.ChannelParticipantBanned):
        k = rights_kind(p.banned_rights)
        if k:
            return until_from_rights(p.banned_rights), k
    if isinstance(p, T.ChannelParticipantLeft):
        return "notmember"
    return "ok"


async def set_pause(g, until, kind, source=""):
    """Guruhga yozishni `until` gacha to'xtatadi (faqat uzaytiradi, qisqartirmaydi) va egasiga xabar beradi."""
    now = time.time()
    if until <= max(g["pause_until"], now):
        return
    g["pause_until"] = until
    g["kind"] = kind
    stats["pauses"] += 1
    g["notify_resume"] = until < FOREVER
    if until < FOREVER:
        g["next_at"] = max(g["next_at"], until + random.uniform(60, 300))
        tail = f"{fmt_wait(until - now)} yozmayman"
    else:
        tail = "muddatsiz. 👥 Guruhlar orqali o'zingiz qayta yoqasiz"
    save_groups()
    await notify(app, OWNER_ID, f"⛔ {g['title']}: {PAUSE_UZ.get(kind, kind)}{source}. {tail}.")


async def on_my_participant(g, new):
    """Telegram bu guruhdagi a'zoligimiz o'zgarganini bildirdi (mute/ban/chiqarish yoki cheklov olib tashlandi)."""
    now = time.time()
    if isinstance(new, T.ChannelParticipantBanned):
        k = rights_kind(new.banned_rights)
        if k:
            await set_pause(g, until_from_rights(new.banned_rights), k, " (Telegram xabari)")
            return
    if new is None or isinstance(new, T.ChannelParticipantLeft):
        await set_pause(g, FOREVER, "left")
        return
    if g["pause_until"] > now and g["kind"] in ("ban", "mute", "left", "write"):
        g["pause_until"] = 0.0
        g["notify_resume"] = False
        g["next_at"] = max(g["next_at"], now + random.uniform(60, 300))
        save_groups()
        await notify(app, OWNER_ID, f"✅ {g['title']}: cheklov olib tashlandi, yozish davom etadi.")


def gate_targets(msg):
    """Bot xabaridan (tugma yoki matn) ochiq t.me/username havolalarini topadi. Botlarga havola olinmaydi."""
    urls = []
    try:
        for row in (msg.buttons or []):
            for b in row:
                if getattr(b, "url", None):
                    urls.append(b.url)
    except Exception as _e:
        log.debug("tugmalardan havola olinmadi: %s", type(_e).__name__)
    try:
        for ent, _ in (msg.get_entities_text() or []):
            if isinstance(ent, T.MessageEntityTextUrl):
                urls.append(ent.url)
    except Exception as _e:
        log.debug("matn havolalari olinmadi: %s", type(_e).__name__)
    urls.append(msg.raw_text or "")
    out = []
    for u in urls:
        for a1, a2 in GROUP_RE.findall(u):
            n = (a1 or a2).lower()
            if n in ("joinchat", "addstickers", "addemoji", "share", "proxy", "socks", "boost") or n.endswith("bot"):
                continue
            if n not in out:
                out.append(n)
    return out[:3]


async def sender_is_admin(a, event):
    """Xabar yuborgan odam/bot shu guruhda admin (yoki egasi) bo'lsa True. Xato bo'lsa False (xavfsiz tomon)."""
    try:
        chat = await event.get_input_chat()
        who = await event.get_input_sender()
        r = await a.client(GetParticipantRequest(chat, who))
        return isinstance(r.participant, (T.ChannelParticipantAdmin, T.ChannelParticipantCreator))
    except Exception as _e:
        log.debug("admin tekshiruvi bajarilmadi: %s", type(_e).__name__)
        return False


async def autojoin(a, g, msg):
    """Guruhdagi bot (obuna bo'ling / qo'shiling) deb so'rasa, shu ochiq kanal/guruhga qo'shiladi.
    Guruh bo'lsa, postlar ro'yxatiga ham qo'shadi. Sutkalik limit va pauzalar bilan."""
    try:
        text = (msg.raw_text or "").lower()
        labels = ""
        try:
            labels = " ".join((b.text or "") for row in (msg.buttons or []) for b in row).lower()
        except Exception as _e:
            log.debug("tugma matni olinmadi: %s", type(_e).__name__)
        if not any(w in text or w in labels for w in GATE_WORDS):
            return
        targets = gate_targets(msg)
        if not targets:
            return
        async with a.join_lock:
            for name in targets:
                now = time.time()
                if now - a.join_seen.get(name, 0) < 6 * 3600 or now < a.join_block:
                    continue
                while a.joins and a.joins[0] < now - 86400:
                    a.joins.popleft()
                if len(a.joins) >= JOIN_DAILY_CAP:
                    await warn(app, OWNER_ID, f"joincap:{a.session}",
                               f"⚠️ {a.label or a.session}: bugungi avto-qo'shilish limiti ({JOIN_DAILY_CAP}) tugadi, "
                               f"{g['title']} dagi bot talabi (@{name}) bajarilmadi.", every=6 * 3600)
                    return
                a.join_seen[name] = now
                await asyncio.sleep(random.uniform(*JOIN_DELAY))
                try:
                    ent = await a.client.get_entity(name)
                    if not isinstance(ent, T.Channel):
                        continue
                    cid = utils.get_peer_id(ent)
                    st = await member_state(a, ent)
                    if st == "notmember":
                        await a.client(JoinChannelRequest(ent))
                        a.joins.append(time.time())
                        await asyncio.sleep(random.uniform(3, 8))
                        what = "guruhga" if ent.megagroup else "kanalga"
                        await notify(app, OWNER_ID, f"➕ {a.label or a.session}: {ent.title} {what} qo'shildi ({g['title']} dagi bot talabi).")
                    if ent.megagroup and str(cid) not in groups:
                        rights = getattr(ent, "default_banned_rights", None)
                        if len(groups) >= MAX_GROUPS:
                            await notify(app, OWNER_ID, f"⚠️ {ent.title}: guruhlar limiti ({MAX_GROUPS}) to'lgani uchun postlar ro'yxatiga qo'shilmadi.")
                        elif rights and getattr(rights, "send_messages", False):
                            await notify(app, OWNER_ID, f"ℹ️ {ent.title}: guruhga hamma uchun yozish yopiq, postlar ro'yxatiga qo'shilmadi.")
                        else:
                            ng = new_group(cid, ent.title, a.session, getattr(ent, "username", None))
                            ng["next_at"] = time.time() + random.uniform(60, 180)
                            st2 = await member_state(a, ent)
                            if isinstance(st2, tuple):
                                ng["pause_until"], ng["kind"] = st2
                                ng["notify_resume"] = st2[0] < FOREVER
                            add_group(ng)
                            await notify(app, OWNER_ID, f"✅ {ent.title} postlar ro'yxatiga qo'shildi (tez orada habar yuboriladi).")
                except errors.UserAlreadyParticipantError:
                    pass
                except errors.InviteRequestSentError:
                    await notify(app, OWNER_ID, f"⏳ @{name}: qo'shilish so'rovi yuborildi, admin tasdiqlashi kerak.")
                except errors.FloodWaitError as ex:
                    a.join_block = time.time() + ex.seconds + 5
                    await notify(app, OWNER_ID, f"⏳ {a.label or a.session}: qo'shilish cheklandi ({fmt_wait(ex.seconds)}). Avto-qo'shilish shu vaqtgacha to'xtadi.")
                    return
                except errors.ChannelsTooMuchError:
                    await notify(app, OWNER_ID, f"⚠️ {a.label or a.session}: kanal/guruhlar limiti to'lgan, @{name} ga qo'shila olmadi.")
                    return
                except DEAD_ERRORS:
                    await dead(a)
                    return
                except Exception as ex:
                    log.warning("avto-qo'shilish (@%s): %s", name, type(ex).__name__)
    except Exception:
        log.exception("autojoin")


def attach_handlers(a):
    """Akkaunt guruhlarida mute/ban/warn bo'lsa darhol sezish uchun hodisalarni ulaydi."""
    if a.hooked or not a.client:
        return
    a.hooked = True

    @a.client.on(events.Raw(T.UpdateChannelParticipant))
    async def _participant(update):
        try:
            if update.user_id != a.tg_id:
                return
            g = groups.get(str(utils.get_peer_id(T.PeerChannel(update.channel_id))))
            if g and g["acc"] == a.session:
                await on_my_participant(g, update.new_participant)
        except Exception:
            log.exception("participant hodisasi")

    @a.client.on(events.NewMessage(incoming=True))
    async def _message(event):
        try:
            g = groups.get(str(event.chat_id))
            if not g or g["acc"] != a.session:
                return
            msg = event.message
            addressed = bool(msg.mentioned)
            if not addressed and msg.reply_to:
                rep = await event.get_reply_message()
                addressed = bool(rep and rep.out)
            if not addressed:
                return
            # Oddiy foydalanuvchi (bot emas) akkauntni tilga olsa yoki javob yozsa, egasiga xabar beramiz
            try:
                who = await event.get_sender()
                if (isinstance(who, T.User) and not who.bot and who.id != a.tg_id
                        and rate_ok(f"mention:{event.chat_id}:{who.id}", 3, 600)
                        and rate_ok("mention:all", 30, 600)):
                    name = " ".join(x for x in (who.first_name, who.last_name) if x) or str(who.id)
                    tag = f" @{who.username}" if who.username else ""
                    how = "tilga oldi" if msg.mentioned else "javob yozdi"
                    cid = str(g["id"])
                    if g.get("user"):
                        link = f"https://t.me/{g['user']}/{msg.id}"
                    elif cid.startswith("-100"):
                        link = f"https://t.me/c/{cid[4:]}/{msg.id}"
                    else:
                        link = ""
                    body = (msg.raw_text or "").strip().replace("\n", " ")[:500] or "(matnsiz xabar)"
                    await notify(app, OWNER_ID,
                                 f"💬 {a.label or a.session} akkauntini {g['title']} guruhida {how}:\n"
                                 f"👤 {name}{tag} (id {who.id})\n\n{body}" + (f"\n\n🔗 {link}" if link else ""))
            except Exception:
                log.exception("mention xabari")
            kind, secs = parse_moderation(msg.raw_text or "")
            if kind:
                await set_pause(g, time.time() + secs, kind, " (guruh xabari asosida)")
                return
            if conf.get("autojoin", True):
                sender = await event.get_sender()
                if isinstance(sender, T.User) and sender.bot and await sender_is_admin(a, event):
                    asyncio.create_task(autojoin(a, g, msg))
        except Exception:
            log.exception("xabar hodisasi")

    @a.client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def _dm(event):
        """Blok ro'yxatidagi odam shaxsiy xabar yozsa, uni bloklaydi."""
        try:
            if not bl["on"] or not bl["last_id"]:
                return
            sender = await event.get_sender()
            if not isinstance(sender, T.User):
                return
            why = bl_match(sender)
            if not why:
                return
            who = ("@" + sender.username) if sender.username else f"id {sender.id}"
            link = f"t.me/{BL_CHANNEL}/{why[1]}"
            if getattr(sender, "contact", False):
                await warn(app, OWNER_ID, f"blc:{sender.id}",
                           f"ℹ️ {who} ({why[0]} bo'yicha) blok ro'yxatida, lekin kontaktingizda: bloklamadim. Post: {link}",
                           every=86400)
                return
            await a.client(BlockRequest(await event.get_input_sender()))
            bl["count"] += 1
            stats["blocks"] += 1
            bl["blocked"].append({"id": sender.id, "who": who, "acc": a.session, "post": why[1], "by": why[0], "t": time.time()})
            del bl["blocked"][:-30]
            save_bl()
            await notify(app, OWNER_ID,
                         f"🚫 {who} bloklandi ({why[0]} bo'yicha). Post: {link}\n"
                         "Xato bo'lsa: 🚫 Blok ro'yxati → 🔓 Blokdan chiqarish.")
        except Exception:
            log.exception("blok hodisasi")


async def send_one(a, g):
    now = time.time()
    text = posts["texts"][g["ti"] % len(posts["texts"])]
    try:
        inp = await a.client.get_input_entity(int(g["id"]))
        await a.client.send_message(inp, text, parse_mode=None)
    except errors.SlowModeWaitError as e:
        g["next_at"] = now + e.seconds + 5
        save_groups()
        return
    except errors.FloodWaitError as e:
        await set_block(a, "post", e.seconds)
        return
    except errors.PeerFloodError:
        await spam_hold(a, "PeerFlood xatosi")
        return
    except DEAD_ERRORS:
        await dead(a)
        return
    except ValueError:
        await set_pause(g, now + iv("fallback_pause"), "write", " (guruh topilmadi)")
        return
    except Exception as e:
        t = etxt(e)
        if any(k in t for k in ("FORBIDDEN", "BANNED", "RESTRICTED", "KICKED", "PRIVATE", "NOTPARTICIPANT", "ADMINREQUIRED")):
            st = await member_state(a, inp)
            if st == "notmember":
                await set_pause(g, FOREVER, "left")
            elif isinstance(st, tuple):
                await set_pause(g, st[0], st[1])
            else:
                await set_pause(g, now + iv("fallback_pause"), "write", " (sababi aniqlanmadi, @SpamBot'ni tekshiring)")
        else:
            log.warning("post xatosi %s: %s", g["title"], t)
            g["next_at"] = now + 600
            save_groups()
        return
    g["last_post"] = now
    a.sent.append(now)
    g["sent"] += 1
    stats["posts"] += 1
    g["ti"] += 1
    save_groups()


cyc = {"queue": [], "last": 0.0, "posts0": 0}   # joriy tsikl: navbat, oxirgi yuborish vaqti


def cycle_eligible(g, now):
    a = accs.get(g["acc"])
    if not (g["enabled"] and now >= g["pause_until"] and a and a.auth and role_has(a, "post")
            and a.block["post"] <= now and not spam_active(a, now)):
        return False
    while a.sent and a.sent[0] < now - 3600:
        a.sent.popleft()
    return len(a.sent) < POST_HOURLY_CAP


async def poster_cycle(app):
    """Tsikl modeli: tsikl boshida faol guruhlar navbatga olinadi, har biriga ketma-ket yoziladi
    (habarlar orasida `gap`), hammasi tugagach `cycle` kutiladi va keyingi tsikl boshlanadi."""
    now = time.time()
    for g in list(groups.values()):    # cheklov muddati tugaganini xabar qilish
        if g.get("notify_resume") and g["pause_until"] < FOREVER and now >= g["pause_until"]:
            g["notify_resume"] = False
            save_groups()
            await notify(app, OWNER_ID, f"✅ {g['title']}: {PAUSE_UZ.get(g['kind'], g['kind'])} muddati tugadi, yozish davom etadi.")
    if not window_ok(local_now()):
        await asyncio.sleep(30)
        return
    if not posts["on"] or not posts["texts"] or not groups:
        cyc["queue"] = []
        await asyncio.sleep(3)
        return
    if not cyc["queue"]:
        if now < posts["next_cycle"]:
            await asyncio.sleep(min(3, posts["next_cycle"] - now))
            return
        cyc["queue"] = [k for k, g in groups.items() if cycle_eligible(g, now)]
        cyc["posts0"] = stats["posts"]
        if not cyc["queue"]:
            posts["next_cycle"] = now + posts["cycle"]
            save_posts()
            return
    g = groups.get(cyc["queue"].pop(0))
    if g and cycle_eligible(g, time.time()):
        wait = cyc["last"] + max(posts["gap"], MIN_GAP) * random.uniform(1.0, 1.25) - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
        if posts["on"] and cycle_eligible(g, time.time()):
            cyc["last"] = time.time()
            await send_one(accs[g["acc"]], g)
    if not cyc["queue"]:    # tsikl tugadi
        posts["next_cycle"] = time.time() + posts["cycle"]
        save_posts()
        log_event(f"🔁 Tsikl tugadi: {stats['posts'] - cyc['posts0']} ta post. Keyingisi {fmt_wait(posts['cycle'])}dan keyin.")


async def poster_loop(app):
    while True:
        try:
            await poster_cycle(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("poster_loop xatosi")
            await asyncio.sleep(5)


async def resolve_group(name):
    """Username bo'yicha guruhni topib, akkaunt a'zoligini tekshiradi. (guruh | None, natija qatori)"""
    for _ in range(max(1, len(accs))):
        a = await acquire("resolve", RESOLVE_DELAY, "post")
        if a is None:
            return None, f"⏳ @{name} — Telegram akkaunt qidirishni cheklagan"
        try:
            e = await a.client.get_entity(name)
        except errors.FloodWaitError as ex:
            await set_block(a, "resolve", ex.seconds)
            continue
        except DEAD_ERRORS:
            await dead(a)
            continue
        except Exception:
            return None, f"❌ @{name} — topilmadi"
        if isinstance(e, T.Channel) and not e.megagroup:
            return None, f"❌ @{name} — kanal (guruh emas)"
        if not isinstance(e, (T.Channel, T.Chat)):
            return None, f"❌ @{name} — guruh emas"
        cid = utils.get_peer_id(e)
        if str(cid) in groups:
            return None, f"ℹ️ {e.title} — allaqachon ro'yxatda"
        st = await member_state(a, e) if isinstance(e, T.Channel) else "ok"
        if st == "notmember":
            return None, f"❌ {e.title} — akkaunt a'zo emas (avval qo'lda qo'shiling, bot o'zi qo'shilmaydi)"
        g = new_group(cid, e.title, a.session, getattr(e, "username", None))
        line = f"✅ {e.title} — qo'shildi"
        if isinstance(st, tuple):
            g["pause_until"], g["kind"] = st
            g["notify_resume"] = st[0] < FOREVER
            line += f"\n    ⛔ hozir {PAUSE_UZ.get(st[1], st[1])}: " + (
                "muddatsiz" if st[0] >= FOREVER else f"{fmt_wait(st[0] - time.time())} yozmayman")
        return g, line
    return None, f"⏳ @{name} — Telegram akkaunt qidirishni cheklagan"


async def handle_group_add(update, text):
    names = []
    for a1, a2 in GROUP_RE.findall(text):
        n = (a1 or a2).lower()
        if n != "joinchat" and n not in names:
            names.append(n)
    names = names[:20]
    if not names:
        await update.message.reply_text(
            "Guruh username yoki t.me havola topilmadi. Maxfiy (+) havolalar qo'llab-quvvatlanmaydi: "
            "bot o'zi guruhga qo'shilmaydi. Ochiq bo'lmasa 📥 Akkaunt guruhlari tugmasidan foydalaning."
        )
        return
    if not live("post"):
        await update.message.reply_text("Avval 📣 avto post rolidagi akkaunt qo'shing (🔑).")
        return
    msg = await update.message.reply_text("⏳ Guruhlar tekshirilmoqda...")
    lines = []
    for n in names:
        if len(groups) >= MAX_GROUPS:
            lines.append(f"⚠️ @{n} — limit ({MAX_GROUPS}) to'ldi")
            continue
        g, line = await resolve_group(n)
        if g:
            add_group(g)
        lines.append(line)
    await send_chunks(msg, update, lines)


async def list_dialog_groups():
    """Akkauntlar a'zo bo'lgan, hali ro'yxatda yo'q va yozish mumkin bo'lgan guruhlar."""
    out, seen_ids = [], set()
    for a in live("post"):
        try:
            async for d in a.client.iter_dialogs(limit=300):
                if not d.is_group or str(d.id) in groups or d.id in seen_ids:
                    continue
                ent = d.entity
                if getattr(ent, "left", False):
                    continue
                rights = getattr(ent, "default_banned_rights", None)
                if rights and getattr(rights, "send_messages", False):
                    continue    # guruh hamma uchun yozishga yopiq
                seen_ids.add(d.id)
                out.append({"id": d.id, "title": d.name or str(d.id), "acc": a.session})
        except Exception as e:
            log.warning("dialoglar o'qilmadi (%s): %s", a.session, e)
    return out


def texts_view():
    t = posts["texts"]
    if t:
        body = "\n".join(f"{i + 1}. {x[:60]}{'…' if len(x) > 60 else ''}" for i, x in enumerate(t))
    else:
        body = "Matn yo'q."
    text = (f"📣 Post matnlari ({len(t)}/{MAX_TEXTS}). Bir nechta bo'lsa, navbat bilan aylanadi.\n\n" + body)
    rows = [[InlineKeyboardButton("➕ Matn qo'shish", callback_data="ptadd")]]
    dels = [InlineKeyboardButton(f"🗑 {i + 1}", callback_data=f"ptdel:{i}") for i in range(len(t))]
    rows += [dels[i:i + 5] for i in range(0, len(dels), 5)]
    return text, InlineKeyboardMarkup(rows)


def delay_view():
    text = (
        "⏱ Kechikish\n"
        f"Habarlar orasida: {fmt_wait(posts['gap'])}\n"
        f"Tsikllar orasida: {fmt_wait(posts['cycle'])}\n\n"
        "Birinchi pauza guruhlar orasidagi vaqtni boshqaradi.\n"
        "Ikkinchi pauza keyingi yuborish tsiklini boshlaydi.\n"
        "Pauza qisqa bo'lsa, Telegram akkauntni spam deb cheklashi mumkin."
    )
    rows = [
        [InlineKeyboardButton("⌛ Habarlar orasida", callback_data="dgap")],
        [InlineKeyboardButton("🔄 Tsikllar orasida", callback_data="dcyc")],
    ]
    return text, InlineKeyboardMarkup(rows)


def groups_view():
    now = time.time()
    lines, rows = [], []
    for k, g in groups.items():
        if not g["enabled"]:
            st = "⏸ o'chiq"
        elif g["pause_until"] > now:
            st = "⛔ " + PAUSE_UZ.get(g["kind"], "pauza") + (
                " (muddatsiz)" if g["pause_until"] >= FOREVER else f" ({fmt_wait(g['pause_until'] - now)})")
        else:
            st = "🟢 faol"
        lines.append(f"{st} {g['title']}")
        resume = (not g["enabled"]) or g["pause_until"] > now
        rows.append([
            InlineKeyboardButton(("▶️ " if resume else "⏸ ") + g["title"][:22], callback_data=f"gtog:{k}"),
            InlineKeyboardButton("🗑", callback_data=f"gdel:{k}"),
        ])
    rows.append([
        InlineKeyboardButton("➕ Guruh qo'shish", callback_data="gadd"),
        InlineKeyboardButton("📥 Akkaunt guruhlari", callback_data="gimp"),
    ])
    state = "yoqilgan" if posts["on"] else "o'chiq"
    head = (f"👥 Guruhlar ({len(groups)}/{MAX_GROUPS}). Avto post: {state}, "
            f"habarlar orasida {fmt_wait(posts['gap'])}, tsikllar orasida {fmt_wait(posts['cycle'])}.")
    return head + ("\n\n" + "\n".join(lines) if lines else "\n\nGuruh yo'q."), InlineKeyboardMarkup(rows)


# ---------- blok ro'yxati (kanal postlaridan) ----------
bl = read_json(BL_FILE) or {}
for _k, _v in (("on", False), ("last_id", 0), ("synced", 0.0), ("retry_at", 0.0), ("count", 0)):
    bl.setdefault(_k, _v)
for _k in ("users", "ids", "phones"):
    bl.setdefault(_k, {})        # {kalit: post_id}
for _k in ("allow", "exclude", "blocked"):
    bl.setdefault(_k, [])
bl_status = {"running": False, "n": 0, "added": 0}

USER_RE = re.compile(r"(?<![A-Za-z0-9_/.])@([A-Za-z][A-Za-z0-9_]{3,31})")
LINK_RE = re.compile(r"t\.me/([A-Za-z][A-Za-z0-9_]{3,31})(?![A-Za-z0-9_/])")
PHONE_RE = re.compile(r"(?<![\w])\+?\d[\d\s\-()]{7,16}\d")
SKIP_LINKS = {"joinchat", "addstickers", "addemoji", "share", "proxy", "socks", "iv", "boost", "addlist", "c", "s"}


def save_bl():
    write_json(BL_FILE, bl)


def norm_phone(text):
    d = re.sub(r"\D", "", text or "")
    return d[-9:] if 9 <= len(d) <= 13 else None


def extract_ids(msg):
    """Post matnidan username, user ID va telefonlarni ajratadi."""
    users, ids, phones = set(), set(), set()
    text = msg.raw_text or ""
    for m in USER_RE.findall(text):
        users.add(m.lower())
    for m in LINK_RE.findall(text):
        if m.lower() not in SKIP_LINKS:
            users.add(m.lower())
    for m in PHONE_RE.findall(text):
        ph = norm_phone(m)
        if ph:
            phones.add(ph)
    for ent, _ in (msg.get_entities_text() or []):
        if isinstance(ent, T.MessageEntityMentionName):
            ids.add(ent.user_id)
        elif isinstance(ent, T.MessageEntityTextUrl):
            url = ent.url or ""
            m = re.search(r"tg://user\?id=(\d+)", url)
            if m:
                ids.add(int(m.group(1)))
            m = LINK_RE.search(url)
            if m and m.group(1).lower() not in SKIP_LINKS:
                users.add(m.group(1).lower())
    return users, ids, phones


def bl_match(user):
    """Yuboruvchi blok ro'yxatida bo'lsa (sabab, post_id), aks holda None.
    Istisnolar, kanal admin/aloqa akkauntlari, botlar va o'z akkauntlaringiz hech qachon bloklanmaydi."""
    if getattr(user, "bot", False) or getattr(user, "is_self", False):
        return None
    if user.id in {a.tg_id for a in accs.values() if a.tg_id}:
        return None
    names = {(user.username or "").lower()} - {""}
    for u in (getattr(user, "usernames", None) or []):
        if getattr(u, "active", True) and u.username:
            names.add(u.username.lower())
    allow = {str(x).lower() for x in bl["allow"]}
    if str(user.id) in allow or names & allow or names & set(bl["exclude"]):
        return None
    if str(user.id) in bl["ids"]:
        return "id", bl["ids"][str(user.id)]
    for n in names:
        if n in bl["users"]:
            return "username", bl["users"][n]
    ph = norm_phone(getattr(user, "phone", "") or "")
    if ph and ph in bl["phones"]:
        return "telefon", bl["phones"][ph]
    return None


async def bl_sync(app, manual=False):
    """Kanalning barcha (yangi) postlarini o'qib, blok ro'yxatini to'ldiradi. Kanalga qo'shilish shart emas."""
    if bl_status["running"] or time.time() < bl["retry_at"]:
        return False
    a = await acquire("resolve", RESOLVE_DELAY)
    if a is None:
        return False
    first = not bl["last_id"]
    bl_status.update(running=True, n=0, added=0)
    done = False
    try:
        try:
            ch = await a.client.get_entity(BL_CHANNEL)
            full = await a.client(GetFullChannelRequest(ch))
        except errors.FloodWaitError as e:
            await set_block(a, "resolve", e.seconds)
            return False
        about = getattr(full.full_chat, "about", "") or ""
        bl["exclude"] = sorted({BL_CHANNEL.lower()} | {m.lower() for m in USER_RE.findall(about)}
                               | {m.lower() for m in LINK_RE.findall(about)})
        try:
            async for m in a.client.iter_messages(ch, min_id=bl["last_id"], reverse=True, wait_time=1):
                if not isinstance(m, T.Message):
                    continue
                users, ids, phones = extract_ids(m)
                for x in users:
                    if x not in bl["users"] and len(bl["users"]) < BL_MAX:
                        bl["users"][x] = m.id
                        bl_status["added"] += 1
                for x in ids:
                    if str(x) not in bl["ids"] and len(bl["ids"]) < BL_MAX:
                        bl["ids"][str(x)] = m.id
                        bl_status["added"] += 1
                for x in phones:
                    if x not in bl["phones"] and len(bl["phones"]) < BL_MAX:
                        bl["phones"][x] = m.id
                        bl_status["added"] += 1
                bl["last_id"] = max(bl["last_id"], m.id)
                bl_status["n"] += 1
                if bl_status["n"] % 200 == 0:
                    save_bl()
            done = True
        except errors.FloodWaitError as e:
            bl["retry_at"] = time.time() + e.seconds
        bl["synced"] = time.time()
        save_bl()
    except DEAD_ERRORS:
        await dead(a)
        return False
    except Exception as e:
        log.warning("kanal o'qilmadi: %s", e)
        return False
    finally:
        bl_status["running"] = False
    text = (f"🚫 Blok ro'yxati yangilandi: {bl_status['n']} ta post o'qildi, {bl_status['added']} ta yangi yozuv. "
            f"Jami: {len(bl['users'])} username, {len(bl['ids'])} id, {len(bl['phones'])} telefon.")
    if not done:
        text += "\nTelegram cheklagani uchun to'liq tugamadi, keyinroq o'zi davom etadi."
    if manual or first or not done:
        await notify(app, OWNER_ID, text)
    elif bl_status["added"]:
        log_event(text)
    return True


async def bl_loop(app):
    await asyncio.sleep(45)
    while True:
        try:
            due = not bl["last_id"] or time.time() - bl["synced"] >= iv("sync_every")
            if bl["on"] and live("sniper") and due:
                await bl_sync(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("bl_loop xatosi")
        await asyncio.sleep(60)


async def bl_unblock(uid):
    """Botdan bloklangan odamni blokdan chiqaradi va istisnoga qo'shadi. (ok, matn)"""
    uid = str(uid)
    x = next((b for b in bl["blocked"] if str(b["id"]) == uid), None)
    a = accs.get(x["acc"]) if x else None
    if not x or not a or not a.auth:
        return False, "Topilmadi yoki akkaunt ulanmagan."
    try:
        await a.client(UnblockRequest(await a.client.get_input_entity(x["id"])))
    except Exception as e:
        return False, f"Xato: {type(e).__name__}"
    if uid not in bl["allow"]:
        bl["allow"].append(uid)
    bl["blocked"] = [b for b in bl["blocked"] if str(b["id"]) != uid]
    save_bl()
    return True, f"🔓 {x['who']} blokdan chiqarildi va istisnoga qo'shildi."


def bl_view():
    now = time.time()
    last = f"{fmt_wait(now - bl['synced'])} oldin" if bl["synced"] else "hali o'qilmagan"
    state = "yoqilgan" if bl["on"] else "o'chiq"
    text = (
        f"🚫 Blok ro'yxati (kanal: @{BL_CHANNEL})\n"
        f"Avto-bloklash: {state}\n"
        f"Ro'yxatda: {len(bl['users'])} username, {len(bl['ids'])} id, {len(bl['phones'])} telefon\n"
        f"Oxirgi yangilanish: {last}\n"
        f"Bloklangan: {bl['count']} ta, istisnolar: {len(bl['allow'])} ta"
    )
    rows = [
        [InlineKeyboardButton("🔄 Kanalni yangilash", callback_data="blsync")],
        [InlineKeyboardButton("⏸ Avto-bloklashni o'chirish" if bl["on"] else "▶️ Avto-bloklashni yoqish", callback_data="bltog")],
        [InlineKeyboardButton("🔓 Blokdan chiqarish", callback_data="blun"),
         InlineKeyboardButton("✅ Istisno qo'shish", callback_data="blallow")],
    ]
    return text, InlineKeyboardMarkup(rows)


# ---------- sozlamalar, hisobot, zaxira ----------
conf = read_json(CONF_FILE) or {}
for _k, _v in (("quiet", [23, 7]), ("report_hour", 21), ("backup_hour", 3), ("last_report", ""), ("last_backup", ""), ("auto_drop", True), ("autojoin", True)):
    conf.setdefault(_k, _v)
# Qo'lda o'zgartiriladigan vaqt oraliqlari (soniya): kalit -> (standart, nomi, izoh)
INTERVALS = {
    "recheck_every": (RECHECK_EVERY, "🔁 Faollikni qayta tekshirish", "kuzatuvdagi usernamelar faolligi qanchada bir tekshirilsin"),
    "spam_check_every": (SPAM_CHECK_EVERY, "🛡 SpamBot tekshiruvi", "akkaunt holati @SpamBot orqali qanchada bir tekshirilsin"),
    "sync_every": (SYNC_EVERY, "📥 Blok kanalini yangilash", "kanaldan yangi postlar qanchada bir olinsin"),
    "warn_pause": (WARN_PAUSE, "⚠️ Warn pauzasi", "warn olinsa guruhga qancha yozilmasin (muddat aytilmasa)"),
    "fallback_pause": (FALLBACK_PAUSE, "⏸ Noma'lum cheklov pauzasi", "sababi aniqlanmagan cheklovda qancha kutilsin"),
}
IV_MIN, IV_MAX = 5 * 60, 30 * 86400


def iv(key):
    """Sozlamadagi vaqt oralig'i (soniya); noto'g'ri bo'lsa standart qiymat."""
    try:
        v = float(conf.get("intervals", {}).get(key))
        if IV_MIN <= v <= IV_MAX:
            return v
    except (TypeError, ValueError):
        pass
    return INTERVALS[key][0]


def fmt_iv(sec):
    sec = int(sec)
    if sec % 86400 == 0:
        return f"{sec // 86400} kun"
    if sec % 3600 == 0:
        return f"{sec // 3600} soat"
    return fmt_wait(sec)


STAT_KEYS = ("checks", "posts", "blocks", "claimed", "floods", "pauses")
stats = {k: 0 for k in STAT_KEYS}
stats.update({k: v for k, v in (conf.get("stats") or {}).items() if k in stats})
quiet_buf = []
IMPORTANT = ("🎉", "⛔", "🚫", "⚠️", "⚠")


def local_now():
    return datetime.now(TZ)


def hour_in(h, a, b):
    """h soat [a, b) oraliqda (yarim tundan o'tishi mumkin) mi? a == b bo'lsa, oraliq yo'q."""
    if a == b:
        return False
    return a <= h < b if a < b else (h >= a or h < b)


def window_ok(now):
    """Guruhlarga yozish uchun ruxsat etilgan soatlarmi?"""
    a, b = posts["from"], posts["to"]
    return True if (a, b) == (0, 24) else hour_in(now.hour, a, b)


def in_quiet(now):
    a, b = conf["quiet"]
    return hour_in(now.hour, a, b)


def save_conf():
    conf["stats"] = stats
    write_json(CONF_FILE, conf)


def report_text():
    now = time.time()
    act = sum(1 for g in groups.values() if g["enabled"] and g["pause_until"] <= now)
    lim = [a.label or a.session for a in accs.values() if any(v > now for v in a.block.values())]
    t = (
        "📊 Kunlik hisobot\n"
        f"Tekshiruv: {stats['checks']}\n"
        f"Egallangan: {stats['claimed']}\n"
        f"Guruhga post: {stats['posts']}\n"
        f"Bloklangan: {stats['blocks']}\n"
        f"Telegram cheklovi: {stats['floods']} marta\n"
        f"Guruh pauzasi: {stats['pauses']} marta\n\n"
        f"Kuzatuvda: {len(watch)} username\n"
        f"Faol guruh: {act}/{len(groups)}\n"
        f"Faol akkaunt: {len(live())}/{len(accs)}"
    )
    if lim:
        t += "\nHozir cheklangan: " + ", ".join(lim)
    return t


def make_backup():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (WATCH_FILE, GROUPS_FILE, POSTS_FILE, BL_FILE, ACC_FILE, CONF_FILE):
            if os.path.exists(f):
                z.write(f)
    buf.seek(0)
    return buf, f"zaxira_{local_now():%Y%m%d_%H%M}.zip"


async def send_backup(app):
    buf, name = make_backup()
    await app.bot.send_document(
        OWNER_ID, document=buf, filename=name,
        caption="💾 Zaxira nusxa. Seans va config.json kiritilmagan. Tiklash: fayllarni bot papkasiga qo'ying.",
    )


async def report_loop(app):
    await asyncio.sleep(30)
    while True:
        try:
            now = local_now()
            today = now.strftime("%Y-%m-%d")
            if quiet_buf and not in_quiet(now):
                lines = [f"{datetime.fromtimestamp(t, TZ):%H:%M} {x.replace(chr(10), ' ')}" for t, x in quiet_buf]
                del quiet_buf[:]
                await notify(app, OWNER_ID, ("🌙 Jim rejimda yig'ilgan xabarlar:\n" + "\n".join(lines))[:4000], force=True)
            if now.hour >= conf["report_hour"] and conf["last_report"] != today:
                await notify(app, OWNER_ID, report_text(), force=True)
                for k in stats:
                    stats[k] = 0
                conf["last_report"] = today
            if now.hour >= conf["backup_hour"] and conf["last_backup"] != today:
                try:
                    await send_backup(app)
                except Exception as e:
                    log.warning("zaxira yuborilmadi: %s", e)
                conf["last_backup"] = today
            save_conf()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("report_loop xatosi")
        await asyncio.sleep(60)


def settings_view():
    qa, qb = conf["quiet"]
    quiet = "o'chiq" if qa == qb else f"{qa:02d}:00–{qb:02d}:00"
    drop_state = "yoqilgan" if conf.get("auto_drop", True) else "o'chiq"
    text = (
        "⚙️ Sozlamalar (vaqt zonasi: " + TZ_LABEL + ")\n"
        f"🕘 Post soatlari: {posts['from']:02d}:00–{posts['to'] % 24:02d}:00\n"
        f"🌙 Jim rejim: {quiet} (faqat muhim xabarlar keladi)\n"
        f"📊 Hisobot: har kuni {conf['report_hour']:02d}:00\n"
        f"💾 Zaxira: har kuni {conf['backup_hour']:02d}:00\n"
        f"🗑 Faol bo'lsa kuzatuvdan chiqarish: {drop_state}\n"
        f"➕ Bot talabi bilan avto qo'shilish: {'yoqilgan' if conf.get('autojoin', True) else 'xo' + chr(39) + 'chiq'} (faqat guruh admini bo'lgan botdan, sutkada {JOIN_DAILY_CAP} tagacha)\n\n"
        "⏱ Vaqt oraliqlari:\n"
        + "\n".join(f"{v[1]}: {fmt_iv(iv(k))}" for k, v in INTERVALS.items())
    )
    rows = [
        [InlineKeyboardButton("🕘 Post soatlari", callback_data="setwin"),
         InlineKeyboardButton("🌙 Jim rejim", callback_data="setquiet")],
        [InlineKeyboardButton("📊 Hisobot soati", callback_data="setrep"),
         InlineKeyboardButton("💾 Zaxira soati", callback_data="setbak")],
        [InlineKeyboardButton("📊 Hisobotni hozir", callback_data="repnow"),
         InlineKeyboardButton("💾 Zaxirani hozir", callback_data="bakup")],
        [InlineKeyboardButton("🗑 Faol bo'lsa chiqarish: yoq/o'ch", callback_data="setdrop")],
        [InlineKeyboardButton("➕ Avto qo'shilish: yoq/o'ch", callback_data="setjoin")],
    ] + [[InlineKeyboardButton(v[1], callback_data=f"setiv:{k}")] for k, v in INTERVALS.items()]
    return text, InlineKeyboardMarkup(rows)


# ---------- @SpamBot cheklovi ----------
MONTH_PREFIXES = (
    ("fevr", 2), ("апрел", 4), ("сентябр", 9), ("октябр", 10), ("ноябр", 11), ("декабр", 12),
    ("yanv", 1), ("jan", 1), ("янв", 1), ("fev", 2), ("feb", 2), ("фев", 2), ("mart", 3), ("mar", 3), ("мар", 3),
    ("apr", 4), ("апр", 4), ("may", 5), ("мая", 5), ("май", 5), ("iyun", 6), ("jun", 6), ("июн", 6),
    ("iyul", 7), ("jul", 7), ("июл", 7), ("avg", 8), ("aug", 8), ("авг", 8), ("sen", 9), ("сен", 9),
    ("okt", 10), ("oct", 10), ("окт", 10), ("noy", 11), ("nov", 11), ("ноя", 11), ("dek", 12), ("dec", 12), ("дек", 12),
)
SB_DATE_RE = re.compile(r"(\d{1,2})[\s-]*([a-zа-я]{3,})\.?,?\s*(\d{4})(?:[^\d]{0,12}?(\d{1,2}):(\d{2}))?")
SB_NUM_RE = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{4})(?:[^\d]{0,6}(\d{1,2}):(\d{2}))?")
# @SpamBot "cheklov yo'q" deydigan iboralar (inglizcha, ruscha, o'zbekcha)
OK_HINTS = (
    # inglizcha
    "no limits", "free as a bird", "good news",
    # ruscha
    "нет ограничений", "ограничений нет", "не ограничен", "хорошие новости",
    # o'zbekcha (lotin)
    "xushxabar", "yaxshi xabar", "cheklov yo'q", "cheklovlar yo'q", "cheklov mavjud emas", "cheklovlar mavjud emas",
    "cheklov qo'llanilmagan", "cheklovlar qo'llanilmagan", "hech qanday cheklov", "cheklanmagan", "cheklanishlar yo'q",
    "erkin qush", "qush kabi erkin", "qushdek erkin",
    # o'zbekcha (kirill)
    "яхши хабар", "хушхабар", "чеклов йўқ", "чекловлар йўқ", "чеклов мавжуд эмас", "чекловлар мавжуд эмас",
    "чеклов қўлланилмаган", "ҳеч қандай чеклов", "чекланмаган", "қуш каби эркин",
)
LIMITED_HINTS = (
    # inglizcha
    "limited", "unfortunately", "restricted", "i'm afraid", "moderators",
    # ruscha
    "ограничен", "к сожалению", "модератор",
    # o'zbekcha (lotin)
    "cheklangan", "cheklandi", "cheklab qo'yil", "cheklab qo'yilgan", "cheklov qo'yil", "cheklovlar qo'yil",
    "chegaralangan", "chegaralandi", "afsuski", "shikoyat", "moderator", "spam deb", "bloklangan",
    # o'zbekcha (kirill)
    "чекланган", "чекланди", "чеклаб қўйил", "чеклов қўйил", "чегараланган", "афсуски", "шикоят", "модератор", "спам деб",
)


def fmt_local(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m.%Y %H:%M")


def spam_active(a, now):
    """Akkaunt spam cheklovida (muddat kiritilmagan yoki muddat hali tugamagan) mi?"""
    sp = a.spam if a else None
    return bool(sp) and (sp.get("state") != "until" or now < sp.get("until", 0))


def norm_text(t):
    """Apostrof belgilarini birxillashtirib, kichik harfga o'tkazadi (yo'q / yo‘q / yoʻq bir xil bo'lsin)."""
    return re.sub(r"[‘’ʻʼ`´]", "'", t or "").lower()


def _utc_ts(y, mo, d, hh, mm):
    try:
        return datetime(y, mo, d, int(hh) if hh is not None else 23, int(mm) if mm is not None else 59,
                        tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def parse_spambot_date(text):
    """@SpamBot javobidagi aniq sana (UTC) -> epoch. Oy nomi inglizcha, ruscha yoki o'zbekcha bo'lishi mumkin;
    vaqt yozilmasa kun oxiri olinadi."""
    t = norm_text(text)
    for m in SB_DATE_RE.finditer(t):
        mon = next((n for p, n in MONTH_PREFIXES if m.group(2).startswith(p)), None)
        if mon:
            ts = _utc_ts(int(m.group(3)), mon, int(m.group(1)), m.group(4), m.group(5))
            if ts:
                return ts
    for m in SB_NUM_RE.finditer(t):
        ts = _utc_ts(int(m.group(3)), int(m.group(2)), int(m.group(1)), m.group(4), m.group(5))
        if ts:
            return ts
    return None


def parse_when(text):
    """Egasi yozgan sana/soat (masalan '25.11 14:00', '2026-11-25 14:00', '3 kun') -> epoch yoki None.
    Vaqt zonasi: TZ. Yil yozilmasa va sana o'tib ketgan bo'lsa, keyingi yil."""
    t = text.strip().lower()
    if not re.search(r"\d{1,2}[./-]\d{1,2}", t):
        d = parse_duration(t)
        return time.time() + d if d else None
    year_given = True
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, da = (int(x) for x in m.groups())
    else:
        m = re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", t)
        if not m:
            return None
        da, mo = int(m.group(1)), int(m.group(2))
        if m.group(3):
            y = int(m.group(3))
            y += 2000 if y < 100 else 0
        else:
            y, year_given = local_now().year, False
    tm = re.search(r"(\d{1,2})(?::(\d{2}))?", t[m.end():])
    hh, mm = (int(tm.group(1)), int(tm.group(2) or 0)) if tm else (0, 0)
    try:
        ts = datetime(y, mo, da, hh, mm, tzinfo=TZ).timestamp()
        if ts < time.time() and not year_given:
            ts = datetime(y + 1, mo, da, hh, mm, tzinfo=TZ).timestamp()
    except ValueError:
        return None
    return ts if ts > time.time() else None


async def spambot_check(a):
    """@SpamBot dan akkaunt holatini so'raydi.
    'ok' (cheklov yo'q) | 'limited' (aniq belgi: sana yoki 'cheklangan' kabi so'z) | 'unknown' (tushunib bo'lmadi),
    javob matni, tugash vaqti (aniq sana aytilgan bo'lsa)."""
    try:
        async with a.client.conversation("SpamBot", timeout=25) as conv:
            await conv.send_message("/start")
            r = await conv.get_response()
    except Exception as e:
        return "unknown", type(e).__name__, None
    text = r.raw_text or ""
    low = norm_text(text)
    if any(k in low for k in OK_HINTS):
        return "ok", text, None
    until = parse_spambot_date(text)
    if until or any(k in low for k in LIMITED_HINTS):
        return "limited", text, until
    return "unknown", text, None


async def ask_spam_until(a, why, suggest=None, snippet=""):
    """Egasidan so'raydi: cheklov qachongacha? (sana/soat kiritiladi, o'sha kundan yozish boshlanadi)"""
    rows = [
        [InlineKeyboardButton("📅 Sana va soat kiritish", callback_data=f"spq:{a.session}")],
        [InlineKeyboardButton("🔎 @SpamBot'dan so'rash", callback_data=f"spc:{a.session}"),
         InlineKeyboardButton("▶️ Cheklov yo'q", callback_data=f"spn:{a.session}")],
    ]
    if suggest:
        rows.insert(0, [InlineKeyboardButton(f"✅ SpamBot sanasi: {fmt_local(suggest)}",
                                             callback_data=f"spu:{a.session}:{int(suggest)}")])
    text = (f"⚠️ {a.label or a.session}: Telegram akkauntni spam deb cheklagan ({why}). "
            "Guruhlarga yozish to'xtatildi.\n\nCheklov qachongacha? Sana va soatni kiriting, o'sha kundan boshlayman.")
    if snippet:
        text += "\n\n@SpamBot javobi:\n" + snippet[:400]
    log_event(f"⚠️ {a.label or a.session}: spam cheklovi, muddat so'raldi")
    try:
        await app.bot.send_message(OWNER_ID, text, reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e:
        log.warning("spam xabari yuborilmadi: %s", e)


async def apply_spam_result(a, state, text, until, why, manual=False):
    label = a.label or a.session
    now = time.time()
    if state == "ok":
        if a.spam:
            a.spam = None
            save_accs()
            await notify(app, OWNER_ID, f"✅ @SpamBot: {label} akkauntida cheklov yo'q, guruhlarga yozish davom etadi.", force=True)
        elif manual:
            await notify(app, OWNER_ID, f"✅ @SpamBot: {label} akkauntida cheklov yo'q.", force=True)
    elif state == "limited" and until and until > now:
        # @SpamBot aniq sana aytdi: so'ramaymiz, shu sanagacha kutamiz va o'zi davom etamiz
        same = bool(a.spam) and a.spam.get("state") == "until" and abs(a.spam.get("until", 0) - until) < 60
        a.spam = {"state": "until", "until": until}
        save_accs()
        if manual or not same:
            await notify(app, OWNER_ID,
                         f"⛔ {label}: @SpamBot cheklov muddatini aytdi: {fmt_local(until)} gacha. "
                         "O'sha vaqtgacha guruhlarga yozmayman, keyin o'zi davom etadi.", force=True)
    elif state == "limited":
        # cheklov bor, lekin sana aytilmagan: egasidan so'raymiz
        if not a.spam:
            a.spam = {"state": "ask", "since": now, "asked": now}
            save_accs()
            await ask_spam_until(a, why, None, text)
        elif manual or a.spam.get("state") == "ask":
            await ask_spam_until(a, why, None, text)
    elif manual:
        await notify(app, OWNER_ID, f"⚠️ @SpamBot javobini tushunmadim: {text[:300]}", force=True)


async def spam_probe(a, manual=False, why="@SpamBot javobi"):
    state, text, until = await spambot_check(a)
    await apply_spam_result(a, state, text, until, why, manual)
    return state


async def spam_hold(a, why):
    """Guruhga yozishda PeerFlood chiqdi: avval @SpamBot'dan haqiqiy holatni so'raymiz."""
    if a.spam:
        return
    state, text, until = await spambot_check(a)
    label = a.label or a.session
    if state == "ok":
        await set_block(a, "post", 3600)
        await warn(app, OWNER_ID, "pf:" + a.session,
                   f"ℹ️ {label}: Telegram PeerFlood berdi, lekin @SpamBot cheklov yo'q deydi. 1 soat kutib davom etaman.",
                   every=3600)
        return
    if state == "limited" and until and until > time.time():
        await apply_spam_result(a, state, text, until, why)
        return
    a.spam = {"state": "ask", "since": time.time(), "asked": time.time()}
    save_accs()
    await ask_spam_until(a, why, None, text if state == "limited" else "")


async def spam_loop(app):
    await asyncio.sleep(120)
    last_check = {}
    while True:
        try:
            now = time.time()
            for a in live():
                sp = a.spam
                label = a.label or a.session
                if sp and sp.get("state") == "until" and now >= sp["until"]:
                    a.spam = None
                    save_accs()
                    await notify(app, OWNER_ID, f"✅ {label}: spam cheklovi muddati tugadi, guruhlarga yozish davom etadi.", force=True)
                    continue
                if sp and sp.get("state") == "ask" and now - sp.get("asked", 0) >= 12 * 3600:
                    sp["asked"] = now
                    save_accs()
                    await ask_spam_until(a, "muddat hali kiritilmagan")
                    continue
                uses = any(g["acc"] == a.session for g in groups.values())
                if posts["on"] and uses and now - last_check.get(a.session, 0) >= iv("spam_check_every"):
                    last_check[a.session] = now
                    await spam_probe(a)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("spam_loop xatosi")
        await asyncio.sleep(60)


# ---------- bot (faqat egasi uchun) ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Matn ichida @ bilan boshlangan usernamelarni yuboring "
        f"(masalan @durov @test, bir martada {MAX_CHECK} tagacha).\n"
        "Menyu pastdagi ⊞ tugmasida.",
        reply_markup=menu(),
    )


def acc_lines():
    items = list(accs.values())
    if not items:
        return "Akkaunt yo'q. 🔑 orqali qo'shing.", []
    lines, btns = [], []
    now = time.time()
    for a in items:
        st = "✅" if a.auth else "⚠️ ulanmagan"
        w = max(max(a.block.values()) - now, 0)
        extra = f" ⏳ {fmt_wait(w)}" if w > 0 else ""
        if a.spam:
            extra += " 🛑 spam: " + (f"{fmt_local(a.spam['until'])} gacha" if a.spam.get("state") == "until" else "muddat kiritilmagan")
        lines.append(f"{st} {a.label or a.session} [{ROLE_UZ[a.role]}]{extra}")
        btns.append([
            InlineKeyboardButton(f"🗑 {a.label or a.session}", callback_data=f"accdel:{a.session}"),
            InlineKeyboardButton("🔁 Rol", callback_data=f"accrole:{a.session}"),
            InlineKeyboardButton("🛡 SpamBot", callback_data=f"spc:{a.session}"),
        ])
    s_, p_ = slots_used()
    return (f"📱 Akkauntlar ({len(live())} ta faol, limit {MAX_ACCOUNTS}; "
            f"🎯 {s_}/{SNIPER_SLOTS}, 📣 {p_}/{POST_SLOTS}):\n" + "\n".join(lines)), btns


async def do_action(data, msg, ctx):
    """Klaviatura tugmalari va inline tugmalar uchun umumiy amallar."""
    if data == "login":
        await begin_login(msg, ctx)
    elif data == "add":
        if not live("sniper"):
            await msg.reply_text("Avval akkaunt qo'shing: 🔑 Akkaunt qo'shish tugmasini bosing.")
            return
        ctx.user_data["mode"] = "watch"
        await msg.reply_text(
            "Egallamoqchi bo'lgan usernamelarni yuboring.\n"
            "Ular bo'shashi bilan kanal ochib egallayman."
        )
    elif data == "list":
        if watch:
            await msg.reply_text("🎯 Kuzatilmoqda:\n" + "\n".join(f"@{n}" for n in watch))
        else:
            await msg.reply_text("Ro'yxat bo'sh.")
    elif data == "clear":
        watch.clear()
        meta.clear()
        seen.clear()
        save()
        await msg.reply_text("Ro'yxat tozalandi.")
    elif data == "accs":
        text, btns = acc_lines()
        await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(btns) if btns else None)
    elif data == "web":
        if not WEB_ON:
            await msg.reply_text("Web sahifa sozlanmagan: WEBAPP_URL (https) va aiohttp kerak.")
            return
        await msg.reply_text(
            "🌐 Kuzatuvni web sahifada oching:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Ochish", web_app=WebAppInfo(url=WEBAPP_URL))]]
            ),
        )
    elif data == "ptext":
        text, kb = texts_view()
        await msg.reply_text(text, reply_markup=kb)
    elif data == "ptadd":
        if len(posts["texts"]) >= MAX_TEXTS:
            await msg.reply_text(f"Matn limiti ({MAX_TEXTS}) to'ldi. Avval birini o'chiring.")
            return
        ctx.user_data["mode"] = "post_text"
        await msg.reply_text("Guruhlarga yuboriladigan matnni yuboring (oddiy matn, formatlashsiz).")
    elif data.startswith("ptdel:"):
        try:
            posts["texts"].pop(int(data[6:]))
            save_posts()
            await msg.reply_text("🗑 Matn o'chirildi.")
        except (ValueError, IndexError):
            await msg.reply_text("Matn topilmadi.")
    elif data == "groups":
        text, kb = groups_view()
        await msg.reply_text(text, reply_markup=kb)
    elif data == "gadd":
        if not live("post"):
            await msg.reply_text("Avval 📣 avto post rolidagi akkaunt qo'shing (🔑).")
            return
        ctx.user_data["mode"] = "group_add"
        await msg.reply_text(
            "Guruh username yoki t.me havolasini yuboring (bir nechta bo'lishi mumkin).\n"
            "Akkaunt guruhga allaqachon a'zo bo'lishi kerak: bot o'zi guruhga qo'shilmaydi."
        )
    elif data == "gimp":
        if not live("post"):
            await msg.reply_text("Avval 📣 avto post rolidagi akkaunt qo'shing (🔑).")
            return
        wait = await msg.reply_text("⏳ Akkaunt guruhlari o'qilmoqda...")
        found = (await list_dialog_groups())[:40]
        ctx.user_data["gcache"] = found
        if not found:
            await wait.edit_text("Qo'shish mumkin bo'lgan yangi guruh topilmadi.")
            return
        rows = [[InlineKeyboardButton(f"➕ Hammasini qo'shish ({len(found)})", callback_data="gi:all")]]
        rows += [[InlineKeyboardButton("➕ " + x["title"][:30], callback_data=f"gi:{i}")] for i, x in enumerate(found)]
        await wait.edit_text("Qo'shiladigan guruhni tanlang:", reply_markup=InlineKeyboardMarkup(rows))
    elif data.startswith("gi:"):
        cache = ctx.user_data.get("gcache") or []
        arg = data[3:]
        if arg == "all":
            pick = list(cache)
        elif arg.isdigit() and int(arg) < len(cache):
            pick = [cache[int(arg)]]
        else:
            pick = []
        if not pick:
            await msg.reply_text("Ro'yxat eskirdi, 📥 tugmasini qayta bosing.")
            return
        lines = []
        for x in pick:
            if str(x["id"]) in groups:
                continue
            if len(groups) >= MAX_GROUPS:
                lines.append(f"⚠️ Limit ({MAX_GROUPS}) to'ldi")
                break
            a = accs.get(x["acc"])
            if not a or not a.auth:
                lines.append(f"❌ {x['title']} — akkaunt ulanmagan")
                continue
            st = "ok"
            try:
                st = await member_state(a, await a.client.get_input_entity(x["id"]))
            except Exception as _e:
                log.warning("guruh a'zolik holati aniqlanmadi: %s", type(_e).__name__)
            if st == "notmember":
                lines.append(f"❌ {x['title']} — akkaunt a'zo emas")
                continue
            g = new_group(x["id"], x["title"], x["acc"])
            tail = ""
            if isinstance(st, tuple):
                g["pause_until"], g["kind"] = st
                g["notify_resume"] = st[0] < FOREVER
                tail = f" (⛔ {PAUSE_UZ.get(st[1], st[1])})"
            add_group(g)
            lines.append(f"✅ {x['title']}{tail}")
            await asyncio.sleep(0.3)
        await msg.reply_text("\n".join(lines) or "Hammasi allaqachon qo'shilgan.")
    elif data.startswith("gtog:"):
        g = groups.get(data[5:])
        if not g:
            await msg.reply_text("Guruh topilmadi.")
            return
        now = time.time()
        if not g["enabled"] or g["pause_until"] > now:
            g.update(enabled=True, pause_until=0.0, notify_resume=False, next_at=now + random.uniform(30, 120))
            await msg.reply_text(f"▶️ {g['title']} qayta yoqildi.")
        else:
            g["enabled"] = False
            await msg.reply_text(f"⏸ {g['title']} o'chirildi.")
        save_groups()
    elif data.startswith("gdel:"):
        g = groups.pop(data[5:], None)
        save_groups()
        await msg.reply_text(f"🗑 {g['title']} ro'yxatdan olindi." if g else "Guruh topilmadi.")
    elif data == "delay":
        text, kb = delay_view()
        await msg.reply_text(text, reply_markup=kb)
    elif data == "dgap":
        ctx.user_data["mode"] = "set_gap"
        await msg.reply_text(
            f"Habarlar (guruhlar) orasidagi pauzani yuboring. Masalan: 40 soniya yoki 40 (soniya). "
            f"Kamida {fmt_wait(MIN_GAP)}. Hozir: {fmt_wait(posts['gap'])}."
        )
    elif data == "dcyc":
        ctx.user_data["mode"] = "set_cycle"
        await msg.reply_text(
            f"Tsikllar orasidagi pauzani yuboring. Masalan: 10 daqiqa, 1 soat yoki 10 (daqiqa). "
            f"Kamida {fmt_wait(MIN_CYCLE)}. Hozir: {fmt_wait(posts['cycle'])}."
        )
    elif data == "ptoggle":
        if posts["on"]:
            posts["on"] = False
            save_posts()
            await msg.reply_text("⏸ Avto post to'xtatildi.")
            return
        if not posts["texts"]:
            await msg.reply_text("Avval 📣 Post matni orqali matn qo'shing.")
            return
        if not groups:
            await msg.reply_text("Avval 👥 Guruhlar orqali guruh qo'shing.")
            return
        if not live("post"):
            await msg.reply_text("Avval 📣 avto post rolidagi akkaunt qo'shing (🔑).")
            return
        posts["on"] = True
        posts["next_cycle"] = 0.0     # birinchi tsikl darhol boshlansin
        save_posts()
        n = sum(1 for g in groups.values() if g["enabled"])
        await msg.reply_text(
            f"▶️ Avto post yoqildi: {n} guruh, habarlar orasida {fmt_wait(posts['gap'])}, "
            f"tsikllar orasida {fmt_wait(posts['cycle'])}, "
            f"{len(posts['texts'])} ta matn. Cheklov olgan guruhga muddati tugaguncha yozmayman."
        )
    elif data.startswith("spq:"):
        if data[4:] not in accs:
            await msg.reply_text("Akkaunt topilmadi.")
            return
        ctx.user_data["mode"] = "spam_until"
        ctx.user_data["spam_acc"] = data[4:]
        await msg.reply_text(
            "Cheklov tugash sana va soatini yuboring. Masalan: 25.11 14:00 yoki 2026-11-25 14:00 "
            f"(yoki muddat: 3 kun). Vaqt zonasi: {TZ_LABEL}."
        )
    elif data.startswith("spu:"):
        _, sess, ts = data.split(":")
        a = accs.get(sess)
        if not a:
            await msg.reply_text("Akkaunt topilmadi.")
            return
        a.spam = {"state": "until", "until": float(ts)}
        save_accs()
        await msg.reply_text(f"✅ {a.label or sess}: {fmt_local(float(ts))} gacha guruhlarga yozmayman, o'sha vaqtdan boshlayman.")
    elif data.startswith("spn:"):
        a = accs.get(data[4:])
        if a:
            a.spam = None
            save_accs()
            await msg.reply_text(f"▶️ {a.label or a.session}: cheklov olib tashlandi, guruhlarga yozish davom etadi.")
    elif data.startswith("spc:"):
        a = accs.get(data[4:])
        if not a or not a.auth:
            await msg.reply_text("Akkaunt topilmadi yoki ulanmagan.")
            return
        await msg.reply_text("⏳ @SpamBot'dan so'ralmoqda...")
        await spam_probe(a, manual=True)
    elif data == "settings":
        text, kb = settings_view()
        await msg.reply_text(text, reply_markup=kb)
    elif data in ("setwin", "setquiet", "setrep", "setbak"):
        ctx.user_data["mode"] = {"setwin": "set_win", "setquiet": "set_quiet", "setrep": "set_rep", "setbak": "set_bak"}[data]
        await msg.reply_text({
            "setwin": "Guruhlarga yozish soatlarini yuboring: boshlanish va tugash soati. Masalan: 9 22 (doim yozish uchun: 0 24).",
            "setquiet": "Jim rejim soatlarini yuboring: boshlanish va tugash. Masalan: 23 7 (o'chirish uchun: 0 0).",
            "setrep": "Kunlik hisobot soatini yuboring (0-23). Masalan: 21",
            "setbak": "Zaxira nusxa soatini yuboring (0-23). Masalan: 3",
        }[data])
    elif data.startswith("setiv:") and data[6:] in INTERVALS:
        key = data[6:]
        ctx.user_data["mode"], ctx.user_data["iv_key"] = "set_iv", key
        d, name, hint = INTERVALS[key]
        await msg.reply_text(
            f"{name}: hozir {fmt_iv(iv(key))}.\n{hint}.\n\n"
            "Yangi qiymatni yuboring. Masalan: 6 soat, 30 daqiqa, 1 kun (faqat raqam yozsangiz, soat hisoblanadi). "
            f"Eng kami {IV_MIN // 60} daqiqa, eng ko'pi {IV_MAX // 86400} kun. "
            f"Standart holatga qaytarish: 0. (Standart: {fmt_iv(d)})"
        )
    elif data == "setjoin":
        conf["autojoin"] = not conf.get("autojoin", True)
        save_conf()
        text, kb = settings_view()
        await msg.reply_text(text, reply_markup=kb)
    elif data == "setdrop":
        conf["auto_drop"] = not conf.get("auto_drop", True)
        save_conf()
        text, kb = settings_view()
        await msg.reply_text(text, reply_markup=kb)
    elif data == "repnow":
        await notify(app, OWNER_ID, report_text(), force=True)
    elif data == "bakup":
        try:
            await send_backup(app)
        except Exception as e:
            await msg.reply_text(f"Zaxira yuborilmadi: {type(e).__name__}")
    elif data == "bl":
        text, kb = bl_view()
        await msg.reply_text(text, reply_markup=kb)
    elif data == "blsync":
        if bl_status["running"]:
            await msg.reply_text(f"⏳ Kanal hozir o'qilmoqda ({bl_status['n']} ta post)...")
            return
        if not live("sniper"):
            await msg.reply_text("Avval 🎯 sniper rolidagi akkaunt qo'shing (🔑).")
            return
        if time.time() < bl["retry_at"]:
            await msg.reply_text(f"Telegram cheklagan, {fmt_wait(bl['retry_at'] - time.time())}dan keyin urinib ko'ring.")
            return
        spawn(bl_sync(app, manual=True))
        await msg.reply_text("⏳ Kanal o'qilmoqda. Tugagach natijani yozaman.")
    elif data == "bltog":
        bl["on"] = not bl["on"]
        save_bl()
        await msg.reply_text("🚫 Avto-bloklash yoqildi." if bl["on"] else "⏸ Avto-bloklash o'chirildi.")
    elif data == "blun":
        if not bl["blocked"]:
            await msg.reply_text("Bot bloklagan odam yo'q.")
            return
        rows = [[InlineKeyboardButton(f"🔓 {x['who']}", callback_data=f"blun:{x['id']}")] for x in reversed(bl["blocked"][-10:])]
        await msg.reply_text("Kimni blokdan chiqaray? (istisnoga qo'shiladi, qayta bloklanmaydi)",
                             reply_markup=InlineKeyboardMarkup(rows))
    elif data.startswith("blun:"):
        ok, text = await bl_unblock(data[5:])
        await msg.reply_text(text)
    elif data == "blallow":
        ctx.user_data["mode"] = "bl_allow"
        await msg.reply_text("Hech qachon bloklanmasligi kerak bo'lgan @username yoki ID larni yuboring.")
    elif data.startswith("lrole:") and data[6:] in ROLES:
        role = data[6:]
        if not role_ok(role):
            await msg.reply_text("Bu rol uchun o'rin qolmagan. 📱 Akkauntlar orqali birortasini o'chiring.")
            return
        await ask_api(msg, ctx, role)
    elif data.startswith("accrole:"):
        a = accs.get(data[8:])
        if not a:
            await msg.reply_text("Akkaunt topilmadi.")
            return
        order = list(ROLES)
        nxt = next((r for r in (order[(order.index(a.role) + i) % 3] for i in (1, 2))
                    if role_ok(r, exclude=a)), None)
        if nxt and not role_has_name(nxt, "post") and any(g["acc"] == a.session for g in groups.values()):
            nxt = None
            await msg.reply_text("Bu akkauntga biriktirilgan guruhlar bor: avval 👥 Guruhlardan ularni o'chiring.")
            return
        if not nxt:
            await msg.reply_text("Rolni o'zgartirib bo'lmadi: boshqa rol uchun o'rin yo'q.")
            return
        a.role = nxt
        save_accs()
        await msg.reply_text(f"✅ {a.label or a.session}: {ROLE_UZ[nxt]}")
    elif data.startswith("accdel:"):
        s_ = data[7:]
        a = accs.get(s_)
        if not a:
            await msg.reply_text("Akkaunt topilmadi.")
            return
        label = a.label or s_
        await remove_acc(s_)
        await msg.reply_text(f"🗑 {label} o'chirildi (seans Telegramdan ham chiqarildi).")


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != OWNER_ID:
        return
    await do_action(q.data or "", q.message, ctx)


def add_names(names):
    """Usernamelarni kuzatuvga qo'shadi. ({nom: natija qatori}, yangi_qo'shilganlar)"""
    res, todo = {}, []
    for n in names:
        if not VALID.match(n) or "__" in n:
            res[n] = f"❌ @{n} — format yaroqsiz"
        elif n in watch:
            res[n] = f"ℹ️ @{n} — allaqachon kuzatilmoqda"
        elif len(watch) >= MAX_WATCH:
            res[n] = f"⚠️ @{n} — limit ({MAX_WATCH}) to'ldi"
        else:
            watch[n] = OWNER_ID   # darhol kuzatuvga qo'shamiz (sniper kutib o'tirmaydi)
            todo.append(n)
    if todo:
        save()
    return res, todo


async def handle_watch(update: Update, names):
    if not live("sniper"):
        await update.message.reply_text("Avval akkaunt qo'shing (🔑).")
        return
    res, todo = add_names(names)
    msg = await update.message.reply_text(
        f"🎯 {len(todo)} ta username kuzatuvga qo'shildi. Ma'lumotlar yig'ilmoqda..."
        if todo else "⏳..."
    )
    # Faollik ma'lumotini yig'ish sekin (Telegram limiti), lekin bot boshqa buyruqlarga javob beraveradi
    for i, n in enumerate(todo, 1):
        info = await describe(n)
        meta[n] = info
        res[n] = f"🎯 @{n} — kuzatuvga qo'shildi\n    ↳ {info}"
        if i % 10 == 0 and i < len(todo):
            try:
                await msg.edit_text(f"🎯 Kuzatuvga qo'shildi. Ma'lumot: {i}/{len(todo)}...")
            except Exception as _e:
                log.debug("xabarni tahrirlash xatosi: %s", type(_e).__name__)
    await send_chunks(msg, update, [res[n] for n in names])


async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    action = KB.get(update.message.text.strip())
    if action:
        # klaviatura tugmasi kirish jarayonini bekor qiladi (yorliq parol sifatida o'qilmasin)
        ctx.user_data.pop("mode", None)
        await drop_login(ctx.user_data, full=True)
        await do_action(action, update.message, ctx)
        return
    mode = ctx.user_data.get("mode")
    if mode in AUTH_MODES:
        await auth_step(update, ctx, mode)
        return
    if mode == "post_text":
        txt = update.message.text.strip()
        ctx.user_data.pop("mode", None)
        if len(posts["texts"]) >= MAX_TEXTS:
            await update.message.reply_text(f"Matn limiti ({MAX_TEXTS}) to'ldi.")
        elif txt:
            posts["texts"].append(txt[:4000])
            save_posts()
            await update.message.reply_text(f"✅ Matn qo'shildi ({len(posts['texts'])}/{MAX_TEXTS}).")
        return
    if mode == "group_add":
        ctx.user_data.pop("mode", None)
        await handle_group_add(update, update.message.text)
        return
    if mode == "spam_until":
        a = accs.get(ctx.user_data.get("spam_acc", ""))
        ts = parse_when(update.message.text)
        if ts is None:
            await update.message.reply_text("Sanani tushunmadim. Masalan: 25.11 14:00 yoki 2026-11-25 14:00 yoki 3 kun.")
            return
        ctx.user_data.pop("mode", None)
        if not a:
            await update.message.reply_text("Akkaunt topilmadi.")
            return
        a.spam = {"state": "until", "until": ts}
        save_accs()
        await update.message.reply_text(
            f"✅ {a.label or a.session}: {fmt_local(ts)} gacha guruhlarga yozmayman, o'sha vaqtdan boshlayman."
        )
        return
    if mode == "set_iv":
        key = ctx.user_data.get("iv_key")
        t = update.message.text.strip()
        if key not in INTERVALS:
            ctx.user_data.pop("mode", None)
            return
        if t == "0":
            sec = None
        else:
            sec = parse_duration(t)
            if sec is None and re.fullmatch(r"\d+", t):
                sec = int(t) * 3600
            if sec is None or not IV_MIN <= sec <= IV_MAX:
                await update.message.reply_text(
                    f"Noto'g'ri qiymat. Masalan: 6 soat, 30 daqiqa, 1 kun ({IV_MIN // 60} daqiqadan {IV_MAX // 86400} kungacha)."
                )
                return
        ivs = conf.setdefault("intervals", {})
        if sec is None:
            ivs.pop(key, None)
        else:
            ivs[key] = sec
        save_conf()
        ctx.user_data.pop("mode", None)
        ctx.user_data.pop("iv_key", None)
        text, kb = settings_view()
        await update.message.reply_text("✅ Saqlandi.\n\n" + text, reply_markup=kb)
        return
    if mode in ("set_win", "set_quiet", "set_rep", "set_bak"):
        nums = [int(x) for x in re.findall(r"\d{1,2}", update.message.text)]
        try:
            if mode in ("set_win", "set_quiet"):
                a, b = nums[0], nums[1]
                if not (0 <= a <= 23 and 0 <= b <= 24):
                    raise ValueError
                if mode == "set_win":
                    posts["from"], posts["to"] = a, b
                    save_posts()
                else:
                    conf["quiet"] = [a, b % 24]
                    save_conf()
            else:
                a = nums[0]
                if not 0 <= a <= 23:
                    raise ValueError
                conf["report_hour" if mode == "set_rep" else "backup_hour"] = a
                save_conf()
        except (IndexError, ValueError):
            await update.message.reply_text("Noto'g'ri format. Masalan: 9 22 (soatlar 0 dan 24 gacha).")
            return
        ctx.user_data.pop("mode", None)
        text, kb = settings_view()
        await update.message.reply_text("✅ Saqlandi.\n\n" + text, reply_markup=kb)
        return
    if mode == "bl_allow":
        ctx.user_data.pop("mode", None)
        found = [x.lower() for x in re.findall(r"@?([A-Za-z][A-Za-z0-9_]{3,31}|\d{5,})", update.message.text)]
        new = [x for x in found if x not in bl["allow"]]
        bl["allow"].extend(new)
        save_bl()
        await update.message.reply_text(f"✅ Istisnoga qo'shildi: {len(new)} ta." if new else "Hech narsa topilmadi.")
        return
    if mode in ("set_gap", "set_cycle"):
        txt = update.message.text
        sec = parse_duration(txt)
        if sec is None:
            m = re.fullmatch(r"\s*(\d+)\s*", txt)
            sec = int(m.group(1)) * (1 if mode == "set_gap" else 60) if m else None
        lo = MIN_GAP if mode == "set_gap" else MIN_CYCLE
        if sec is None or sec < lo:
            await update.message.reply_text(
                f"Tushunmadim yoki juda kichik (kamida {fmt_wait(lo)}). Masalan: 40 soniya yoki 10 daqiqa.")
            return
        ctx.user_data.pop("mode", None)
        if mode == "set_gap":
            posts["gap"] = sec
        else:
            posts["cycle"] = sec
            posts["next_cycle"] = min(posts["next_cycle"], time.time() + sec)
        save_posts()
        text, kb = delay_view()
        await update.message.reply_text("✅ Saqlandi.\n\n" + text, reply_markup=kb)
        return
    names = parse_names(update.message.text)[:MAX_CHECK]
    if mode == "watch":
        if not names:
            await update.message.reply_text("Username topilmadi. @ bilan boshlab yuboring (masalan @test).")
            return
        ctx.user_data.pop("mode", None)
        await handle_watch(update, names)
        return
    if not names:
        return
    msg = await update.message.reply_text("⏳ Tekshirilmoqda...")

    n_live = len(live("sniper"))
    verify_budget = {"left": MAX_VERIFY * n_live} if n_live else None

    async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
        results = await asyncio.gather(*(check(client, n, verify=verify_budget) for n in names))

    # Uzoq kirmagan akkauntlarni avtomatik kuzatuvga qo'shish
    results = list(results)
    inactive = {}   # indeks -> izoh
    notes = []
    added = 0
    has_acc = any(r.startswith("👤") for r in results)
    if has_acc and not n_live:
        notes.append("ℹ️ Avtomatik kuzatuv uchun avval akkaunt qo'shing (🔑).")
    elif has_acc:
        resolved = 0
        max_res = MAX_RESOLVE * n_live
        for i, (n, r) in enumerate(zip(names, results)):
            if not r.startswith("👤"):
                continue
            if n in watch:
                inactive[i] = "allaqachon kuzatuvda"
                continue
            if len(watch) >= MAX_WATCH:
                notes.append(f"⚠️ Kuzatuv limiti ({MAX_WATCH}) to'ldi, qolganlari qo'shilmadi.")
                break
            cached = cache_get(n) is not None
            if not cached:
                left = pool_wait("resolve")
                if left > 0:
                    notes.append(
                        f"⏳ Telegram akkaunt qidirishni yana {fmt_wait(left)} cheklagan: "
                        "avtomatik kuzatuv vaqtincha to'xtatildi (tekshiruv ishlayveradi)."
                    )
                    break
                if resolved >= max_res:
                    notes.append(
                        f"ℹ️ Bir xabarda {max_res} tadan ortiq akkaunt tekshirilmaydi "
                        "(Telegram limitidan saqlanish uchun). Qolganlarini keyin yuboring."
                    )
                    break
            try:
                old_acc, info = await inactive_info(n)
                if not cached:
                    resolved += 1
                if old_acc:
                    await add_watch(n)
                    added += 1
                    inactive[i] = info
            except (errors.FloodWaitError, PoolBlocked) as e:
                notes.append(
                    f"⏳ Telegram akkaunt qidirishni {fmt_wait(e.seconds)}ga cheklab qo'ydi: "
                    "avtomatik kuzatuv vaqtincha to'xtatildi (tekshiruv ishlayveradi)."
                )
                break
            except Exception as _e:
                log.warning("akkaunt qidirishda kutilmagan xato: %s", type(_e).__name__)
    if added:
        notes.append(f"🎯 Jami {added} ta username kuzatuvga qo'shildi.")

    # Natijani guruhlarga ajratamiz (aralashmasin)
    titles = {
        "✅": "✅ BO'SH (Telegram tasdiqlagan)",
        "❔": "❔ EHTIMOL BO'SH (tasdiqlanmagan)",
        "🎯": "🎯 UZOQ KIRMAGAN (kuzatuvda)",
        "💎": "💎 FRAGMENT'DA SOTUVDA",
        "🔒": "🔒 NFT, SOTILGAN",
        "👤": "👤 BAND (faol akkaunt)",
        "🚫": "🚫 EGALLAB BO'LMAYDI (ban/band/zaxira)",
        "❓": "❓ NOANIQ",
        "❌": "❌ YAROQSIZ FORMAT",
        "⚠": "⚠️ XATO",
    }
    groups = {}
    for i, (n, r) in enumerate(zip(names, results)):
        if i in inactive:
            key, r = "🎯", f"🎯 @{n} — {inactive[i]}"
        else:
            key = r[:1]
            if key not in titles:
                key = "❓"
        groups.setdefault(key, []).append(r)

    lines = []
    for key, title in titles.items():
        items = groups.get(key)
        if items:
            if lines:
                lines.append("")
            lines.append(f"{title} — {len(items)} ta")
            lines.extend(items)
    if notes:
        lines.append("")
        lines.extend(notes)

    await send_chunks(msg, update, lines)


# ---------- web sahifa (Telegram Web App) ----------
bg_tasks = set()


def spawn(coro):
    t = asyncio.create_task(coro)
    bg_tasks.add(t)
    t.add_done_callback(bg_tasks.discard)


async def fill_meta(names):
    for n in names:
        if n in watch:
            meta[n] = await describe(n)


def verify_init_data(init_data, max_age=86400):
    """Telegram Web App initData imzosini tekshiradi; to'g'ri bo'lsa foydalanuvchi (dict)."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        got = pairs.pop("hash", "")
        check_str = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check_str.encode(), hashlib.sha256).hexdigest()
        if not got or not hmac.compare_digest(calc, got):
            return None
        if time.time() - int(pairs.get("auth_date", "0")) > max_age:
            return None
        return json.loads(pairs.get("user", "{}"))
    except Exception:
        return None


async def web_index(request):
    return web.FileResponse(
        os.path.join(BASE_DIR, "index.html"), headers={"Cache-Control": "no-store"}
    )


async def api_state(request):
    now = time.time()
    return web.json_response({
        "now": now,
        "max": MAX_WATCH,
        "cycle": round(len(watch) * CHECK_DELAY / max(1, len(live("sniper")))),
        "watch": [{"name": n, "info": meta.get(n, ""), "t": seen.get(n)} for n in watch],
        "slots": {"max": MAX_ACCOUNTS, "sniper": [slots_used()[0], SNIPER_SLOTS], "post": [slots_used()[1], POST_SLOTS],
                  "free": {r: len(accs) < MAX_ACCOUNTS and role_ok(r) for r in ROLES}},
        "accs": [
            {"label": a.label or a.session, "ok": a.auth, "claimed": a.claimed, "role": a.role,
             "blocks": {k: round(v) for k, v in a.block.items() if v > now},
             "spam": ({"state": a.spam.get("state"), "until": a.spam.get("until", 0)} if a.spam else None)}
            for a in accs.values()
        ],
        # hamma akkaunt cheklangan bo'lsa: tur -> cheklov tugash vaqti (epoch)
        "pool": {k: round(now + w) for k in ("check", "resolve", "claim")
                 for w in [pool_wait(k)] if w > 0},
        "events": [{"t": t, "text": x} for t, x in reversed(events)],
        "recheck": dict(recheck),
        "post": {"on": posts["on"], "gap": posts["gap"], "cycle": posts["cycle"], "texts": len(posts["texts"]),
                 "next_cycle": posts["next_cycle"], "running": bool(cyc["queue"])},
        "bl": {
            "channel": BL_CHANNEL, "on": bl["on"], "users": len(bl["users"]), "ids": len(bl["ids"]),
            "phones": len(bl["phones"]), "synced": bl["synced"], "count": bl["count"], "allow": len(bl["allow"]),
            "running": bl_status["running"], "n": bl_status["n"],
            "retry": bl["retry_at"] if bl["retry_at"] > now else 0,
            "blocked": [{"id": x["id"], "who": x["who"], "by": x["by"], "post": x["post"], "t": x["t"]}
                        for x in reversed(bl["blocked"])],
        },
        "groups": [
            {"title": g["title"], "enabled": g["enabled"], "kind": g["kind"], "sent": g["sent"],
             "forever": g["pause_until"] >= FOREVER,
             "until": g["pause_until"] if now < g["pause_until"] < FOREVER else 0,
             "next": g["next_at"]}
            for g in groups.values()
        ],
    })


async def api_add(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Noto'g'ri so'rov"}, status=400)
    raw = body.get("names", "")
    if isinstance(raw, str):
        raw = re.findall(r"[A-Za-z0-9_]+", raw)
    names = []
    for x in raw:
        n = str(x).strip().lstrip("@").lower()
        if n and n not in names:
            names.append(n)
    names = names[:MAX_CHECK]
    if not names:
        return web.json_response({"error": "Username topilmadi"}, status=400)
    if not live("sniper"):
        return web.json_response({"error": "Avval botda 🎯 sniper rolidagi akkaunt qo'shing (🔑)."}, status=409)
    res, todo = add_names(names)
    if todo:
        spawn(fill_meta(todo))
    return web.json_response({"added": todo, "skipped": [res[n] for n in names if n not in todo]})


# ---------- web orqali akkaunt qo'shish ----------
WEB_LOGIN_TTL = 600
wl = {}   # {"lc","session","creds","role","phone","hash","step","t"}: bir vaqtda bitta kirish (faqat egasi)


async def wl_drop():
    lc, sess = wl.get("lc"), wl.get("session")
    wl.clear()
    if lc:
        try:
            await lc.disconnect()
        except Exception as _e:
            log.debug("disconnect xatosi: %s", type(_e).__name__)
    if sess and sess not in accs:
        try:
            os.remove(sess + ".session")
        except FileNotFoundError:
            pass
        except OSError as _e:
            log.warning("seans fayli o'chirilmadi: %s", _e)


def wl_err(msg, status=400):
    return web.json_response({"error": msg}, status=status)


async def wl_body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


async def wl_done(step_ok_msg=None):
    lc, session, role, creds = wl["lc"], wl["session"], wl["role"], wl.get("creds")
    wl.clear()
    a, err = await register_login(lc, session, role, creds)
    if not a:
        return wl_err(err, 409)
    return web.json_response({"step": "done", "label": a.label})


async def api_acc_start(request):
    b = await wl_body(request)
    role = str(b.get("role", ""))
    if role not in ROLES:
        return wl_err("Rolni tanlang.")
    if len(accs) >= MAX_ACCOUNTS:
        return wl_err(f"Akkauntlar limiti to'ldi ({MAX_ACCOUNTS} ta).", 409)
    if not role_ok(role):
        return wl_err("Bu rol uchun o'rin qolmagan.", 409)
    api_id, api_hash = str(b.get("api_id", "")).strip(), str(b.get("api_hash", "")).strip()
    if not api_id.isdigit():
        return wl_err("api_id faqat raqamlardan iborat.")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        return wl_err("api_hash 32 ta harf-raqamdan iborat.")
    digits = re.sub(r"\D", "", str(b.get("phone", "")))
    if not 7 <= len(digits) <= 15:
        return wl_err("Telefon raqam noto'g'ri. +998901234567 shaklida yozing.")
    phone = "+" + digits
    await wl_drop()
    creds = (int(api_id), api_hash)
    session = new_session()
    client = TelegramClient(session, *creds)
    wl.update(lc=client, session=session, creds=creds, role=role, step="starting", t=time.time())
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
    except errors.PhoneNumberInvalidError:
        await wl_drop()
        return wl_err("Raqam noto'g'ri.")
    except errors.ApiIdInvalidError:
        await wl_drop()
        return wl_err("api_id/api_hash noto'g'ri.")
    except errors.FloodWaitError as e:
        await wl_drop()
        return wl_err(f"Juda ko'p urinish. {fmt_wait(e.seconds)}dan keyin qayta urining.", 429)
    except Exception as e:
        await wl_drop()
        return wl_err(f"Xato: {type(e).__name__}")
    secure(session + ".session")
    wl.update(phone=phone, hash=sent.phone_code_hash, step="code", t=time.time())
    return web.json_response({"step": "code", "where": code_where(getattr(sent, "type", None)),
                              "can_resend": getattr(sent, "next_type", None) is not None})


def wl_active(step):
    if not wl or wl.get("step") != step:
        return False
    if time.time() - wl.get("t", 0) > WEB_LOGIN_TTL:
        return False
    return True


async def api_acc_resend(request):
    if not wl_active("code"):
        return wl_err("Seans eskirdi. Qaytadan boshlang.", 409)
    try:
        sent = await wl["lc"](ResendCodeRequest(wl["phone"], wl["hash"]))
    except errors.FloodWaitError as e:
        return wl_err(f"Juda ko'p urinish. {fmt_wait(e.seconds)}dan keyin qayta urining.", 429)
    except Exception as e:
        return wl_err(f"Qayta yuborib bo'lmadi ({type(e).__name__}). Bekor qilib, bir ozdan keyin qayta urining.")
    wl.update(hash=sent.phone_code_hash, t=time.time())
    return web.json_response({"step": "code", "where": code_where(getattr(sent, "type", None)),
                              "can_resend": getattr(sent, "next_type", None) is not None})


async def api_acc_code(request):
    b = await wl_body(request)
    if not wl_active("code"):
        await wl_drop()
        return wl_err("Seans eskirdi. Qaytadan boshlang.", 409)
    code = re.sub(r"\D", "", str(b.get("code", "")))
    if not code:
        return wl_err("Kodni kiriting.")
    try:
        await wl["lc"].sign_in(wl["phone"], code, phone_code_hash=wl["hash"])
    except errors.SessionPasswordNeededError:
        wl.update(step="password", t=time.time())
        return web.json_response({"step": "password"})
    except errors.PhoneCodeInvalidError:
        return wl_err("Kod noto'g'ri. Qayta kiriting.")
    except errors.PhoneCodeExpiredError:
        await wl_drop()
        return wl_err("Kod eskirdi. Qaytadan boshlang.", 409)
    except errors.FloodWaitError as e:
        return wl_err(f"Juda ko'p urinish. {fmt_wait(e.seconds)}dan keyin qayta urining.", 429)
    except Exception as e:
        return wl_err(f"Xato: {type(e).__name__}")
    return await wl_done()


async def api_acc_password(request):
    b = await wl_body(request)
    if not wl_active("password"):
        await wl_drop()
        return wl_err("Seans eskirdi. Qaytadan boshlang.", 409)
    pw = str(b.get("password", ""))
    if not pw:
        return wl_err("Parolni kiriting.")
    try:
        await wl["lc"].sign_in(password=pw)
    except errors.PasswordHashInvalidError:
        return wl_err("Parol noto'g'ri. Qayta kiriting.")
    except errors.FloodWaitError as e:
        return wl_err(f"Juda ko'p urinish. {fmt_wait(e.seconds)}dan keyin qayta urining.", 429)
    except Exception as e:
        return wl_err(f"Xato: {type(e).__name__}")
    return await wl_done()


async def api_acc_cancel(request):
    await wl_drop()
    return web.json_response({"ok": True})


async def api_remove(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Noto'g'ri so'rov"}, status=400)
    n = str(body.get("name", "")).strip().lstrip("@").lower()
    if n in watch:
        await drop(n)
    return web.json_response({"ok": True})


recheck = {"running": False, "done": 0, "total": 0, "last": 0.0, "next": 0.0, "cut": False}


async def recheck_all(auto=False):
    """Kuzatuvdagi hamma usernamening faollik ma'lumotini Telegramdan qayta oladi.
    Telegram akkaunt qidirishni cheklasa, to'xtaydi (cut=True) va cheklov tugagach davom ettiriladi."""
    if recheck["running"]:
        return
    names = sorted(watch, key=lambda n: checked.get(n, 0))   # eng uzoq tekshirilmaganlardan boshlaymiz
    dropped = []
    recheck.update(running=True, done=0, total=len(names), cut=False)
    try:
        for n in names:
            if n not in watch:
                recheck["done"] += 1
                continue
            if pool_wait("resolve") > 0:
                recheck["cut"] = True
                break
            info, active = await check_activity(n)
            if info is None:
                if pool_wait("resolve") > 0:
                    recheck["cut"] = True
                    break
            else:
                meta[n] = info
                checked[n] = time.time()
                if active and conf.get("auto_drop", True):
                    await drop(n)     # akkaunt faol: bo'shamaydi, kuzatuv befoyda
                    dropped.append((n, info))
            recheck["done"] += 1
    finally:
        recheck["running"] = False
        recheck["last"] = time.time()
        text = f"🔄 Qayta tekshirish: {recheck['done']}/{recheck['total']}"
        if auto:
            if recheck["cut"]:
                text += "\nTelegram akkaunt qidirishni cheklagan, cheklov tugagach o'zi davom etadi."
            await notify(app, OWNER_ID, text)
        else:
            log_event(text + (" (Telegram cheklovi sabab to'xtadi)" if recheck["cut"] else ""))
        if dropped:
            await notify(app, OWNER_ID, "🗑 Faol bo'lgani uchun kuzatuvdan chiqarildi:\n"
                         + "\n".join(f"@{n}: {info}" for n, info in dropped))


async def api_recheck(request):
    if recheck["running"]:
        return web.json_response({"error": "Tekshiruv allaqachon ketmoqda"}, status=409)
    if not watch:
        return web.json_response({"error": "Ro'yxat bo'sh"}, status=400)
    if not live("sniper"):
        return web.json_response({"error": "Avval botda 🎯 sniper rolidagi akkaunt qo'shing (🔑)."}, status=409)
    left = pool_wait("resolve")
    if left > 0:
        return web.json_response(
            {"error": f"Telegram akkaunt qidirishni {fmt_wait(left)}ga cheklagan. Cheklov tugagach bot o'zi tekshiradi."},
            status=409,
        )
    spawn(recheck_all())
    return web.json_response({"started": True})


async def recheck_loop(app):
    """Har RECHECK_EVERY da avtomatik qayta tekshiradi; cheklov tufayli to'xtagan bo'lsa, cheklov tugashini kutadi."""
    await asyncio.sleep(60)
    while True:
        try:
            if watch and live("sniper"):
                await recheck_all(auto=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("recheck_loop xatosi")
        wait = max(60, pool_wait("resolve") + 5) if recheck["cut"] else iv("recheck_every")
        recheck["next"] = time.time() + wait
        await asyncio.sleep(wait)


async def api_bl_toggle(request):
    bl["on"] = not bl["on"]
    save_bl()
    return web.json_response({"on": bl["on"]})


async def api_bl_sync(request):
    if bl_status["running"]:
        return web.json_response({"error": "Kanal hozir o'qilmoqda"}, status=409)
    if not live("sniper"):
        return web.json_response({"error": "Avval botda 🎯 sniper rolidagi akkaunt qo'shing (🔑)."}, status=409)
    if time.time() < bl["retry_at"]:
        return web.json_response(
            {"error": f"Telegram cheklagan, {fmt_wait(bl['retry_at'] - time.time())}dan keyin urinib ko'ring."}, status=409)
    spawn(bl_sync(app, manual=True))
    return web.json_response({"started": True})


async def api_bl_unblock(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Noto'g'ri so'rov"}, status=400)
    ok, text = await bl_unblock(body.get("id", ""))
    return web.json_response({"ok": ok, "text": text}, status=200 if ok else 409)


_rl = {}   # kalit -> so'rov vaqtlari (oynali tezlik chegarasi)


def rate_ok(key, limit, window=60):
    now = time.time()
    if len(_rl) > 2000:
        _rl.clear()
    q = _rl.setdefault(key, deque())
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def make_web():
    @web.middleware
    async def auth_mw(request, handler):
        if request.path.startswith("/api/"):
            user = verify_init_data(request.headers.get("X-Init-Data", ""))
            if not user or user.get("id") != OWNER_ID:
                ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                      or request.remote or "?")
                if not rate_ok("fail:" + ip, 20):
                    return web.json_response({"error": "too many requests"}, status=429)
                return web.json_response({"error": "unauthorized"}, status=401)
            if not rate_ok("owner", 600):
                return web.json_response({"error": "too many requests"}, status=429)
        return await handler(request)

    w = web.Application(middlewares=[auth_mw], client_max_size=64 * 1024)
    w.add_routes([
        web.get("/", web_index),
        web.get("/api/state", api_state),
        web.post("/api/add", api_add),
        web.post("/api/remove", api_remove),
        web.post("/api/acc/start", api_acc_start),
        web.post("/api/acc/resend", api_acc_resend),
        web.post("/api/acc/code", api_acc_code),
        web.post("/api/acc/password", api_acc_password),
        web.post("/api/acc/cancel", api_acc_cancel),
        web.post("/api/recheck", api_recheck),
        web.post("/api/bl/toggle", api_bl_toggle),
        web.post("/api/bl/sync", api_bl_sync),
        web.post("/api/bl/unblock", api_bl_unblock),
    ])
    return w


async def start_web(application):
    if WEBAPP_URL and not web:
        log.warning("WEBAPP_URL berilgan, lekin aiohttp o'rnatilmagan: pip install aiohttp")
    if not WEB_ON:
        return
    try:
        runner = web.AppRunner(make_web())
        await runner.setup()
        await web.TCPSite(runner, WEB_HOST, WEB_PORT).start()
        application.bot_data["web"] = runner
    except Exception as e:
        log.warning("web server ishga tushmadi: %s", e)


COMMANDS = [
    ("kuzatuv", "Kuzatuv ro'yxati va qo'shish"),
    ("guruhlar", "Guruhlarga avto post"),
    ("akkauntlar", "Akkauntlar va cheklovlar"),
    ("voqealar", "So'nggi voqealar"),
    ("blok", "Blok ro'yxati (mashkalar)"),
    ("start", "Pastdagi menyuni ochish"),
]
SECTIONS = {
    "kuzatuv": "🎯 Kuzatuv",
    "guruhlar": "👥 Guruhlar",
    "akkauntlar": "📱 Akkauntlar",
    "blok": "🚫 Blok ro'yxati",
    "voqealar": "🕘 So'nggi voqealar",
}


def events_text():
    if not events:
        return "Hozircha voqea yo'q."
    rows = [f"{time.strftime('%H:%M', time.localtime(t))}  {x}" for t, x in list(events)[-15:]]
    return "🕘 So'nggi voqealar:\n" + "\n".join(reversed(rows))


async def open_section(msg, name, ctx):
    """Chapdagi menyu bo'limi: web sahifani shu bo'limda ochadi (web yo'q bo'lsa, matn ko'rinishida)."""
    if WEB_ON:
        await msg.reply_text(
            SECTIONS[name],
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Ochish", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?tab={name}"))]]
            ),
        )
    elif name == "kuzatuv":
        await do_action("list", msg, ctx)
    elif name == "guruhlar":
        await do_action("groups", msg, ctx)
    elif name == "akkauntlar":
        await do_action("accs", msg, ctx)
    elif name == "blok":
        await do_action("bl", msg, ctx)
    else:
        await msg.reply_text(events_text())


async def blok_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await do_action("bl", update.message, ctx)


async def section_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.lstrip("/").split("@")[0].split()[0].lower()
    if name in SECTIONS:
        await open_section(update.message, name, ctx)


async def setup_ui(application):
    """Chap ko'k tugma: web sahifa (WEBAPP_URL bo'lsa), bo'lmasa buyruqlar ro'yxati. Buyruqlar / orqali ishlayveradi."""
    try:
        await application.bot.set_my_commands(
            [BotCommand(c, d) for c, d in COMMANDS], scope=BotCommandScopeChat(chat_id=OWNER_ID)
        )
        if WEB_ON:   # ko'k tugma buyruqlar ro'yxati o'rniga to'g'ridan-to'g'ri web sahifani ochadi
            btn = MenuButtonWebApp(text="🌐 Web", web_app=WebAppInfo(url=WEBAPP_URL))
        else:
            btn = MenuButtonCommands()
        await application.bot.set_chat_menu_button(chat_id=OWNER_ID, menu_button=btn)
    except Exception as e:
        log.warning("menyu o'rnatilmadi: %s", e)


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    log.error("Handler xatosi", exc_info=ctx.error)


async def post_init(application):
    load_accs()
    for a in list(accs.values()):
        try:
            await connect_acc(a)
        except Exception as e:
            log.warning("%s ulanmadi: %s", a.session, e)
    harden()
    await setup_ui(application)
    await start_web(application)
    application.bot_data["tasks"] = [
        asyncio.create_task(sniper_loop(application)),
        asyncio.create_task(maintain_loop(application)),
        asyncio.create_task(recheck_loop(application)),
        asyncio.create_task(poster_loop(application)),
        asyncio.create_task(bl_loop(application)),
        asyncio.create_task(report_loop(application)),
        asyncio.create_task(spam_loop(application)),
    ]
    print("Bot ishga tushdi. Faol akkauntlar:", len(live()), "/", len(accs), "| ma'lumotlar papkasi:", os.getcwd())
    if os.environ.get("RAILWAY_ENVIRONMENT_NAME") and not DATA_DIR:
        await notify(application, OWNER_ID,
                     "⚠️ Railway'da Volume ulanmagan: akkaunt seanslari va sozlamalar qayta deploydan keyin o'chib ketadi. "
                     "Volume yarating (mount: /data).")


async def post_shutdown(application):
    for t in application.bot_data.get("tasks", []):
        t.cancel()
    runner = application.bot_data.get("web")
    if runner:
        await runner.cleanup()
    for a in accs.values():
        if a.client:
            try:
                await a.client.disconnect()
            except Exception as _e:
                log.debug("mijozni uzishda xato: %s", type(_e).__name__)


app = (
    ApplicationBuilder()
    .token(TOKEN)
    .concurrent_updates(True)     # uzoq vazifa (masalan 200 ta username) botni qotirib qo'ymaydi
    .post_init(post_init)
    .post_shutdown(post_shutdown)
    .build()
)
OWNER_ONLY = filters.User(user_id=OWNER_ID) & filters.ChatType.PRIVATE
app.add_handler(CommandHandler("start", start, filters=OWNER_ONLY))
app.add_handler(CommandHandler(list(SECTIONS), section_cmd, filters=OWNER_ONLY))
app.add_handler(CallbackQueryHandler(on_button))   # ichida egasi tekshiriladi
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & OWNER_ONLY, handle))
app.add_error_handler(on_error)
app.run_polling()
