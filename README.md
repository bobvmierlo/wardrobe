# 👕 Kledingkast

Een zelf-gehoste, mobiel-vriendelijke web-app om je kledingkast te inventariseren
(met foto's, merk, categorie, kleur, maat…) en om samen met je partner te bepalen
welke stukken bij elkaar passen — via een **Tinder-achtige swipe**.

- 📷 **Inventariseren** – foto maken met je telefoon, merk/categorie/kleur/maat/seizoen noteren.
- 🗂️ **Categorieën** – polo, t-shirt, trui, vest, hoodie, broek, shorts, schoenen… (vrij aan te vullen).
- 💞 **Combineren** – swipe per kledingstuk of het bij een ander past. Rechts = past,
  links = past niet, en **overslaan** als je er nog niet uit bent (dat paar komt
  achteraan de rij weer terug). Vergist? Elke beoordeling is **ongedaan te maken**.
- ⇄ **Naast elkaar vergelijken** – zet beide stukken even groot naast elkaar in
  plaats van één grote kaart met een klein duimnageltje ernaast. Die keuze onthoudt
  de app. Eén tik op ⤢ (of op een foto) zet ze schermvullend naast elkaar — daar
  kun je meteen ✕, ⏭ of ♥ kiezen, en wisselen tussen naast en onder elkaar.
- ✨ **Outfits** – bekijk per stuk alle goedgekeurde combinaties, met wie ze goedkeurde.
  Suggesties van het systeem kun je in één tik **opslaan als combinatie**. Op een
  kledingstuk zie je ook wat er juist **niet** bij past, en wie dat vond. Elke foto
  is met ⤢ **groot te bekijken** — een suggestie opent als hele outfit, een
  goedgekeurde combinatie naast het gekozen stuk.
- 🚪 **Eigen kast per gebruiker** – iedereen heeft z'n eigen kledingkast.
- 🤝 **Delen** – nodig iemand uit voor je kast als **bewerker** (mag alles aanpassen)
  of **kijker** (alleen inzage, maar mag wél meestemmen op combinaties). Heeft diegene
  nog geen account? Stuur een **uitnodigingslink** of laat 'm de **QR-code** scannen;
  daarmee registreren ze zichzelf.
- 🔒 **Alleen op uitnodiging** – niemand kan zich zomaar aanmelden; dat zegt het
  inlogscherm er ook bij. Een beheerder deelt een **uitnodiging (link of QR-code)**
  uit voor een nieuw account, of zet **zelf registreren** met één schakelaar open.
- 🔑 **Inloggen via je eigen SSO** – optioneel inloggen met **OpenID Connect**
  (Authentik, Authelia, Keycloak, Zitadel, Entra ID…). Wie in de juiste **groep**
  zit is meteen beheerder, wie er niet in zit een gewone gebruiker — bij elke
  login opnieuw. Een uitnodigingslink werkt ook via SSO. Inloggen met
  gebruikersnaam en wachtwoord blijft er altijd naast staan, zodat een
  onbereikbare inlogdienst je nooit buitensluit.
- 💾 **Back-up & export** – iedereen kan z'n eigen kast downloaden als Excel-bestand
  met de foto's erbij; een beheerder maakt een volledige back-up of een exacte
  momentopname, en kan een export weer terugzetten. Of laat het de app **elke
  nacht zelf doen**, met rotatie — want niemand klikt elke week op een knop.
- 📋 **Logboek** – een beheerder ziet in de app wie wat wijzigde, goedkeurde of afkeurde,
  plus de technische logregels van de server.
- 👥 **Accounts** – jij én je partner een eigen login. Een **beheerder** kan bij
  elke kast, en heeft daarnaast ook gewoon z'n eigen kast.
- 📱 **PWA & offline** – installeerbaar op je telefoon (Toevoegen aan beginscherm).
  Zonder verbinding blijf je ingelogd, zie je je kast en je outfits zoals ze het
  laatst geladen waren, en kun je gewoon doorswipen: je oordelen worden verstuurd
  zodra je weer online bent — ook als je de app tussendoor sluit.
- 🔐 **Dichte voordeur** – wachtwoorden van minimaal 8 tekens, een login die
  afremt na mislukte pogingen, een wachtwoordwijziging die je andere apparaten
  uitlogt (en een knop om dat los te doen), en een server die weigert adressen
  in je eigen netwerk op te halen. Zie [Beveiliging](#beveiliging).
- 🔒 **Foto's achter de login** – een foto-URL is geen achterdeur: elke foto wordt
  geserveerd met dezelfde toegangsregels als het kledingstuk waar hij bij hoort.

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
   (Liever inloggen via je eigen Authentik/Authelia? Zie
   [Inloggen via SSO](#inloggen-via-sso-openid-connect) — dit account blijft
   daarnaast bestaan als noodingang.)
2. Ga naar **Instellingen → Wachtwoord wijzigen** en kies een eigen wachtwoord
   (minimaal 8 tekens; je huidige wachtwoord wordt erbij gevraagd).
3. Maak onder **Instellingen → Accounts** een account voor je partner aan.
4. **Deel je kast:** tik rechtsboven op je eigen kast op **🔗 Delen** (of ga naar
   **Instellingen → Mijn kast delen**), kies die persoon uit de lijst en geef ze
   de rol **bewerker** of **kijker**. Daarna ziet die persoon jouw kast en kan
   meteen meeswipen.

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
| `WARDROBE_LOG_LEVEL` | `INFO` | Hoeveel er gelogd wordt: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `WARDROBE_PUBLIC_URL` | — | Het adres waarop je de app bereikt, bv. `https://kast.jouwdomein.nl`. Alleen nodig voor SSO. |

Voor **beveiliging** — alle standaarden zijn al de veilige keuze, zie
[Beveiliging](#beveiliging):

| Variabele | Standaard | Uitleg |
|---|---|---|
| `WARDROBE_MIN_PASSWORD_LENGTH` | `8` | Kortste wachtwoord dat wordt geaccepteerd als er één wordt *ingesteld*. Bestaande wachtwoorden blijven werken. |
| `WARDROBE_LOGIN_MAX_ATTEMPTS` | `5` | Mislukte pogingen op rij voordat de app met 429 antwoordt. |
| `WARDROBE_LOGIN_LOCKOUT_SECONDS` | `30` | Eerste wachttijd daarna; verdubbelt per verdere poging tot een kwartier. |
| `WARDROBE_CORS_ORIGINS` | — | Adressen die de API cross-origin mogen aanroepen. Leeg = geen, en dat klopt voor vrijwel elke installatie. |
| `WARDROBE_COOKIE_SECURE` | `auto` | `Secure`-vlag op de fotocookie. `auto` = aan op https, uit op http. |
| `WARDROBE_CONTENT_SECURITY_POLICY` | alles van dit adres | De CSP die wordt meegestuurd. Leeg = geen policy. |
| `WARDROBE_HSTS_SECONDS` | `0` (uit) | HSTS op https. Zet dit pas aan als je certificaat staat. |
| `WARDROBE_FETCH_ALLOW_PRIVATE` | `false` | Of de foto-URL- en importfuncties adressen in je eigen netwerk mogen ophalen. |
| `WARDROBE_REPAIR_ON_START` | `false` | Draai de opruimcontrole ook als de database al bij is — zie [Opstarten](#opstarten-migraties-en-healthcheck). |
| `WARDROBE_BACKUP_TIME` | — (uit) | Tijd (`UU:MM`) waarop er elke dag een momentopname wordt gemaakt — zie [Automatische back-ups](#automatische-back-ups). |
| `WARDROBE_BACKUP_KEEP` | `7` | Hoeveel automatische back-ups bewaard blijven. |

Voor **inloggen via SSO** (optioneel, standaard uit):

| Variabele | Standaard | Uitleg |
|---|---|---|
| `WARDROBE_OIDC_ENABLED` | `false` | Zet federated login aan. Blijft uit zolang issuer, client-id of secret ontbreekt. |
| `WARDROBE_OIDC_ISSUER` | — | Basis-URL van je provider; `/.well-known/openid-configuration` wordt er zelf achter gezet. |
| `WARDROBE_OIDC_CLIENT_ID` | — | Client-id van de toepassing die je bij je provider maakt. |
| `WARDROBE_OIDC_CLIENT_SECRET` | — | Bijbehorend secret (confidential client). |
| `WARDROBE_OIDC_SCOPES` | `openid profile email groups` | Welke scopes gevraagd worden. `openid` wordt altijd toegevoegd. |
| `WARDROBE_OIDC_GROUPS_CLAIM` | `groups` | Claim met de groepen. Een punt gaat dieper, bv. `realm_access.roles`. |
| `WARDROBE_OIDC_ADMIN_GROUP` | — | Wie hierin zit is beheerder, wie niet een gewone gebruiker. Leeg = de app beheert rollen zelf. |
| `WARDROBE_OIDC_ALLOWED_GROUPS` | — | Komma-lijst; alleen leden hiervan mogen inloggen. Leeg = iedereen die je provider doorlaat. |
| `WARDROBE_OIDC_AUTO_CREATE` | `false` | Maak een account aan bij de eerste login. Uit = alleen op uitnodiging. |
| `WARDROBE_OIDC_LINK_BY_USERNAME` | `false` | Koppel aan een bestaand account met dezelfde gebruikersnaam. Voor een eenmalige overstap. |
| `WARDROBE_OIDC_BUTTON_LABEL` | `Inloggen met SSO` | De tekst op de knop. |
| `WARDROBE_OIDC_LOGOUT_REDIRECT` | `false` | Bij uitloggen ook afmelden bij de provider zelf. |
| `WARDROBE_LOCAL_LOGIN` | `true` | Of het wachtwoordformulier meteen op het inlogscherm staat. Het blijft altijd bereikbaar — zie [Inloggen via SSO](#inloggen-via-sso-openid-connect). |

Foto's worden bij upload automatisch geroteerd (EXIF), verkleind (max 1280px)
en als JPEG opgeslagen, plus een thumbnail — zodat de kast licht blijft.

---

## Offline

De app is een PWA en moet dus ook iets doen als je telefoon geen bereik heeft.
Wat er dan wél en niet werkt:

| | Zonder verbinding |
| --- | --- |
| Ingelogd blijven | ✅ Je sessie blijft staan; alleen een écht geweigerde sessie (401) logt je uit |
| Kast, Outfits, kledingstuk bekijken | ✅ Uit de cache, inclusief foto's |
| Combineren (swipen) | ✅ De app heeft een stuk of 25 paren vooruit opgehaald |
| Oordeel geven of overslaan | ✅ Wordt bewaard en later verstuurd |
| Ongedaan maken | ❌ Kan pas weer online |
| Kledingstuk toevoegen of wijzigen | ❌ Kan pas weer online |
| Back-up, export, terugzetten | ❌ Kan pas weer online |

Bovenin verschijnt een balk zodra de verbinding weg is, want een geïnstalleerde
app verbergt de offline-melding van de browser — zonder die balk lijkt het net
alsof je alles ziet zoals het nu is, terwijl je partner ondertussen van alles
beoordeeld kan hebben.

Onder water:

* **App zelf** – voorgeladen in de cache, dus de app opent altijd.
* **Foto's** – `cache-first`; een foto-URL bevat een UUID en verandert nooit.
* **API (GET)** – `network-first`: online altijd vers, offline uit de cache.
  Alleen de verzoeken die een scherm tekenen. De cache wordt gewist bij in- én
  uitloggen, zodat de volgende persoon op dat toestel niet jouw kast ziet.
* **Oordelen (POST)** – gaan bij verbindingsverlies in een wachtrij van de
  service worker (`background sync`) en worden later opnieuw verstuurd, ook met
  de app dicht. Zodra de app zelf merkt dat de server er weer is, stuurt hij ze
  bovendien meteen zelf — de API bewaart één oordeel per paar per persoon, dus
  twee keer aankomen verandert niets.
* **Verbinding vaststellen** – niet op `navigator.onLine` alleen (die liegt
  achter een captive portal, en klopt soms even niet vlak na het openen), maar
  door `/api/version` op te vragen, dat expres nooit gecachet wordt.

---

## Back-up, export en terugzetten

Onder **Instellingen → Back-up & export** staat alles wat met exporteren te maken
heeft. Er zijn drie soorten bestanden, allemaal één ZIP:

| Wat | Voor wie | Wat zit erin |
| --- | --- | --- |
| **Exporteer mijn kast** | iedereen, voor de eigen kast | `Kledingkast.xlsx`, de foto's in `photos/`, en `wardrobe.json` |
| **Volledige back-up** | beheerder | hetzelfde, maar voor álle kasten, plus accounts, categorieën, maten en kleurregels |
| **Momentopname** | beheerder | een exacte kopie van `wardrobe.db` en de map `uploads/` |

Die laatste kan ook [elke nacht automatisch](#automatische-back-ups), met rotatie.

### Het exportbestand

`Kledingkast.xlsx` is bedoeld om zelf te openen: elke regel is een kledingstuk
met een kleine foto erbij, en een link naar het volledige fotobestand in de map
`photos`. Er zijn tabbladen voor **Kledingstukken**, **Combinaties** (inclusief
wie welk oordeel gaf) en, in een volledige back-up, **Gebruikers**. Sorteer je de
lijst, dan blijven de foto's staan waar ze staan — dat doet Excel nu eenmaal met
afbeeldingen; de kolom *Fotobestand* blijft wel kloppen.

Daarnaast zit er een `wardrobe.json` in met dezelfde gegevens in
machineleesbare vorm. Dát bestand heeft de app nodig om een kast terug te
zetten, en het verwijst naar kledingstukken via een vast kenmerk (`uid`) in
plaats van via een database-id — daarom kun je dezelfde export twee keer
terugzetten zonder dat je alles dubbel krijgt.

### Terugzetten

Terugzetten kan alleen een **beheerder**, en alleen met een export (niet met een
momentopname). De app leest eerst het bestand en laat zien wat erin zit, daarna
kies je de kast en:

* **Samenvoegen** – voegt toe wat ontbreekt en werkt bij wat er al staat. Er
  wordt niets verwijderd.
* **Vervangen** – leegt de gekozen kast eerst helemaal (inclusief foto's en
  beoordelingen) en zet daarna het bestand terug.

Beide gaan in één transactie: mislukt er iets halverwege, dan is er niets
gewijzigd. Elke export en elke restore komt in het logboek te staan.

### Automatische back-ups

De app heeft al een tijd een knop voor een volledige back-up en een voor een
momentopname. Niemand klikt die elke week. Dat is geen kwestie van discipline —
zo werken knoppen — en het betekende dat de eerlijke omschrijving van de
back-upsituatie was: "er zijn back-upknoppen". Dat is iets anders dan "er zijn
back-ups".

Zet daarom een tijd:

```bash
WARDROBE_BACKUP_TIME=03:30     # elke dag om half vier 's nachts
WARDROBE_BACKUP_KEEP=7         # de laatste zeven blijven staan
```

Dan schrijft de app elke dag een **momentopname** naar `/data/backups` en
verwijdert wat daarbuiten valt. Leeg laten (de standaard) zet het uit.

De tijd is die van de **container**, niet die van je browser. Staat je server op
UTC en wil je Nederlandse tijd, zet dan `TZ=Europe/Amsterdam` in je
`docker-compose.yml`.

#### Waarom een momentopname en geen export

De export is degene die de app via z'n eigen schermen kan terugzetten, dus die
lijkt de logischere keuze. Dat is 'ie niet: een momentopname is een exacte kopie
van de database plús de foto's, en zet dus **alles** terug — accounts,
uitnodigingen, het logboek, de catalogus — waar een export de inhoud van een
kast terugzet. Als een schijf overlijdt is "alles" de enige nuttige hoeveelheid.

Hij is ook goedkoper: de momentopname gebruikt SQLite's eigen backup-API in
plaats van elk kledingstuk via de ORM langs te lopen. Dat is sneller én veilig
terwijl de app verzoeken afhandelt.

De prijs is dat terugzetten een bestandskopie is in plaats van een knop — zie
[Momentopname terugzetten](#momentopname-terugzetten). De volledige export onder
**Instellingen → Back-up & export** blijft staan voor de variant die de app wél
zelf kan terugzetten.

#### Wat je ervan ziet

Onder **Instellingen → Back-up & export** staat wat het schema is en wat het tot
nu toe heeft opgeleverd, met per back-up een downloadknop. Daar zit ook **Nu een
back-up maken**, voor als je niet tot vannacht wilt wachten — en om te
controleren dat het op jouw machine überhaupt werkt voordat je een schema
vertrouwt.

Een schema dat niemand kan zien is namelijk niet te onderscheiden van een schema
dat stilletjes gestopt is. Elke ronde komt ook in het **logboek**:

```
INFO  Back-up gemaakt: auto-20260913-033000.zip (48.2 MB) in 1.4s; 1 oude verwijderd
```

#### Als er een nacht misgaat

Dan schrijft de app een luide regel en wacht tot morgen. De lus gaat nooit
dood — een scheduler die bij de eerste fout opgeeft is erger dan geen
scheduler, want die lijkt te werken.

Een half weggeschreven bestand komt er nooit in te staan: de bytes landen eerst
onder een naam die geen back-upnaam is en krijgen de echte naam pas als ze er
allemaal zijn. Een afgekapte zip onder een normale naam is namelijk erger dan
geen back-up, omdat het er als een back-up uitziet.

#### Wat er niet bij hoort

- **Het staat op dezelfde schijf.** Een momentopname in `/data/backups`
  overleeft een foute restore, een kapotte migratie en een per ongeluk
  verwijderd account — niet het overlijden van de schijf zelf. Haal ze er
  periodiek af (de downloadknop, of `docker cp`, of een rsync van het volume).
- **Ze bevatten de gegevens van iedereen**, wachtwoord-hashes incluis. Bewaar ze
  net zo zorgvuldig als de server zelf.
- **Bestanden die jij er zelf in zet blijven staan.** De rotatie raakt alleen
  wat de app zelf geschreven heeft.

### Momentopname terugzetten

Een momentopname is een exacte kopie en gaat buiten de app om terug:

```bash
docker compose down
# pak het archief uit en zet de bestanden in het volume:
#   wardrobe.db  ->  /data/wardrobe.db
#   uploads/*    ->  /data/uploads/
docker compose up -d
```

Of maak er zelf een van buitenaf, zonder de app. **Zet de container dan eerst
stil**: de database staat in WAL-modus, dus een deel van de laatste wijzigingen
staat in `wardrobe.db-wal` en hoort mee in het archief (zie
[WAL](#wal)). Met de container uit is dat geregeld.

```bash
docker compose down
docker run --rm -v kledingkast-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/kledingkast-backup.tar.gz -C /data .
docker compose up -d
```

Terugzetten: draai hetzelfde met `tar xzf` in `/data`, ook met de container uit.

> Een volledige back-up en een momentopname bevatten de gegevens van iedereen —
> een momentopname zelfs de wachtwoord-hashes. Bewaar ze net zo zorgvuldig als
> de server zelf.

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
npm run lint           # oxlint; draait ook in CI
npm test               # unit-tests (vitest); draait ook in CI
```

### Tests

```bash
cd backend && pytest -q         # 189 tests: API, migraties, SSO, beveiliging
cd frontend && npm test         # 46 tests: offline-wachtrij, verbinding, API-laag
cd frontend && npx playwright test   # de doorloop in een echte browser
```

Drie lagen, elk met een eigen reden:

- **pytest** dekt elke API-route, de migraties en de toegangsregels.
- **vitest** dekt de frontend-logica waar een fout pas opvalt als je in de trein
  zit: de wachtrij met oordelen, het vaststellen of er verbinding is, en het
  verschil tussen "de server zegt nee" en "de server zegt niets".
- **playwright** doet één doorloop in een echte browser — inloggen, een
  kledingstuk toevoegen, het terugvinden — op desktop- én telefoonformaat. Dat
  is het enige wat kan vertellen of de app überhaupt tekent en of de knoppen aan
  de juiste routes hangen; precies de soort kapotheid waar de andere twee lagen
  langs varen. Het bouwt de frontend en start de backend zelf
  (`frontend/e2e/serve.sh`), tegen een wegwerpdatabase.

De eerste keer heeft Playwright een browser nodig:

```bash
cd frontend && npx playwright install chromium
```

Staat er al een Chromium op je machine, dan kun je die gebruiken met
`PLAYWRIGHT_CHROMIUM_PATH=/pad/naar/chrome npx playwright test`.

Standaard-admin bij eerste start: `admin` / `changeme`.

---

## Projectstructuur

```
backend/            FastAPI-app (Python)
  app/
    main.py         de app zelf: middleware, healthcheck, serveert de gebouwde frontend
    models.py       User, Wardrobe, WardrobeMember, Item, Match (SQLAlchemy)
    access.py       kast-toegang & rollen (eigenaar/beheerder/bewerker/kijker)
    routers/        auth, oidc, users, wardrobes, items, matches, catalog,
                    color_rules, imports, invitations, admin_log
    app_settings.py instellingen die een beheerder in de app omzet (zelf registreren)
    migrations.py   genummerde schemastappen (één keer) + seeds (elke start)
    scheduled_backup.py  dagelijkse momentopname in <data>/backups, met rotatie
    oidc.py         federated login: discovery, PKCE, tokencontrole, groep → beheerder
    throttle.py     mislukte inlogpogingen afremmen
    fetching.py     URL's die een gebruiker typt ophalen zónder je eigen netwerk te raken
    deps.py         wie doet dit verzoek: één plek die bepaalt wat een token betekent
    images.py       foto-verwerking (Pillow)
    matching.py     categorie-groepen voor slimme combinatie-suggesties
    audit.py        auditlog: wie deed wat (naar database én logregel)
    logging_setup.py logging naar stdout (docker logs) + ringbuffer voor in de app
frontend/           React + Vite (TypeScript)
  e2e/              één doorloop in een echte browser (Playwright)
  src/*.test.ts     unit-tests voor de offline-logica en de API-laag (vitest)
  src/pages/        Login, Invite, Wardrobe, AddItem, ItemDetail, Combine, Outfits,
                    Settings, AdminLog
  src/wardrobe.tsx  kast-context (welke kast is actief + je rol)
  src/components/   SwipeCard, ItemForm, BottomNav, WardrobeSwitcher, SuggestionList,
                    JudgedPairList, PartnerGrid, InvitationLinks, QrCode
  src/qr.ts         QR-codes voor uitnodigingslinks (geen externe bibliotheek)
Dockerfile          multi-stage build (frontend → python runtime)
docker-compose.yml  container + datavolume
deploy/             nginx-voorbeeldconfig
```

---

## Kasten & delen

Elke gebruiker heeft z'n **eigen kast**. Kledingstukken en je oordelen over
combinaties horen bij één kast — ze zijn niet globaal gedeeld.

Een kast deel je vanaf je eigen kast via **🔗 Delen** (of **Instellingen →
Mijn kast delen**). Kies een bestaande gebruiker uit de lijst en een rol:

- **Bewerker** – mag kledingstukken toevoegen, bewerken en verwijderen, én
  meestemmen op combinaties.
- **Kijker** – mag alleen kijken, maar wél meestemmen op combinaties.

Bovenin de kast-, combineer- en outfits-schermen wissel je met de kast-kiezer
tussen je eigen kast en kasten die met je gedeeld zijn.

Een **beheerder** kan bij élke kast (ook zonder uitnodiging) en heeft daarnaast
gewoon een eigen kast als elke andere gebruiker.

### Een account verwijderen

Verwijderen onder **Instellingen → Accounts** haalt het hele account weg, niet
alleen de inlog: de eigen kast van die persoon verdwijnt mét de kledingstukken
en foto's erin, en met al hun oordelen over combinaties. De gebruikersnaam is
daarna meteen weer vrij.

Wat blijft staan:

- **Kledingstukken die ze aan een gedeelde kast toevoegden.** Die horen bij die
  andere kast, dus ze blijven; het beheer ervan gaat naar de beheerder die het
  account verwijderde.
- **Het logboek.** Auditregels houden de naam die erin stond, zodat "wie heeft
  dit gedaan?" ook achteraf te beantwoorden is.

Dit kan niet ongedaan gemaakt worden — maak eerst een [back-up](#back-up) als
je twijfelt.

**Let op:** het verwijderen haalt een account weg; het laat accounts die je
*niet* verwijderd hebt gewoon staan. Zie je iemand nog in de lijst staan, dan
bestaat dat account nog.

**Eén keer** — bij de eerste start na het bijwerken — controleert de app of er
resten liggen van accounts die in een oudere versie half verwijderd zijn, en
ruimt die op. Daarna niet meer, want die controle leest de hele kast in het
geheugen en er komt geen nieuwe wrakstukken meer bij; zie
[Opstarten](#opstarten-migraties-en-healthcheck) als je 'm alsnog wilt draaien
(`WARDROBE_REPAIR_ON_START=true`). In beide gevallen zegt het logboek wat er
gebeurd is:

```
WARNING  Resten van eerder verwijderde accounts opgeruimd: 1 kasten, 2 kledingstukken
INFO     Databasecontrole: geen resten van verwijderde accounts gevonden (3 account(s), 3 kast(en))
```

Wil je zelf in de database kijken wie er nog staat en of er iets is blijven
liggen:

```bash
docker compose exec -T kledingkast python - < scripts/check_db.py
```

(De `-T` is nodig: zonder die vlag opent `docker compose exec` een terminal en
weigert 'ie het doorgegeven script met *"the input device is not a TTY"*.)

### Iemand uitnodigen die nog geen account heeft

Registratie staat standaard dicht: niemand kan zichzelf zomaar aanmelden, en het
inlogscherm zegt dat er met zoveel woorden bij. Binnenkomen gaat dus op
uitnodiging, en die bestaat in twee smaken.

**Een uitnodiging voor je kast** maak je vanaf **Instellingen → Mijn kast delen →
Uitnodigen met een link of QR-code**. Zet erbij voor wie 'ie is, kies de rol en
hoe lang de link geldig blijft. Stuur 'm via WhatsApp/mail, of klik op
**QR-code** en laat 'm scannen met de camera van de telefoon.

Wie de link opent ziet van wie de kast is en welke rol 'ie krijgt, en kiest dan:

- **al een account** → inloggen, de uitnodiging wordt meteen geaccepteerd;
- **nog geen account** → ter plekke registreren; diegene komt direct in je kast
  terecht en krijgt daarnaast een eigen kast.

**Een uitnodiging voor alleen een account** maakt een beheerder onder
**Instellingen → Toegang & registratie → Iemand nieuw uitnodigen**. Daarmee deelt
er niets van jouw kast: precies één iemand maakt een account aan — naam,
gebruikersnaam en wachtwoord naar eigen keuze — en krijgt een eigen lege kast.
Ook hier hoort een QR-code bij, handig als diegene naast je staat.

Een link werkt in beide gevallen **één keer** en verloopt daarna vanzelf. Zolang
'ie nog niet gebruikt is kun je 'm altijd **intrekken**.

Heb je [SSO](#inloggen-via-sso-openid-connect) aanstaan, dan staat er op de
uitnodigingspagina ook een SSO-knop: dan hoeft de uitgenodigde geen wachtwoord
te kiezen, en verzilvert één keer inloggen bij je provider meteen de uitnodiging.

### Zelf registreren open- of dichtzetten

Wil je geen uitnodigingen meer uitdelen — bijvoorbeeld binnen een huishouden of
vereniging waar iedereen er gewoon bij mag — dan zet een beheerder onder
**Instellingen → Toegang & registratie** de schakelaar **Zelf registreren
toestaan** aan. Het inlogscherm krijgt er dan een knop *Account aanmaken* bij, en
iedereen die het adres kent kan een account maken. Uit staat 'ie weer met
dezelfde schakelaar; de wissel komt in het logboek te staan.

> Zet 'm alleen open als de app niet zomaar vanaf het internet te bereiken is,
> of als je het niet erg vindt wie er binnenkomt.

---

## Opstarten, migraties en healthcheck

### Migraties lopen één keer

De database houdt in een tabelletje `schema_version` bij hoe ver 'ie is. Bij het
opstarten worden alleen de stappen gedaan die nog niet gedaan zijn; staat 'ie
al op de nieuwste versie, dan zegt het logboek dat en gebeurt er niets:

```
INFO  Database is bij (schemaversie 10); geen migraties nodig.
```

Bij de eerste start ná deze versie worden alle stappen één keer doorlopen —
elke stap kijkt eerst zelf of 'ie nodig is, dus op een bestaande database doen
ze niets en verandert er niets aan je gegevens:

```
INFO  Geen schemaversie gevonden — alle 10 stappen worden één keer doorlopen.
INFO  Migratie 1/10: tabellen en kolommen
INFO  Migratie 2/10: kolommen voor SSO-login
...
INFO  Migraties afgerond; database staat op schemaversie 10
```

Elke stap wordt apart afgevinkt, dus als er halverwege iets misgaat blijven de
stappen die wél lukten staan in plaats van dat ze bij de volgende start opnieuw
langskomen.

Waarom dit beter is dan "altijd alles doen": bij de stappen zit een
**opruimcontrole** die resten opspoort van accounts die in een oude versie half
verwijderd zijn. Die leest daarvoor alle kledingstukken en alle beoordelingen in
het geheugen. Bij tweehonderd kledingstukken kost dat niets; bij een paar
duizend, elke keer dat de container herstart, wel.

Wil je die controle toch nog eens draaien — bijvoorbeeld nadat je een back-up met
de hand hebt teruggezet — dan zet je `WARDROBE_REPAIR_ON_START=true`. Hij zegt in
het logboek wat 'ie vond, of dat er niets te vinden was. Zet 'm daarna weer uit.

> **Seeds lopen wél elke start.** De categorieënlijst, de matenlijst en de
> kleurregels worden elke keer bijgevuld, want dat is hoe een maat die in een
> nieuwe versie is toegevoegd terechtkomt in een kast die de lijst al had. Dat
> kost twee telvragen en raakt niets wat je zelf hebt aangepast.

### De healthcheck

`/api/health` kijkt of de app z'n werk kan doen: is de database te lezen, en is
de fotomap te beschrijven. Gaat er iets niet, dan antwoordt 'ie **503** met wat
er stuk is:

```json
{"status": "degraded", "checks": {"database": "ok", "uploads": "niet beschrijfbaar"}, "version": "0.11.0"}
```

`docker-compose.yml` gebruikt dat nu als `healthcheck`. Dat is wat
`restart: unless-stopped` nodig heeft om te kunnen ingrijpen: zonder healthcheck
herstart Docker alleen een container die *stopt*, niet één die nog draait maar
niet meer bij z'n eigen database kan.

```bash
docker compose ps            # toont "healthy" of "unhealthy"
curl -s localhost:8000/api/health | jq
```

De eerste minuut na het starten telt niet mee (`start_period`), want de eerste
start doet de migraties en dat mag even duren.

### WAL

De database staat in **WAL-modus**, zodat lezen niet hoeft te wachten op
schrijven. Dat is hier geen theoretische winst: een volledige back-up of een
export loopt door álle kledingstukken en foto's, en zonder WAL staat iedereen die
ondertussen wil swipen stil tot dat klaar is. Je ziet er twee extra bestanden van
naast `wardrobe.db` (`-wal` en `-shm`); die horen erbij.

> Maak je een **momentopname** met `tar` buiten de app om, zet de container dan
> eerst stil (`docker compose down`). Met WAL staat een deel van de laatste
> wijzigingen nog in `wardrobe.db-wal`, en die moet er dus mee in het archief.
> De back-up- en exportfuncties ín de app hebben dit probleem niet.

---

## Beveiliging

Niets hiervan hoef je in te stellen: de standaarden zijn al de veilige keuze.
Dit staat er zodat je weet wat de app doet, en wat je kúnt bijstellen.

### Wachtwoorden

- **Minimaal 8 tekens** bij het instellen van een wachtwoord
  (`WARDROBE_MIN_PASSWORD_LENGTH`). Dit geldt alleen bij het *instellen*:
  bestaande wachtwoorden blijven werken, dus er wordt niemand buitengesloten —
  je komt de regel pas tegen als je 'm wijzigt.
- **Je huidige wachtwoord is nodig** om een nieuw in te stellen. Zonder die
  vraag kon iemand met een geleende, ontgrendelde telefoon het wachtwoord
  omzetten en het account houden; nu is zo'n moment tijdelijk in plaats van
  definitief. Een account dat alleen via SSO inlogt heeft nog geen wachtwoord
  en stelt er dus een eerste in — daar is niets te bewijzen, en het logboek
  schrijft het als zodanig op.
- **Een wachtwoordwijziging logt alle andere apparaten uit.** Dat is meestal
  precies waarom je 'm wijzigt. Het toestel waarop je het doet blijft ingelogd.
- **Overal uitloggen** kan ook los, onder **Instellingen → Wachtwoord
  wijzigen**: handig als je telefoon kwijt is en je je wachtwoord niet wilt
  veranderen.

### Wat staat er eigenlijk aan?

Bij elke start schrijft de app **alle** instellingen naar het logboek, met de
waarde die 'ie echt gebruikt en waar die vandaan komt. "Leest die .env nou wel?"
is daarmee geen gokwerk meer:

```
Actieve instellingen (31; 4 afwijkend van de standaard). Herkomst: 'omgeving' =
uit je .env of docker-compose, '.env-bestand' = uit een .env naast de app,
'standaard' = de ingebouwde waarde.
  -- Opslag en basis --
  * WARDROBE_DATA_DIR               = /data                   [omgeving]
  * WARDROBE_SECRET_KEY             = (ingesteld, 64 tekens)  [omgeving]
    WARDROBE_ADMIN_USERNAME         = admin                   [standaard]
  -- Beveiliging --
    WARDROBE_LOGIN_MAX_ATTEMPTS     = 5                       [standaard]
  * WARDROBE_MIN_PASSWORD_LENGTH    = 12                      [omgeving]
  -- Inloggen via SSO (OpenID Connect) --
  * WARDROBE_OIDC_ENABLED           = true                    [omgeving]
  * WARDROBE_OIDC_CLIENT_SECRET     = (ingesteld, 40 tekens)  [omgeving]
    WARDROBE_OIDC_GROUPS_CLAIM      = groups                  [standaard]
  (database: /data/wardrobe.db)
  (foto's:   /data/uploads)
```

Een `*` betekent: deze wijkt af van de ingebouwde standaard. Dus één blik zegt
je wat je zelf hebt aangezet.

Te zien met `docker compose logs kledingkast`, en in de app onder
**Instellingen → Logboek**.

> **Wachtwoorden en sleutels komen er niet in.** Van een geheim staat er alleen
> óf 'ie gezet is en hoe lang 'ie is — genoeg om "hij is wel aangekomen" van
> "hij is leeg" te onderscheiden, zonder je sleutel in een logboek te zetten
> dat in de app te lezen is.

Dat `[omgeving]` / `[standaard]`-onderscheid werkt alleen doordat
`docker-compose.yml` de variabelen **op naam** doorgeeft (`- WARDROBE_LOG_LEVEL`)
in plaats van met een eigen fallback (`WARDROBE_LOG_LEVEL: "${WARDROBE_LOG_LEVEL:-INFO}"`).
Die tweede vorm zet de variabele namelijk *altijd*, ook als je `.env` zwijgt, en
dan kan de container het verschil niet meer zien. Zo staan de standaarden ook op
één plek — in `app/config.py` — in plaats van ook nog eens in het compose-bestand.

### Inlogpogingen

Na **5 mislukte pogingen** op rij antwoordt de app met een 429. De eerste
wachttijd is **30 seconden** en verdubbelt bij elke volgende poging, tot
maximaal een kwartier. Een goed wachtwoord wist de teller meteen, dus wie zich
twee keer vertypt merkt er niets van.

Geteld wordt op **gebruikersnaam** én op **afzender-adres**, en een blokkade op
een van de twee is genoeg. Dat eerste is wat een account echt beschermt; het
tweede moet voorkomen dat één machine een lijst met accounts afwerkt. Achter een
reverse-proxy komt elk verzoek van `127.0.0.1`, dus daar wordt
`X-Forwarded-For` gebruikt — te vervalsen, en dat maakt niet uit: wie dat doet
verdeelt alleen z'n eigen budget over verzonnen adressen, terwijl de teller op
de gebruikersnaam gewoon doortikt.

De tellers staan in het geheugen van het proces. Een herstart wist ze, en dat is
hier prima: de app draait met opzet één worker, en een herstart is geen
gereedschap dat een aanvaller heeft.

Blokkades komen in het **logboek** te staan, naast de mislukte pogingen zelf.

### Sessies

Een login-token is 30 dagen geldig en draagt het **tokenversie-nummer** van het
account. Gaat dat nummer omhoog — bij een wachtwoordwijziging of bij "overal
uitloggen" — dan zijn alle tokens van ervóór op dat moment dood. Zonder dat
bleef een sessie die je oude wachtwoord kende nog een maand doorlopen.

Hetzelfde geldt voor foto's: die worden met een cookie geautoriseerd, en die
gaat door precies dezelfde controle. Een ingetrokken token stopt met foto's
serveren op hetzelfde moment dat het stopt met gegevens serveren.

Tokens van vóór deze versie hebben nog geen versienummer en gelden als versie 1
— dus de update zelf logt niemand uit. De eerste wachtwoordwijziging daarna
ruimt ze op.

### Headers en cookies

De app stuurt zelf de headers mee die de browser nodig heeft om het werk te
doen:

| Header | Waarde |
| --- | --- |
| `Content-Security-Policy` | alles van dit ene adres (`WARDROBE_CONTENT_SECURITY_POLICY`) |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-Frame-Options` | `DENY` |
| `Strict-Transport-Security` | alleen op https én als je `WARDROBE_HSTS_SECONDS` zet |

De CSP is de belangrijkste: het login-token leeft in `localStorage`, waar een
script dat in de pagina terechtkomt het zou kunnen lezen. Een policy die niets
anders laat draaien dan de eigen scripts van deze app is daar de sterkste
bescherming tegen, en kost hier niets omdat de app niets van buiten laadt.

`WARDROBE_HSTS_SECONDS` staat op 0 omdat HSTS een belofte is die de browser een
jaar lang onthoudt: aanzetten voordat je certificaat staat sluit mensen buiten
van hun eigen kast. Staat certbot, zet 'm dan op `31536000`. Doet je nginx het
al, laat 'm dan op 0.

De **fotocookie** krijgt de `Secure`-vlag op https en niet op gewone http
(`WARDROBE_COOKIE_SECURE=auto`). Beide antwoorden zijn namelijk fout als vaste
waarde: op http wordt een secure cookie simpelweg nooit verstuurd en breekt elke
foto, en op https is 'm weglaten het weggeven van je token.

**CORS** staat standaard helemaal uit. De app serveert z'n eigen frontend vanaf
hetzelfde adres, en de Vite-dev-server proxyt `/api` en `/uploads` naar de
backend — in geen van beide gevallen komt er ooit een cross-origin-verzoek. Host
je de frontend echt elders, dan noem je dat adres in `WARDROBE_CORS_ORIGINS`.

### URL's die de server voor je ophaalt

Twee functies geven de server een adres en vragen 'm het op te halen: een
kledingstuk toevoegen via een **foto-URL**, en de gegevens van een **webshop**
inlezen. Dat is handig, en zonder zorg ook een manier om de server op deuren te
laten kloppen die alleen hij kan bereiken — het beheerpaneel van een andere
container, de webinterface van je router. De app staat op je eigen server,
meestal op hetzelfde netwerk als de rest van wat die server draait, dus "alleen
de server komt daar" is juist het probleem: *elke* ingelogde gebruiker, ook een
kijker op een gedeelde kast, zou dat bereik lenen.

Daarom gaat zo'n verzoek langs een controle:

- alleen `http` en `https`;
- de servernaam wordt eerst opgezocht, en geweigerd als **één van** de adressen
  privé, loopback, link-local of anderszins geen publiek internetadres is
  (dus ook `127.0.0.1`, `10.x`, `192.168.x`, `169.254.169.254` en `::1`);
- omleidingen worden met de hand gevolgd, maximaal vier, met diezelfde controle
  bij **elke stap** — een omleiding naar `127.0.0.1` is de voor de hand liggende
  manier om een controle te omzeilen die alleen kijkt naar wat er getypt werd;
- de download heeft een maximum, dus een adres dat eindeloos blijft sturen kan
  de schijf niet volzetten.

Wat hiermee *niet* dicht is: het gaatje tussen het opzoeken van een naam en het
verbinden ermee. Een DNS-server die de tweede keer een ander adres teruggeeft
kan er nog langs. Dat echt dichtzetten betekent de verbinding vastpinnen op het
gecontroleerde adres, wat TLS-verificatie breekt tenzij je 'm zorgvuldig weer in
elkaar zet — voor een thuisserver niet die complexiteit waard. Het gaatje staat
hier dus opgeschreven in plaats van weggemoffeld.

Wil je juist wél je eigen netwerk kunnen bereiken (een NAS met foto's, een
interne catalogus), zet dan `WARDROBE_FETCH_ALLOW_PRIVATE=true`. Doe dat alleen
als je iedereen met een account in deze Kledingkast dat toevertrouwt.

---

## Inloggen via SSO (OpenID Connect)

Naast de eigen gebruikersnaam en wachtwoord kan de app inloggen uitbesteden aan
je eigen identity provider — **Authentik**, **Authelia**, **Keycloak**,
**Zitadel**, **Pocket ID**, **Microsoft Entra ID**, **Google**: alles wat
OpenID Connect spreekt. Eén knop op het inlogscherm, en wie in de juiste
**groep** zit is meteen beheerder.

Alleen OpenID Connect, geen SAML. Dat is een bewuste keuze: OIDC kost hier geen
enkele extra systeembibliotheek, en Authentik (of Keycloak) kan desnoods zelf
als brug naar een SAML-provider dienen.

> **Inloggen met gebruikersnaam en wachtwoord blijft altijd werken.** Er is geen
> schakelaar die dat uitzet. Als je provider onbereikbaar is, stuk staat of
> verkeerd ingesteld is, moet je nog steeds in je eigen kast kunnen — dus blijft
> die deur open. `WARDROBE_LOCAL_LOGIN=false` klapt het formulier alleen dicht
> op het inlogscherm; één klik opent het weer.

### Hoe het werkt

1. Je klikt op de knop; de app stuurt je naar je provider (authorization code
   met PKCE).
2. Je meldt je daar aan — met MFA, passkey of wat je daar ook hebt ingesteld.
3. De app controleert de signature van het identiteitsbewijs tegen de sleutels
   die je provider publiceert, plus de issuer, de audience en een eenmalige
   nonce.
4. Je komt binnen als je eigen account, met je eigen kast, precies zoals bij een
   wachtwoord-login. Ook offline-swipen en de PWA merken er niets van.

Een paar dingen die goed zijn om te weten:

- **Een account wordt herkend op de `sub`-claim**, niet op je e-mailadres of
  gebruikersnaam. Die twee kun je bij je provider wijzigen; `sub` niet. Zou de
  app op e-mail matchen, dan kon iemand die bij de provider van naam verandert
  in de kast van een ander belanden.
- **Je weergavenaam volgt je provider** bij elke login. Je *gebruikersnaam*
  niet: daarmee staat het logboek volgeschreven, en die laten we dus staan.
- **Een SSO-account heeft geen wachtwoord.** Er is er geen om te raden. Wil je
  er toch een lokaal wachtwoord bij (handig voor een beheerder die er altijd in
  moet kunnen), dan stel je dat in onder **Instellingen → Wachtwoord wijzigen**.

### Authentik

**1. Maak een provider.** *Applications → Providers → Create →
OAuth2/OpenID Provider*:

| Veld | Waarde |
| --- | --- |
| Name | `Kledingkast` |
| Authorization flow | je gebruikelijke (bv. *implicit consent*) |
| Client type | **Confidential** |
| Redirect URI | `https://kast.jouwdomein.nl/api/auth/oidc/callback` (exact, strict match) |
| Signing Key | je certificaat (bv. de standaard self-signed) |

Bewaar de **Client ID** en het **Client Secret** die Authentik laat zien.

**2. Maak een application** (*Applications → Applications → Create*), geef 'm
een slug zoals `kledingkast` en hang de provider eraan. De issuer-URL die je
nodig hebt is wat Authentik onder de provider toont als *OpenID Configuration
Issuer*, meestal:

```
https://auth.jouwdomein.nl/application/o/kledingkast/
```

**3. Zorg dat de groepen meekomen.** In recente versies van Authentik zit
`groups` al in de standaard-scopemapping van `profile`, en staat *Include claims
in id_token* aan — dan hoef je niks te doen. Controleer het even; werkt het
niet, maak er dan zelf één: *Customization → Property mappings → Create →
Scope mapping*:

| Veld | Waarde |
| --- | --- |
| Name | `Kledingkast groups` |
| Scope name | `groups` |
| Expression | `return {"groups": [g.name for g in request.user.ak_groups.all()]}` |

Voeg die mapping daarna toe aan de **Scopes** van je provider (bij de
OAuth2-provider onder *Advanced protocol settings → Scopes*).

**4. Maak de groep** waar je beheerders in komen, bv. `kledingkast-admins`
(*Directory → Groups*), en zet de juiste mensen erin.

**5. Zet het in je `.env`:**

```bash
WARDROBE_PUBLIC_URL=https://kast.jouwdomein.nl
WARDROBE_OIDC_ENABLED=true
WARDROBE_OIDC_ISSUER=https://auth.jouwdomein.nl/application/o/kledingkast/
WARDROBE_OIDC_CLIENT_ID=...
WARDROBE_OIDC_CLIENT_SECRET=...
WARDROBE_OIDC_SCOPES=openid profile email groups
WARDROBE_OIDC_GROUPS_CLAIM=groups
WARDROBE_OIDC_ADMIN_GROUP=kledingkast-admins
WARDROBE_OIDC_BUTTON_LABEL=Inloggen met Authentik
```

Dan `docker compose up -d`. Het logboek van de container zegt bij het opstarten
of SSO aan staat en welke groep beheerder maakt.

### Authelia

Authelia zet groepen standaard in de `groups`-claim, maar je moet de scope wel
aan de client toewijzen. In je `configuration.yml`:

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: kledingkast
        client_name: Kledingkast
        # Genereer met: authelia crypto hash generate pbkdf2 --password '<secret>'
        client_secret: '$pbkdf2-sha512$...'
        public: false
        authorization_policy: two_factor
        require_pkce: true
        pkce_challenge_method: S256
        redirect_uris:
          - https://kast.jouwdomein.nl/api/auth/oidc/callback
        scopes: [openid, profile, email, groups]
        userinfo_signed_response_alg: none
```

```bash
WARDROBE_OIDC_ISSUER=https://auth.jouwdomein.nl
WARDROBE_OIDC_CLIENT_ID=kledingkast
WARDROBE_OIDC_CLIENT_SECRET=<het secret in platte tekst>
WARDROBE_OIDC_GROUPS_CLAIM=groups
WARDROBE_OIDC_ADMIN_GROUP=kledingkast-admins
WARDROBE_OIDC_BUTTON_LABEL=Inloggen met Authelia
```

De groepen komen uit je gebruikersbestand (`users_database.yml`) of uit je LDAP.

### Keycloak

Maak een client (*Clients → Create client*), **Client authentication: On**,
*Valid redirect URIs* op `https://kast.jouwdomein.nl/api/auth/oidc/callback`.
Het secret staat onder *Credentials*.

Keycloak zet **realm roles** in `realm_access.roles` in plaats van in een
`groups`-claim — daar is de punt-notatie voor:

```bash
WARDROBE_OIDC_ISSUER=https://auth.jouwdomein.nl/realms/jouwrealm
WARDROBE_OIDC_SCOPES=openid profile email
WARDROBE_OIDC_GROUPS_CLAIM=realm_access.roles
WARDROBE_OIDC_ADMIN_GROUP=kledingkast-admin
```

Wil je liever echte *groups* gebruiken, voeg dan in de client een
**Group Membership**-mapper toe met token claim name `groups`, zet *Full group
path* uit, en houd `WARDROBE_OIDC_GROUPS_CLAIM=groups`.

### Zitadel, Pocket ID en andere zelfgehoste providers

Dezelfde drie dingen: een confidential client, de redirect-URI hierboven, en een
claim met groepsnamen.

- **Zitadel** – maak een *Web*-applicatie met *Code*-flow en PKCE. Rollen komen
  mee als je in de applicatie *Assert Roles on Authentication* aanzet; de claim
  heet dan `urn:zitadel:iam:org:project:roles`. Zet die naam in
  `WARDROBE_OIDC_GROUPS_CLAIM`. Die claim is een object en geen lijst — werkt
  dat niet, gebruik dan een *Action* om er een platte lijst van te maken.
- **Pocket ID** – maak een OIDC-client, vink de groepen-scope aan en zet
  `WARDROBE_OIDC_SCOPES=openid profile email groups`.
- **Komt je claim niet aan?** Zet `WARDROBE_LOG_LEVEL=DEBUG` en kijk in het
  logboek: de app zegt het expliciet als de groepen-claim er niet in zat.

### Microsoft Entra ID en Google

Werkt, met twee aantekeningen.

- **Entra ID** – registreer een app, redirect-URI van het type *Web* op
  `https://kast.jouwdomein.nl/api/auth/oidc/callback`. Issuer:
  `https://login.microsoftonline.com/<tenant-id>/v2.0`. Groepen komen standaard
  **niet** mee: zet in het app-manifest *groupMembershipClaims* op
  `SecurityGroup`, en let op dat de claim dan groeps-**GUID's** bevat, geen
  namen — vul dus de GUID in bij `WARDROBE_OIDC_ADMIN_GROUP`. Netter is een
  app-rol met een *Optional claim* op naam.
- **Google** – levert geen groepen in het ID token (Workspace-groepen vereisen
  de Admin SDK). Gebruik Google dus alleen om te authenticeren, laat
  `WARDROBE_OIDC_ADMIN_GROUP` leeg en beheer beheerders in de app.

### Wie er binnen mag

Ook met SSO blijft de app **op uitnodiging**. Iemand die zich bij je provider
netjes aanmeldt maar hier nog geen account heeft, komt er standaard *niet* in —
dat is het punt van een gesloten voordeur. Er zijn drie manieren om mensen toe
te laten:

| Manier | Hoe |
| --- | --- |
| **Uitnodigingslink** (aanbevolen) | Deel een link of QR-code zoals altijd. Wie 'm opent, ziet naast "account aanmaken" ook de SSO-knop. Eén keer inloggen bij je provider maakt het account én verzilvert de uitnodiging — inclusief de rol (bewerker/kijker) op je kast. |
| **Iedereen binnenlaten** | `WARDROBE_OIDC_AUTO_CREATE=true`. Wie je provider doorlaat, krijgt meteen een account en een eigen kast. Combineer dit met `WARDROBE_OIDC_ALLOWED_GROUPS` om het tot een groep te beperken. |
| **Bestaande accounts overzetten** | `WARDROBE_OIDC_LINK_BY_USERNAME=true` koppelt een SSO-login aan een bestaand account met dezelfde gebruikersnaam. Bedoeld om eenmalig over te stappen; zet 'm daarna weer uit, want hij vertrouwt je provider op de gebruikersnaam. |

### Beheerders via een groepsclaim

Zet `WARDROBE_OIDC_ADMIN_GROUP` op de naam van je groep, en dan geldt bij
**elke** SSO-login:

- zit je in die groep → je bent beheerder;
- zit je er niet in → je bent een gewone gebruiker.

Dus iemand de beheerdersrol afnemen doe je door 'm uit de groep te halen; bij de
volgende login is het geregeld. De naam wordt vergeleken zonder op
hoofdletters te letten, zodat `Kledingkast-Admins` en `kledingkast-admins`
hetzelfde betekenen. Elke wijziging komt in het logboek te staan.

Omdat de provider deze rol bezit, staat er voor zulke accounts geen knop
*"Maak beheerder"* meer onder **Instellingen → Accounts** — die zou bij de
volgende login toch weer overschreven worden. Je ziet er in plaats daarvan een
**SSO**-label.

Drie grenzen, zodat dit je nooit buitensluit:

- **Lokale accounts blijft dit ongemoeid.** De beheerder uit je `.env` houdt
  z'n rol, wat je provider ook zegt. Daarom blijft die het vangnet.
- **De laatste beheerder wordt nooit gedegradeerd.** Typ je de groepsnaam
  verkeerd, dan kost dat iemand een rol — niet iedereen het instellingenscherm.
  Het logboek zegt dan dat de rol behouden is.
- **Ontbreekt de claim helemaal, dan verandert er niets.** "Niet in de groep" en
  "de provider stuurt geen groepen mee" zijn twee heel verschillende dingen, en
  de app houdt ze apart: bij het tweede blijft de rol staan en komt er een
  waarschuwing in het logboek (`SSO-login zonder groepen-claim`). Dat is
  veruit de meest gemaakte fout bij het instellen.

Laat je `WARDROBE_OIDC_ADMIN_GROUP` leeg, dan komt de app niet aan de rollen en
beheer je ze gewoon in de app.

### Als het niet werkt

Bijna alles is terug te vinden onder **Instellingen → Logboek** (of in
`docker compose logs -f kledingkast`).

| Wat je ziet | Wat er meestal aan de hand is |
| --- | --- |
| *"De inlogdienst is niet bereikbaar"* | De container kan de issuer-URL niet ophalen. Check DNS in de container, en of je provider intern op een ander adres zit. Gebruikt je provider een self-signed certificaat, mount dan je CA en zet `SSL_CERT_FILE=/pad/naar/ca.crt`. |
| *"De inlogdienst weigerde deze aanmelding"* | Client-id of client-secret klopt niet. |
| *"Het identiteitsbewijs ... is niet geldig"* | De issuer-URL of de client-id wijkt af van wat de provider in het token zet. Neem de issuer letterlijk over uit `/.well-known/openid-configuration`. |
| *"De sleutels van de inlogdienst zijn niet op te halen (foutcode 403)"* | De configuratie van je provider wordt wél geladen, maar het `jwks_uri` eruit niet. Dat zit dus niet in de issuer of de client-id, maar tussen de app en je provider: een reverse-proxy, Cloudflare of WAF die dit ene verzoek tegenhoudt. Sta `Kledingkast/OIDC` toe als user-agent, of zet het pad `/application/o/<slug>/jwks/` vrij. Controleer het van binnenuit met `docker compose exec kledingkast python -c "import httpx;print(httpx.get('<jwks_uri>', headers={'User-Agent':'Kledingkast/OIDC'}).status_code)"`. |
| *"De inlogdienst publiceert geen ondertekeningssleutels"* of *"ondertekent met HS256"* | Bij de toepassing van je provider staat geen **Signing Key**. Authentik valt dan terug op HS256 met het client-secret, en dat accepteert deze app niet. Kies in de provider een certificaat bij *Signing Key*. |
| `redirect_uri` mismatch bij je provider | Moet exact `<WARDROBE_PUBLIC_URL>/api/auth/oidc/callback` zijn, inclusief `https` en zonder slash erachter. Zet `WARDROBE_PUBLIC_URL` altijd als je achter een reverse proxy zit. |
| *"je hebt nog geen account in deze Kledingkast"* | Inloggen lukte, maar de voordeur staat dicht. Stuur een uitnodigingslink, of zet `WARDROBE_OIDC_AUTO_CREATE=true`. |
| `SSO-login zonder groepen-claim` | De groepen komen niet mee. Voeg de scope/mapping bij je provider toe (zie hierboven). |
| Iemand is onbedoeld géén beheerder | Wel een claim, maar de naam matcht niet. Check de exacte groepsnaam. |
| De knop is er niet | `WARDROBE_OIDC_ENABLED` staat uit, óf issuer/client-id/secret is niet alle drie gevuld — dan blijft SSO met opzet uit. Het opstartlogboek zegt welke van de twee. |

---

## Hoe "past bij elkaar" werkt

- Elke swipe slaat jouw oordeel op voor dát paar (ja/nee), per gebruiker en
  binnen de kast waarin de stukken zitten.
- **Overslaan** is géén oordeel: het paar blijft onbeoordeeld en schuift naar
  achteren in de rij, zodat je eerst alles krijgt wat je nog nooit gezien hebt.
- **Ongedaan maken** wist jouw oordeel over dat paar; het komt daarna gewoon
  weer langs. Dat kan vanaf **Combineer → Al beoordeeld**, of direct op een
  combinatie bij **Outfits** en op de pagina van een kledingstuk. Let op: je
  trekt alleen je *eigen* stem in — keurde een huisgenoot het ook goed, dan
  blijft de combinatie staan.
- Bij **Outfits** geldt een combinatie als goedgekeurd wanneer minstens één
  lid van de kast **ja** zei én niemand **nee**. Zo blokkeert een "nee" van een
  ander een combinatie die jij goedkeurde (handig — vaak heeft de ander gelijk 😉).
- Zie je een combinatie niet terug bij Outfits, dan staat 'ie op de pagina van
  het kledingstuk onder **"Past niet bij"**, mét wie 'm afkeurde. Zo is een
  ontbrekende combinatie te verklaren in plaats van onzichtbaar. Afgekeurde
  paren blijven bewust weg bij Outfits: dat scherm gaat over wat wél kan.
  Je kunt alleen je **eigen** "nee" intrekken — die van een ander is niet aan jou.
- De swipe legt alleen **bovenkleding naast een onderstuk** (bv. polo × broek):
  twee broeken of een polo met een trui zijn geen outfit, dus die komen niet
  langs.
- Een paar staat er altijd hetzelfde bij: het **bovenstuk links** (in de
  weergave "Eén kaart": bovenaan) en het **onderstuk rechts**, ook als je vanaf
  een broek bent gaan combineren — dan staat die broek rechts. Vergelijken gaat
  makkelijker als de kanten niet wisselen, en dezelfde combinatie kan zo nooit
  een tweede keer langskomen met de kanten omgedraaid.

### Suggesties opslaan als combinatie

De automatische suggesties zijn bedoeld als startpunt, dus je ziet er alleen
combinaties tussen waar nog geen besluit over is genomen: alles wat al is
goedgekeurd of afgekeurd valt eruit. Bevalt een suggestie? Met **opslaan als
combinatie** keur je in één keer alle paren erin goed. Bestaat de combinatie al,
of is er ooit een paar uit afgekeurd, dan weigert de app dat — een suggestie
overschrijft nooit een beslissing die al genomen is.

---

## Waarop de kleurensuggesties zijn gebaseerd

De automatische suggesties (bij **Combineer**, **Outfits** en op een
kledingstuk) draaien op een **kleine, lokale kennisbank** — géén externe API,
géén AI en géén wetenschappelijke bron. Het zijn met de hand samengestelde
vuistregels zoals een stylist ze zou hanteren:

- **Neutralen passen bij bijna alles.** Zwart, wit, grijs, beige, bruin, navy
  en denim gelden als neutrale basis en scoren altijd goed.
- **Ton-sur-ton** (twee keer dezelfde kleurfamilie) krijgt een pluspunt.
- Een korte, **handmatig gekozen lijst** van kleurparen die mooi samengaan
  (bv. navy + beige, denim + wit, oranje + blauw) en van paren die botsen
  (bv. rood + roze, groen + oranje).
- Vrij ingetikte kleuren worden eerst teruggebracht tot een klein **basispalet**
  ("marineblauw"/"donkerblauw" → navy, "camel"/"khaki" → beige), zodat ze toch
  meetellen.
- Daarbovenop telt **seizoensoverlap** mee: stukken die geen seizoen kunnen
  delen, worden niet samen voorgesteld.

Kortom: een opzettelijk eenvoudige, op stijlconventies gebaseerde scoring —
bewust geen zwarte doos, maar ook geen objectieve waarheid. Daarom is de lijst
met goede/botsende kleurparen **volledig aanpasbaar** door een beheerder onder
**Instellingen → Combinatie-logica**: pas de regels aan naar je eigen smaak.

---

## Logboek & auditlogging

Alles wat de app doet komt in de **container-logs** terecht
(`docker compose logs -f kledingkast`): wijzigingen, waarschuwingen en fouten,
met tijd, niveau en onderdeel. Met `WARDROBE_LOG_LEVEL=DEBUG` komen ook alle
leesverzoeken erbij.

Een **beheerder** hoeft daar niet voor op de server in te loggen: onder
**Instellingen → Logboek** staan twee tabbladen.

- **Wie deed wat** – de auditlog uit de database: elke wijziging, goedkeuring,
  afkeuring, uitnodiging en (mislukte) login, met wie het deed, wanneer en in
  welke kast. Te filteren op handeling, persoon en tekst. Dit blijft bewaard.
- **Systeemlog** – dezelfde regels als in de container-logs, nieuwste bovenaan.
  Die staan alleen in het geheugen (de laatste ~500) en zijn dus leeg na een
  herstart — handig om even mee te kijken, geen archief.

Wachtwoorden komen er nooit in te staan; bij een mislukte login wordt alleen de
gebruikte gebruikersnaam vastgelegd.

---

## Licentie

Vrij te gebruiken en aan te passen voor eigen gebruik.
