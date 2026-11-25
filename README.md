# Username sniper boti

## Fayllar
| Fayl | Vazifasi |
|---|---|
| `main.py` | Asosiy bot (hamma funksiyalar) |
| `index.html` | Telegram Web App sahifasi (`main.py` bilan bir papkada) |
| `login.py` | Akkauntni terminaldan qo'shish (lokal ishga tushirishda) |
| `requirements.txt`, `.python-version`, `railway.json` | Kutubxonalar, Python versiyasi, Railway sozlamasi |
| `.gitignore` | Seans va maxfiy fayllar GitHub'ga chiqmasligi uchun |

## GitHub'ga yuklash
**Muhim:** repo PRIVATE (yopiq) bo'lsin. `*.session`, `config.json` va `*.json` ma'lumot fayllari `.gitignore` da: ularni yuklamang.

Git bilan:
```
git init
git add .
git status        # .session yoki config.json ko'rinmasligi kerak
git commit -m "Birinchi versiya"
git branch -M main
git remote add origin https://github.com/FOYDALANUVCHI/REPO.git
git push -u origin main
```
Git'siz: github.com da yangi **Private** repo yarating, **Add file > Upload files** orqali fayllarni tashlang
(`.gitignore` va `.python-version` ham kerak; zip ichida bor).

## Railway'ga joylash
1. railway.com > **New Project > Deploy from GitHub repo** > reponi tanlang.
2. **Variables** bo'limiga qo'shing:
   - `BOT_TOKEN`: @BotFather tokeni
   - `OWNER_ID`: sizning Telegram ID raqamingiz (bot faqat shunga ishlaydi)
   - `API_ID`, `API_HASH`: ixtiyoriy (endi har akkaunt uchun botning o'zida alohida so'raladi)
   - `TZ_NAME`: `Asia/Tashkent` (ixtiyoriy)
3. **Volume yarating** (project canvas'da o'ng tugma yoki Cmd/Ctrl+K > Create Volume), servisga ulang, mount path: `/data`.
   Busiz seanslar va sozlamalar har deploydan keyin o'chadi. Bot `RAILWAY_VOLUME_MOUNT_PATH` ni o'zi topadi.
4. Servis **Settings > Networking > Generate Domain**. Bot `RAILWAY_PUBLIC_DOMAIN` dan web manzilni o'zi oladi
   (domen yaratilgach qayta deploy qiling).
5. Logda `Bot ishga tushdi` chiqsa, tayyor. Botga `/start` yuboring.
6. Akkaunt qo'shish (ko'pi bilan **5 ta**: 🎯 3 ta sniper + 📣 2 ta avto post; qo'shishda bot rolni so'raydi: sniper / avto post / ikkalasi): botda **🔑 Akkaunt qo'shish**: har bir akkaunt uchun o'zining api_id, api_hash, telefon, kod
   (raqamlar orasiga bo'sh joy: `1 2 3 4 5`) va kerak bo'lsa 2 bosqichli parol.
   `login.py` Railway'da kerak emas.

Eslatma: faqat BITTA nusxa (replica) ishlasin: bir seansni ikki joyda ishlatish seansni o'ldiradi.
Botni lokal kompyuterda ham ishlatmang (token va seanslar bir vaqtda ikki joyda bo'lmasin).

## Lokal ishga tushirish
`pip install -r requirements.txt`, so'ng `BOT_TOKEN`, `OWNER_ID`, `API_ID`, `API_HASH` ni muhitga yozing,
`python login.py`, `python main.py`. Web uchun HTTPS kerak: `cloudflared tunnel --url http://localhost:8080`
va `WEBAPP_URL=https://...`.

## Bot menyusi
- **🔑 Akkaunt qo'shish / 📱 Akkauntlar**: akkauntlar havzasi, 🛡 SpamBot tekshiruvi
- **🎯 Kuzatuvga qo'shish / 📋 Ro'yxat / 🗑 Tozalash**: username kuzatuvi va egallash
- **📣 Post matni / 👥 Guruhlar / ⏱ Kechikish / ▶️ Avto post**: guruhlarga avto post
- **🚫 Blok ro'yxati**: kanal postlaridan ro'yxat, avto-bloklash, istisnolar
- **⚙️ Sozlamalar**: post soatlari, jim rejim, hisobot va zaxira soati hamda vaqt oraliqlari (faollikni qayta tekshirish, SpamBot tekshiruvi, blok kanalini yangilash, warn va noma'lum cheklov pauzasi): hammasi qo'lda yoziladi
- Chapdagi ko'k tugma (🌐 Web) to'g'ridan-to'g'ri web sahifani ochadi (WEBAPP_URL bo'lsa; bo'lmasa buyruqlar ro'yxati). Buyruqlar `/kuzatuv`, `/guruhlar`, `/akkauntlar`, `/blok`, `/voqealar` xabar maydoniga `/` yozilganda ham ishlaydi

## Qoidalar
- Guruhda ban, mute, warn olinsa, shu guruhga cheklov tugaguncha yozilmaydi.
- @SpamBot cheklasa, yozish to'xtaydi; bot muddatni so'raydi va kiritilgan kundan davom etadi.
- Telegram FloodWait bo'lsa, akkaunt shu amal uchun to'xtaydi; taymer web sahifada ko'rinadi.
- Bot guruhga o'zi qo'shilmaydi; akkaunt oldindan a'zo bo'lishi kerak.

## Sozlamalar (`main.py` tepasida)
`CHECK_DELAY`, `MAX_CHECK`, `MAX_WATCH` (300), `MIN_GAP` (40 s), `MIN_CYCLE` (5 daq), `DEFAULT_GAP` (40 s), `DEFAULT_CYCLE` (10 daq), `POST_HOURLY_CAP` (60 post/soat har akkauntga), `SLOW_MAX`/`SLOW_STEP`/`SLOW_RECOVER` (FloodWaitdan keyin tekshiruvni avtomatik sekinlashtirish), `MAX_GROUPS` (40),
`WARN_PAUSE` (24 soat), `RECHECK_EVERY` (6 soat), `SYNC_EVERY` (30 daq), `SPAM_CHECK_EVERY` (6 soat), `BL_CHANNEL`.

## Zaxira
Har kuni botdan zip keladi (kuzatuv, guruhlar, postlar, blok ro'yxati, sozlamalar; seans va `config.json` kiritilmagan).
Railway Volume'ning o'zida ham zaxira (backup) yoqish mumkin.

## Xavfsizlik
Seans fayllari akkauntga to'liq kirish beradi: GitHub'ga yuklamang, hech kimga bermang.
Bir xil matnni ko'p guruhga tez yuborish Telegramda spam hisoblanadi va akkauntni cheklatishi mumkin.

## Telegram cheklovidan saqlanish (nima o'zgargan)
- Guruhlar orasidagi pauza kamida 40 soniya (+0-25% tasodifiy qo'shimcha). Eski saqlangan qisqa qiymat ham 40 ga ko'tariladi.
- Tsikllar orasida kamida 5 daqiqa; har akkaunt soatiga ko'pi bilan 60 ta post yuboradi.
- Sniper tekshiruvi FloodWait olsa, shu akkauntning pauzasi 1.5 baravar uzayadi (4 baravargacha), 1 soat tinch o'tsa asta-sekin qaytadi.
- Blok ro'yxati (avto-bloklash) sukut bo'yicha O'CHIQ. Yoqishdan oldin kanal ro'yxatini ko'rib chiqing.
- Egallashda kanal ochilib, entity olinmasa, yetim kanal qolmaydi (o'chiriladi).
- Maslahat: bir xil matnni ko'p guruhga yubormang, bir nechta matn qo'shing (navbat bilan aylanadi); faqat o'zingiz a'zo va yozish ruxsati bor guruhlarga yuboring.

## Akkaunt rollari
- Akkaunt qo'shayotganda bot rolni so'raydi: 🎯 sniper, 📣 avto post yoki ikkalasi. Limit: 5 ta akkaunt, shundan 3 tasi sniper, 2 tasi avto post (ikkalasi rolidagi akkaunt ikkala o'rinni ham oladi).
- Sniper akkauntlar username tekshirish/egallash uchun, avto post akkauntlar guruhlarga yozish uchun ishlatiladi: bir-birining ishiga aralashmaydi.
- Rolni 📱 Akkauntlar bo'limidagi 🔁 Rol tugmasi bilan o'zgartirish mumkin (avto postdan chiqarish uchun akkauntga biriktirilgan guruhlar bo'lmasligi kerak).
- Lokal qo'shish: `python login.py acc2 post` (rol: sniper | post | both). Rol bermasangiz `both`.

## Bot talabi bilan avto qo'shilish
- Avto post guruhida bot (masalan obuna tekshiruvchi) akkauntga javob yozib yoki tilga olib "kanalga obuna bo'ling / guruhga qo'shiling" desa, akkaunt shu ochiq kanal/guruhga (t.me/username) o'zi qo'shiladi va egasiga xabar beradi.
- Qo'shilgan joy guruh bo'lsa (yozish ruxsati bor bo'lsa), postlar ro'yxatiga ham qo'shiladi va 1-3 daqiqadan keyin habar yuboriladi. Kanal bo'lsa faqat a'zo bo'linadi.
- Xavfsizlik: faqat akkauntga qaratilgan (reply/mention) va shu guruhda **admin bo'lgan** bot xabarlari (oddiy a'zo yoki admin bo'lmagan bot talabi e'tiborga olinmaydi), har akkaunt sutkasiga 10 tagacha qo'shilish (`JOIN_DAILY_CAP`), qo'shilishdan oldin 8-25 soniya pauza, bir havolaga 6 soat ichida qayta qo'shilmaydi, FloodWait bo'lsa to'xtaydi. Yopiq (taklif) havolalar va botlarga qo'shilmaydi.
- ⚙️ Sozlamalar → ➕ Avto qo'shilish tugmasi bilan yoqish/o'chirish (sukut bo'yicha yoqilgan).

## Loglar va himoya
- `LOG_LEVEL` (ixtiyoriy, sukut `WARNING`): `DEBUG` qo'ysangiz yutilgan mayda xatolar ham chiqadi.
- Web API: noto'g'ri imzoli so'rovlar IP bo'yicha daqiqasiga 20 tadan oshsa 429 qaytadi; egasi uchun daqiqasiga 600.
- Fragment sahifa formati o'zgarsa, logda bir marta ogohlantirish chiqadi.
- Guruhda oddiy foydalanuvchi akkauntni tilga olsa (@mention) yoki uning xabariga javob yozsa, botdan egasiga xabar keladi (ism, username, matn, havola). Bir odamdan 10 daqiqada 3 tagacha, jami 30 tagacha; jim rejimda keyinroq yig'ma xabar bilan keladi. Faqat avto post ro'yxatidagi guruhlar uchun.
