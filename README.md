# 👕 Kledingkast

Een zelf-gehoste, mobiel-vriendelijke web-app om je kledingkast te inventariseren
(met foto's, merk, categorie, kleur, maat…) en om samen met je partner te bepalen
welke stukken bij elkaar passen — via een **Tinder-achtige swipe**.

- 📷 **Inventariseren** – foto maken met je telefoon, merk/categorie/kleur/maat/seizoen noteren.
- 🗂️ **Categorieën** – polo, t-shirt, trui, vest, hoodie, broek, shorts, schoenen… (vrij aan te vullen).
- 💞 **Combineren** – swipe per kledingstuk of het bij een ander past. Rechts = past, links = past niet.
- ✨ **Outfits** – bekijk per stuk alle goedgekeurde combinaties, met wie ze goedkeurde.
- 🚪 **Eigen kast per gebruiker** – iedereen heeft z'n eigen kledingkast.
- 🤝 **Delen** – nodig iemand uit voor je kast als **bewerker** (mag alles aanpassen)
  of **kijker** (alleen inzage, maar mag wél meestemmen op combinaties).
- 👥 **Accounts** – jij én je partner een eigen login. Een **beheerder** kan bij
  elke kast, en heeft daarnaast ook gewoon z'n eigen kast.
- 📱 **PWA** – installeerbaar op je telefoon (Toevoegen aan beginscherm).

Techniek: **FastAPI + SQLite + Pillow** (backend) en **React + Vite** (frontend),
samen in **één Docker-image**. Achter je bestaande nginx als reverse-proxy.

---

## Snel starten (Docker)

Op je Ubuntu-server:

```bash
git clone <deze-repo> kledingkast && cd kledingkast
cp .env.example .env
# genereer een geheime sleutel en zet 'm in .env (WARDROBE_SECRET_KEY):
openssl rand -hex 32
nano .env            # sleutel + admin-wachtwoord invullen
docker compose up -d
```

`docker compose` haalt de kant-en-klare image op van de GitHub Container
Registry (`ghcr.io/bobvmierlo/wardrobe`), gebouwd door de GitHub Actions-
workflow. Bijwerken naar een nieuwe versie doe je met:

```bash
docker compose pull && docker compose up -d
```

De app draait nu op `http://127.0.0.1:8000` (alleen lokaal). Zet je bestaande
nginx ervoor met [`deploy/nginx.conf.example`](deploy/nginx.conf.example) en
regel HTTPS met certbot.

> Zelf bouwen in plaats van de gepubliceerde image gebruiken? Draai
> `docker compose -f docker-compose.yml build` niet — voeg een `build: .`
> toe of gebruik `docker build -t kledingkast .` en pas de `image:` in
> `docker-compose.yml` aan.

> Wil je 'm direct op je LAN i.p.v. achter nginx? Zet in `docker-compose.yml`
> de poort op `"8000:8000"`.

### Eerste login

1. Ga naar de app en log in met `WARDROBE_ADMIN_USERNAME` / `WARDROBE_ADMIN_PASSWORD` uit je `.env`.
2. Ga naar **Instellingen → Wachtwoord wijzigen** en kies een eigen wachtwoord.
3. Maak onder **Instellingen → Accounts** een account voor je partner aan.
   Zij logt daarna op haar eigen telefoon in en kan meteen meeswipen.

---

## Configuratie

Alles via omgevingsvariabelen (zie `.env.example`):

| Variabele | Standaard | Uitleg |
|---|---|---|
| `WARDROBE_SECRET_KEY` | — (**verplicht**) | Ondertekent login-tokens. Lang en willekeurig. |
| `WARDROBE_ADMIN_USERNAME` | `admin` | Beheerder, alleen aangemaakt bij lege database. |
| `WARDROBE_ADMIN_PASSWORD` | `changeme` | Wachtwoord van die beheerder. |
| `WARDROBE_ADMIN_DISPLAY_NAME` | `Beheerder` | Weergavenaam. |
| `WARDROBE_MAX_UPLOAD_MB` | `15` | Max fotogrootte. |
| `WARDROBE_DATA_DIR` | `/data` (in Docker) | Waar SQLite-db + foto's staan. |

Foto's worden bij upload automatisch geroteerd (EXIF), verkleind (max 1280px)
en als JPEG opgeslagen, plus een thumbnail — zodat de kast licht blijft.

---

## Back-up

Alle data (database + foto's) staat in het Docker-volume `kledingkast-data`.
Een back-up maken:

```bash
docker run --rm -v kledingkast-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/kledingkast-backup.tar.gz -C /data .
```

Terugzetten: draai hetzelfde met `tar xzf` in `/data`.

---

## Lokaal ontwikkelen (zonder Docker)

Twee terminals:

```bash
# 1) backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export WARDROBE_SECRET_KEY=dev
uvicorn app.main:app --reload --port 8000
```

```bash
# 2) frontend (proxyt /api en /uploads naar :8000)
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Standaard-admin bij eerste start: `admin` / `changeme`.

---

## Projectstructuur

```
backend/            FastAPI-app (Python)
  app/
    main.py         app + seed-admin + serveert de gebouwde frontend
    models.py       User, Item, Match (SQLAlchemy)
    routers/        auth, users, items, matches
    images.py       foto-verwerking (Pillow)
    matching.py     categorie-groepen voor slimme combinatie-suggesties
frontend/           React + Vite (TypeScript)
  src/pages/        Login, Wardrobe, AddItem, ItemDetail, Combine, Outfits, Settings
  src/components/   SwipeCard, ItemForm, BottomNav
Dockerfile          multi-stage build (frontend → python runtime)
docker-compose.yml  container + datavolume
deploy/             nginx-voorbeeldconfig
```

---

## Hoe "past bij elkaar" werkt

- Elke swipe slaat jouw oordeel op voor dát paar (ja/nee), per gebruiker.
- Bij **Outfits** geldt een combinatie als goedgekeurd wanneer minstens één
  huisgenoot **ja** zei én niemand **nee**. Zo blokkeert een "nee" van je
  partner een combinatie die jij goedkeurde (handig — zij heeft vaak gelijk 😉).
- De swipe toont eerst **cross-categorie**-paren (bv. polo × broek) omdat die
  het nuttigst zijn; twee stukken uit dezelfde groep komen later.

---

## Ideeën voor later

Zie de "Verbeteringen" hieronder — o.a. gedeelde outfit-looks (top+broek+schoenen
als één setje opslaan), filteren op seizoen/gelegenheid, en automatische
kleurherkenning uit de foto.

## Licentie

Vrij te gebruiken en aan te passen voor eigen gebruik.
