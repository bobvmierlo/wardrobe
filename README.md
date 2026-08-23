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
  nog geen account? Stuur een **uitnodigingslink** waarmee ze zich zelf registreren.
- 💾 **Back-up & export** – iedereen kan z'n eigen kast downloaden als Excel-bestand
  met de foto's erbij; een beheerder maakt een volledige back-up of een exacte
  momentopname, en kan een export weer terugzetten.
- 📋 **Logboek** – een beheerder ziet in de app wie wat wijzigde, goedkeurde of afkeurde,
  plus de technische logregels van de server.
- 👥 **Accounts** – jij én je partner een eigen login. Een **beheerder** kan bij
  elke kast, en heeft daarnaast ook gewoon z'n eigen kast.
- 📱 **PWA & offline** – installeerbaar op je telefoon (Toevoegen aan beginscherm).
  Zonder verbinding blijf je ingelogd, zie je je kast en je outfits zoals ze het
  laatst geladen waren, en kun je gewoon doorswipen: je oordelen worden verstuurd
  zodra je weer online bent — ook als je de app tussendoor sluit.
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
2. Ga naar **Instellingen → Wachtwoord wijzigen** en kies een eigen wachtwoord.
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

### Momentopname terugzetten

Een momentopname is een exacte kopie en gaat buiten de app om terug:

```bash
docker compose down
# pak het archief uit en zet de bestanden in het volume:
#   wardrobe.db  ->  /data/wardrobe.db
#   uploads/*    ->  /data/uploads/
docker compose up -d
```

Of maak er zelf een van buitenaf, zonder de app:

```bash
docker run --rm -v kledingkast-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/kledingkast-backup.tar.gz -C /data .
```

Terugzetten: draai hetzelfde met `tar xzf` in `/data`.

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
```

Standaard-admin bij eerste start: `admin` / `changeme`.

---

## Projectstructuur

```
backend/            FastAPI-app (Python)
  app/
    main.py         app + seed-admin + migraties + serveert de gebouwde frontend
    models.py       User, Wardrobe, WardrobeMember, Item, Match (SQLAlchemy)
    access.py       kast-toegang & rollen (eigenaar/beheerder/bewerker/kijker)
    routers/        auth, users, wardrobes, items, matches, catalog, color_rules,
                    imports, invitations, admin_log
    images.py       foto-verwerking (Pillow)
    matching.py     categorie-groepen voor slimme combinatie-suggesties
    audit.py        auditlog: wie deed wat (naar database én logregel)
    logging_setup.py logging naar stdout (docker logs) + ringbuffer voor in de app
frontend/           React + Vite (TypeScript)
  src/pages/        Login, Invite, Wardrobe, AddItem, ItemDetail, Combine, Outfits,
                    Settings, AdminLog
  src/wardrobe.tsx  kast-context (welke kast is actief + je rol)
  src/components/   SwipeCard, ItemForm, BottomNav, WardrobeSwitcher, SuggestionList,
                    JudgedPairList, PartnerGrid
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

Bij het opstarten controleert de app of er resten liggen van accounts die in
een oudere versie half verwijderd zijn, en ruimt die op. In beide gevallen zegt
het logboek wat er gebeurd is:

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

Registratie staat standaard dicht: niemand kan zichzelf zomaar aanmelden. Wél kun
je vanaf **Instellingen → Mijn kast delen → Uitnodigen met een link** een
persoonlijke link maken. Zet erbij voor wie 'ie is, kies de rol en hoe lang de
link geldig blijft, en stuur 'm via WhatsApp/mail.

Wie de link opent ziet van wie de kast is en welke rol 'ie krijgt, en kiest dan:

- **al een account** → inloggen, de uitnodiging wordt meteen geaccepteerd;
- **nog geen account** → ter plekke registreren; diegene komt direct in je kast
  terecht en krijgt daarnaast een eigen kast.

Een link werkt **één keer** en verloopt daarna vanzelf. Zolang 'ie nog niet
gebruikt is kun je 'm altijd **intrekken**.

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
- De swipe toont eerst **cross-categorie**-paren (bv. polo × broek) omdat die
  het nuttigst zijn; twee stukken uit dezelfde groep komen later.

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
