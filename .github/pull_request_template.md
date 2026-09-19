<!-- Vul in wat van toepassing is en gooi de rest weg. Een kleine wijziging
     verdient een korte beschrijving; een grote verdient uitleg. -->

## Wat verandert er

<!-- In gewone taal: wat merkt iemand die de app gebruikt hiervan? -->

## Waarom

<!-- Het probleem of de wens erachter. Hoort er een issue bij? Zet "Fixes #123". -->

## Hoe het is nagelopen

<!-- Wat je zelf hebt gedraaid en wat je zag. De CI draait dit ook, maar die
     kan niet zien of het scherm klopt. -->

- [ ] `cd backend && pytest -q`
- [ ] `cd frontend && npm run lint && npm run build`
- [ ] In de draaiende app geprobeerd — op telefoonformaat, en op een breed scherm als de indeling daar anders is

## Waar het aan raakt

<!-- Alleen aankruisen wat van toepassing is. -->

- [ ] **Database** — nieuwe tabel of kolom, met een migratie in `backend/app/migrations.py` die ook op een bestaande kast draait (zie `backend/tests/test_migrations.py`)
- [ ] **Offline** — de wachtrij, de service worker, of wat er zonder verbinding te zien en te doen is
- [ ] **Toegang** — wie wat mag (beheerder, bewerker, kijker), of foto's die achter de login horen te blijven
- [ ] **Back-up & export** — het formaat van een export, of het terugzetten ervan
- [ ] **Instellingen** — nieuwe of gewijzigde `WARDROBE_*`-variabelen, ook bijgewerkt in de README
- [ ] **Schermteksten** — nieuwe teksten staan in het Nederlands, net als de rest van de app

## Schermafbeeldingen

<!-- Alleen bij iets zichtbaars. Voor en na helpt het meest; telefoonformaat
     is belangrijker dan desktop. -->
