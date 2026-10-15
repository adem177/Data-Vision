# 📊 DataVision

> Plateforme intelligente d'analyse et de visualisation de données — transforme un fichier CSV/Excel brut en dashboard interactif en quelques secondes.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.x-092E20?logo=django&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-2.x-150458?logo=pandas&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-4.x-F68B1F?logo=chart.js&logoColor=white)
![Licence](https://img.shields.io/badge/Licence-MIT-green)

## 🎯 Le problème résolu

Une entreprise possède un fichier Excel de 5 000 ventes (date, produit, catégorie, quantité, prix). Sans outil, il faut parcourir les lignes et construire manuellement les graphiques.

**Avec DataVision**, l'utilisateur importe son fichier et obtient automatiquement :

- ✅ Le chiffre d'affaires total, le panier moyen, le nombre de ventes
- ✅ Les catégories et produits les plus performants — **et les moins performants**
- ✅ L'évolution des ventes dans le temps, **projetée sur les 3 mois à venir**
- ✅ Les **corrélations cachées** entre colonnes (prix ↔ CA, quantité ↔ CA…)
- ✅ La détection des doublons, valeurs manquantes et anomalies
- ✅ Des graphiques filtrables (catégorie, période) et un export CSV/Excel

## 🚀 Démarrage rapide

```bash
git clone https://github.com/TON_PSEUDO/DataVision.git
cd DataVision
python -m venv venv
venv\Scripts\activate        # macOS/Linux : source venv/bin/activate
pip install -r requirements.txt
python data_generator.py     # génère data/sample_sales.csv (5 000 ventes)
python manage.py migrate     # crée la base SQLite + table des analyses
python manage.py runserver   # http://127.0.0.1:8000
```

Ensuite : **crée un compte**, puis clique sur **« Essayer la démo »** ou importe ton propre fichier `.csv` / `.xlsx`. Tes analyses sont sauvegardées et retrouvables dans **« Mes analyses »**.

Pour l'admin Django (gestion des analyses) : crée un superuser puis ouvre `/admin/`

```bash
python manage.py createsuperuser
```

### Compte de démonstration

Pour laisser un visiteur tester l'application sans s'inscrire, crée un compte pré-chargé :

```bash
python manage.py creer_demo
```

Cela crée l'utilisateur `demo` / `DataVision2026` avec l'analyse de démonstration déjà importée. La commande est idempotente : la relancer ne crée aucun doublon. Les identifiants apparaissent en bas de la page de connexion.

## 🛠️ Stack technique

| Technologie | Rôle |
|---|---|
| **Python** | Langage principal |
| **Pandas / NumPy** | Import, nettoyage, statistiques, agrégations |
| **Django** | Backend web : routes, templates, API JSON, admin |
| **Chart.js** | Graphiques interactifs (courbes, barres, anneau) |
| **Bootstrap Icons** | Icônes vectorielles (CDN) |
| **Angular 22** | Preuve de concept : la page `/angular` est rendue côté client |
| **SQLite → PostgreSQL** | Base de dev → production (Niveau 3) |

## 📁 Structure du projet

```
DataVision/
├── manage.py                 # Point d'entrée Django
├── datavision/               # Configuration du projet
│   ├── settings.py           # Apps, bases de données, statiques, médias
│   ├── urls.py               # URLs racines
│   ├── wsgi.py / asgi.py     # Déploiement
├── core/                     # Application principale
│   ├── models.py             # Modèle Projet : analyse sauvegardée par utilisateur
│   ├── formulaires.py        # Formulaire d'inscription
│   ├── views.py              # Ré-export des vues (regroupées en modules ci-dessous)
│   ├── services.py           # Chargement de l'analyseur, recherche d'un projet, KPIs
│   ├── vues_auth.py          # Inscription, connexion, suppression de compte
│   ├── vues_projets.py       # Import, dashboard, renommage, remplacement, export, PDF
│   ├── vues_api.py           # API JSON (Chart.js, Angular, /health)
│   ├── throttle.py           # Limitation de débit des routes coûteuses
│   ├── cache.py              # Cache partagé des analyseurs (locmem / Redis)
│   ├── rapport.py            # Rapport PDF (reportlab, graphiques vectoriels)
│   ├── urls.py               # /inscription /connexion /projets /dashboard/<id> /api/donnees /export
│   ├── admin.py              # Administration des analyses
│   ├── management/commands/  # creer_demo : compte de démonstration pré-créé
│   └── templates/core/       # base, index, dashboard, projets, connexion, inscription
├── analyzer.py               # Moteur d'analyse Pandas (indépendant de Django)
├── data_generator.py         # Génère le jeu de données de démonstration
├── benchmark_lecteur.py      # Mesure le gain du moteur C (×5 mesuré)
├── benchmark_api.py          # Mesure le gain de la mémoïsation de l'API (×4,7 mesuré)
├── front/                    # Preuve de concept Angular (source, page /angular)
├── static/                   # CSS + JS + build Angular (static/angular/)
├── data/sample_sales.csv     # Données de démo (générées)
├── media/uploads/            # Fichiers uploadés (gitignoré)
├── tests/                    # 311 tests Python (pytest)
├── tests_js/                 # 112 tests JavaScript (node:test + jsdom)
├── package.json              # Uniquement les dépendances de test front
├── requirements.txt
└── README.md
```

## ✨ Fonctionnalités

### Niveau 1 — MVP ✅
- [x] Import CSV + aperçu des données
- [x] Nettoyage automatique (doublons, dates, valeurs manquantes)
- [x] KPIs : CA, ventes, panier moyen, produits vendus
- [x] 4 graphiques interactifs
- [x] Messages d'erreur clairs (mauvais format, fichier vide…)

### Niveau 2 — Avancé ✅
- [x] Import Excel (.xlsx)
- [x] Filtres dynamiques (catégorie + période) sans rechargement
- [x] Détection d'anomalies (règle IQR)
- [x] Export des données filtrées en CSV / Excel

### Niveau 3 — Professionnel ✅
- [x] Comptes utilisateurs (inscription / connexion / déconnexion)
- [x] Projets enregistrés : chaque analyse sauvegardée en base, relisible à volonté
- [x] Isolation des données (chaque utilisateur ne voit que ses analyses)
- [x] Administration Django des analyses (`/admin/`)
- [x] Comparaison de deux périodes (variation en %)
- [x] Rapports PDF téléchargeables
- [x] Correspondance manuelle des colonnes (si la détection auto échoue)
- [x] Sécurité : validation de mot de passe, e-mail unique, anti-force-brute
- [x] Déploiement Render (`render.yaml`) + CI GitHub Actions

### Niveau 4 — Fiabilité « Big Data » ✅ (Phase D)
- [x] **Protection mémoire** : au plus `DATAVISION_MAX_ROWS` lignes analysées (500 000 par défaut), l'utilisateur est prévenu si son fichier est tronqué
- [x] **Garde de taille à l'upload** : fichiers de plus de `DATAVISION_MAX_UPLOAD_MB` (100 Mo) refusés avec un message clair
- [x] **Cache partagé** : Redis via `REDIS_URL` en production (les workers gunicorn partagent les analyseurs), cache local en développement
- [x] **Dégradation gracieuse** : si Redis tombe, l'analyse se recharge depuis le fichier au lieu d'afficher une erreur
- [x] **Intégrité de l'import** : alerte visible sur le dashboard si le fichier est tronqué, refus explicite des fichiers trop lourds

### Niveau 5 — Profondeur d'analyse ✅ (Phase E)
- [x] **Prévision de tendance** : régression linéaire par moindres carrés sur l'évolution mensuelle, avec R² de fiabilité et projection sur 3 mois (tracée en pointillés sur le graphique)
- [x] **Corrélations de Pearson** : lien direct ou inverse entre colonnes numériques, qualifié (forte / modérée / faible / négligeable) et illustré par une jauge
- [x] **Top et Flop** : les meilleurs produits *et* ceux à retirer du catalogue
- [x] Tout est repris dans le **rapport PDF**

### Niveau 6 — Finitions ✅ (Phase F)
- [x] **Mode sombre** : bouton 🌙/☀️ dans la barre supérieure, préférence mémorisée dans `localStorage` et respect de la préférence système — appliqué avant le rendu pour éviter le clignotement
- [x] **Compte de démonstration pré-créé** : `python manage.py creer_demo` → identifiants affichés sur la page de connexion (masquables avec `DATAVISION_DEMO_LOGIN=False`)
- [x] **Pagination de l'aperçu** : « Page 2 sur 7 · 30 lignes », boutons désactivés aux extrémités, réinitialisée à chaque changement de filtre
- [x] **Recherche et tri** dans « Mes analyses » : recherche libre sur le nom de l'analyse *ou* du fichier, tri par date, nom ou chiffre d'affaires
- [x] **Accessibilité** : lien d'évitement au clavier, point d'ancrage `#contenu-principal`, `role="status"` et `aria-live` sur le chargeur, `aria-pressed`/`aria-label` sur le bouton de thème
- [x] **Partage** : favicon SVG embarqué, balises Open Graph et `theme-color` — l'aperçu du lien est propre sur Discord, WhatsApp ou LinkedIn
- [x] **Configuration par variables d'environnement** : `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `REDIS_URL`, `DATAVISION_MAX_ROWS`

### Niveau 7 — Performance du lecteur ✅ (Bloc B)

- [x] **Double moteur de lecture** : le fichier est d'abord inspecté sur ses 20 premières lignes ; si elles comptent toutes le même nombre de champs, Pandas lit d'un trait avec son **moteur C**, sinon il part directement sur le moteur Python tolérant
- [x] **Comptage exact préservé** : le moteur C lève une erreur à la première ligne mal formée → repli automatique sur le moteur Python, seul à pouvoir *compter* les lignes sautées. L'avertissement affiché à l'utilisateur reste juste dans tous les cas
- [x] **Mesuré** : **×5 sur 300 000 lignes** (0,46 s → 0,09 s), et les deux chemins produisent strictement le même dataframe

```bash
python benchmark_lecteur.py 300000
```

```
Lecture Pandas seule (hors nettoyage)
  moteur Python            0.458 s
  moteur C                 0.089 s
  gain x5.1

✔ les deux chemins produisent exactement le même dataframe
✔ fichier mal formé : 3 lignes ignorées sur 3 attendues
```

### Niveau 8 — Fiabilité en production ✅ (Plan d'amélioration)

**Bugs corrigés**
- [x] **Mapping appliqué immédiatement** : « Appliquer » sur `/projet/<id>/colonnes` vide maintenant le cache de l'analyseur — sans cela, le choix manuel était ignoré jusqu'à l'expiration du cache (1 h), le cache **sérialisant** sa valeur
- [x] **Route `/health` honnête** : statut `503` quand la base est injoignable (elle renvoyait `200` même en cas de panne : un moniteur ne l'aurait jamais signalée)
- [x] **Fichier perdu** : un projet orphelin de son fichier redirige vers la liste avec un message clair (au lieu d'une erreur 500), l'API renvoie un `404` explicite — et le **réimport** depuis « Mes analyses » répare le projet
- [x] **Jeu de démonstration protégé** : `/demo` nettoie la base derrière lui si le CSV de démonstration est illisible
- [x] **Catégorie fantôme « nan »** : `?categorie=nan` ne renvoie plus toutes les lignes sans catégorie (`astype(str)` transformait chaque `NaN` en la chaîne « nan »)

**Durcissement du déploiement**
- [x] **Identifiants de démo masqués** sur Render (`DATAVISION_DEMO_LOGIN=False`) — les afficher revient à publier un compte d'accès
- [x] **Limitation de débit** : 10 imports/heure et 60 exports/minute par compte, sans dépendance externe (compteur dans le cache Django, réponse `429` lisible)
- [x] **Cache sous taille** : au-delà de `DATAVISION_CACHE_MAX_ROWS` (200 000 lignes), l'analyseur n'est plus sérialisé dans Redis — relecture du fichier préférée à une mémoire Redis proportionnelle

**Performance de l'API**
- [x] **Mémoïsation** : les six agrégations de `/api/donnees` (KPIs, évolution, catégories, classement, corrélations, anomalies) sont calculées **une fois par filtre** ; la pagination ne recalcule plus rien

**Gestion des analyses**
- [x] **Renommage** d'une analyse depuis « Mes analyses » (le fichier importé n'est pas touché)
- [x] **Remplacement du fichier** d'une analyse existante : garde l'identifiant, les indicateurs et le réglage des colonnes ; l'ancien fichier n'est retiré du disque qu'une fois le nouveau confirmé lisible
- [x] **Suppression de compte** confirmée par mot de passe : analyses, fichiers sur disque et session supprimés
- [x] **Graphiques vectoriels dans le PDF** : histogramme d'évolution mensuelle et barres de chiffre d'affaires par catégorie (`reportlab.graphics`)

### Niveau 9 — Finitions de production ✅ (Plan d'amélioration)

**Pages d'erreur du site**
- [x] **404 / 403 / 500 en français**, dans le style du site (`core/vues_erreurs.py`), déclarées via `handler404/403/500` — hors DEBUG, Django aurait affiché ses pages nues, en anglais
- [x] **Refus CSRF stylé** : `CSRF_FAILURE_VIEW` pointe vers la page « Accès refusé » (sans ce réglage, un POST sans jeton rend la page brute de Django)
- [x] **Page 500 sans fuite** : aucun nom de fichier, aucune trace d'exécution dans le HTML — la trace part dans les logs

**Supervision**
- [x] **`healthCheckPath: /health`** dans `render.yaml` : Render détecte une instance dont la base est injoignable (`503`) au lieu de la croire en vie
- [x] **`manage.py check --deploy`** en CI, exécuté avec `DEBUG=False` — sa première exécution a trouvé un vrai bug : en production, les e-mails (mot de passe oublié) partaient dans la console ; le repli est désormais assumé et commenté (`mail.E001` silencé)

**Journalisation**
- [x] **Console uniquement** (Render collecte stdout/stderr : aucun fichier de log à purger), niveau réglable avec `DATAVISION_LOG_LEVEL` (défaut `INFO`), valeur absurde = repli silencieux sur `INFO`

**Espaces de travail**
- [x] **Pagination de « Mes analyses »** : 30 par page, `q`/`tri` conservés dans les liens (tag `{% querystring %}`), `?page=abc` et `?page=999` avalés sans erreur 500
- [x] **Commande `nettoyer_media`** : audit (dry-run) des fichiers de `media/` plus rattachés à aucune analyse, `--appliquer` pour agir, `--age-minimum` (24 h) et `--conserver FRAGMENT` pour préserver un CSV déposé à la main — **740 fichiers orphelins (7,1 Mo) nettoyés** en conservant les fichiers réels

**Preuves**
- [x] **Tests CSRF** (`enforce_csrf_checks=True`) : `403` sans jeton sur les quatre routes POST, jeton de formulaire et en-tête `X-CSRFToken` acceptés, jeton falsifié refusé
- [x] **Banc `benchmark_api.py`** : sur 300 000 lignes (9 Mo), la séquence de six appels à `/api/donnees` passe de 1,02 s à 0,22 s avec la mémoïsation (gain ×4,7, chiffres KPI identiques dans les deux cas)

### Niveau 10 — Fidélité éditoriale ✅ (Inspiration Datawrapper)

Quatre écarts relevés sur Datawrapper et comblés — **sans ajouter la moindre
dépendance** (les deux nouvelles couches tiennent en JavaScript natif et en
Pandas déjà présent).

**Ce qui a été emprunté**
- [x] **Annotations posées sur la courbe** : maximum, minimum et plus forte variation dessinés directement sur la courbe d'évolution — plugin Chart.js maison (`annotationsCourbe`), avec la règle de Datawrapper : jamais deux libellés à un indice d'écart, et sous 480 px de large, les anneaux sans texte. Les points remarquables ne restent plus enfermés dans leur tableau
- [x] **Palette daltonisme-safe** : les graphiques passent à la palette d'Okabe & Ito (2008), six teintes conçues pour rester distinctes sous deutéranopie, protanopie et tritanopie. Le vermillon `#D55E00` est réservé aux barres du « Flop » (le Top 5 s'en prive), la projection devient le bleu principal éclairci en pointillés — et le PDF suit, barres en `#0072B2`
- [x] **Note de l'analyste + source** : deux champs éditables sur le dashboard (formulaire en `<details>`, sans JavaScript), affichés en tête de page, **reproduits dans le PDF** sous le titre et **imprimés en en-tête de chaque export PNG** (titre, note, source, filet de séparation) — une image DataVision collée ailleurs reste lisible et citable
- [x] **Dispersion (nuage de points)** : la paire de colonnes la plus corrélée, avec droite de régression par moindres carrés et titres d'axes posés après coup (le couple dépend des filtres). Le couple retenu **exclut toujours le « CA »** — corréler un total à l'un de ses facteurs (CA = prix × quantité) ne dirait qu'une tautologie — et l'échantillon (600 points au plus) est prélevé **systématiquement sur toute la plage** du fichier

**Ce que ça a coûté**
- [x] Migration `core.0003` (2 champs) + route `POST /projet/<pk>/note` : propriétaire uniquement, 1000 et 300 caractères maximum, texte toujours échappé
- [x] `hidden` renforcé en CSS : `.graphique { display: flex }` neutralisait l'attribut `hidden` — la carte Dispersion ne se serait jamais masquée
- [x] `/api/donnees` réclame désormais **sept agrégations** : le banc `benchmark_api.py` et le test de mémoïsation les couvrent toutes


## 🧪 Tests

```bash
# Moteur Python (Django + Pandas) — 311 tests, ~4 min
pytest tests/ -v

# Front-end (JavaScript) — 112 tests, ~2 s
npm ci       # une seule fois
npm test
```

### Moteur Python — 311 tests

- le moteur d'analyse : nettoyage, détection des colonnes, KPIs, filtres, exports, pagination de l'aperçu
- le parcours utilisateur : inscription, protection des pages, isolation entre comptes, recherche et tri des analyses
- la comparaison de périodes, la génération PDF et le mapping manuel des colonnes
- la sécurité : e-mail en double, mot de passe faible, blocage après tentatives échouées
- la Phase D : troncature des fichiers géants, cache partagé, garde de taille à l'upload
- la Phase E : régression linéaire et projection, corrélations, classement Top/Flop
- la Phase F : pagination, recherche/tri, mode sombre, compte démo, accessibilité
- le Bloc B : bascule de moteur, comptage exact des lignes mal formées, équivalence des deux chemins
- la robustesse des entrées : une date illisible dans l'URL (`?debut=pasune`)
  fait sauter la borne correspondante au lieu de renvoyer une erreur 500
- la fiabilité (`test_fiabilite.py`) : `/health` en 503 quand la base tombe, projet
  orphelin de son fichier (dashboard, API, export, rapport), jeu de démo illisible
- le durcissement (`test_debit.py`, `test_configuration.py`) : limite de débit
  par compte, cache refusant les analyseurs trop gros, valeurs de `render.yaml`
- la performance (`test_memo.py`) : les sept agrégations de `/api/donnees` ne sont
  recalculées qu'au changement de filtre, et un changement de mapping les invalide
- la gestion des analyses (`test_gestion_projets.py`, `test_compte.py`) :
  renommage, remplacement du fichier, suppression de compte confirmée par mot de passe
- les pages d'erreur (`test_erreurs.py`) : 404 / 403 / 500 rendues hors `DEBUG`,
  sans trace d'exécution dans le HTML de la 500
- le CSRF (`test_csrf.py`) : les cinq routes POST refusent sans jeton ; le jeton
  arrive par le formulaire ou l'en-tête `X-CSRFToken`, jamais falsifié
- la pagination (`test_pagination.py`) : 30 analyses par page, `q`/`tri` conservés
  dans les liens, `?page=abc` et `?page=999` avalés sans erreur 500
- le nettoyage de `media/` (`test_nettoyage_media.py`) : dry-run par défaut, un
  fichier rattaché est intouchable, `--age-minimum` et `--conserver` respectés
- la journalisation (`test_journalisation.py`) : handler console, niveau `INFO` par
  défaut, surcharge par `DATAVISION_LOG_LEVEL`, alertes de cache visibles
- le banc de l'API (`test_benchmark_api.py`) : la mémoïsation ne change aucun
  chiffre, et le banc remet `TAILLE_MEMO` en quittant
- la dispersion (`test_dispersion.py`) : couple choisi hors « CA », échantillon
  couvrant toute la plage du fichier, droite exactement celle des points renvoyés
- la note de l'analyste (`test_note_analyste.py`) : propriétaire uniquement,
  longueurs bornées, texte échappé, note et source présentes dans le PDF
  (flux reportlab décodés ASCII85 + Flate pour aller chercher le texte)

### Front-end — 112 tests

Aucun framework : le **moteur de tests intégré à Node** (`node:test`) suffit,
et `jsdom` fournit le DOM. Le code testé est celui servi au navigateur, sans
adaptation.

```bash
tests_js/
├── aide.js             # harnais : DOM jsdom + fausse Chart.js + gabarit de test
├── securite.test.js    # échappement anti-XSS : colonnes, produits, corrélations
├── gabarit.test.js     # contrat gabarit ↔ JS (les id et data-kpi existent-ils ?)
├── formats.test.js     # formatDT, formatNombre, variations, périodes
├── filtres.test.js     # construction de la requête, exports, cycle de vie
├── rendu.test.js       # ce que chaque fonction écrit réellement dans le DOM
├── annotations.test.js # annotations de courbe : calcul pur + plugin dessiné
├── dispersion.test.js  # nuage de points : carte, droite, légende, états vides
└── couleurs.test.js    # palette Okabe-Ito verrouillée, teintes par graphique
```

Points saillants :

- **`echapper()` contre les XSS** — un fichier CSV peut contenir `<script>` dans
  un nom de colonne ; le test vérifie qu'il reste du texte et rien d'autre.
- **Contrat gabarit ↔ JS** — si quelqu'un renomme un `id` dans `dashboard.html`,
  le JS renvoie `null` et l'interface casse *silencieusement*. Ce test l'attrape.
- **États limites** — page unique, modèle de régression indisponible, aucune
  catégorie, valeurs `null`/`NaN`, gabarit incomplet.
- **Cycle de vie** — démarrage, changement de filtre, pagination par clic,
  changement de thème (les graphiques se repeignent sans nouvelle requête).
- **Comparaison de périodes** — le bouton « Comparer » envoie les quatre
  bornes saisies, et encaisse un champ manquant du gabarit, une réponse 404
  ou un réseau coupé sans promesse rejetée.
- **Annotations de courbe** — le calcul (max, min, plus forte variation) est
  une fonction pure testée au cas par cas ; le plugin, lui, ne dessine rien
  quand la place manque (mobile) ou quand la ligne ne raconte rien.
- **Palette & en-têtes d'export** — les six teintes Okabe-Ito sont verrouillées
  par le test, et l'en-tête des exports PNG (titre, note, source) mesure sa
  hauteur avant de repeindre la toile composite.

> `node_modules/` est ignoré : le dépôt ne contient que du code Python produit
> et ce harnais de test.

## ⚛️ Preuve de concept Angular

La page **`/angular`** (lien « Page Angular (démo) » sur `/projets`) est hébergée
par Django mais **rendue par Angular** : le composant appelle les API JSON
`/api/projets` puis `/api/donnees?id=…` et affiche les KPIs ainsi qu'un graphique
en barres dessiné en CSS. Tout le reste du site reste en Django + JavaScript
vanilla.

| Élément | Emplacement |
|---|---|
| Source Angular | `front/src/app/` (`app.ts` : signaux + appels HTTP, `app.html`, `app.css`) |
| Build | `static/angular/browser/main.js` (~140 ko, noms de fichiers stables) |
| Gabarit Django | `core/templates/core/angular.html` (`{% block scripts %}` charge `main.js`) |
| API dédiée | `GET /api/projets` — analyses du compte connecté (session requise) |
| Tests | `tests/test_angular.py` — 5 tests (page, API, isolation des comptes) |

```bash
# Après une modification du front Angular
npm --prefix front install    # une seule fois
npm --prefix front run build  # → static/angular/browser/
```

Points d'attention :

- **Django 6.1 met les gabarits en cache mémoire** : redémarre le serveur après
  avoir modifié un `.html` (sinon l'ancien rendu reste servi).
- **Angular 22 ne utilise plus zone.js** : l'état du composant doit être stocké
  dans des *signaux*, sinon l'écran ne se rafraîchit jamais après les réponses
  HTTP (piège rencontré et corrigé ici).

## 🚀 Déploiement en ligne (Render)

1. Pousse le projet sur GitHub
2. Sur [render.com](https://render.com), crée un **Blueprint** et connecte le repo
3. Render lit `render.yaml` et crée l'app + la base PostgreSQL automatiquement
4. Renseigne `DJANGO_ALLOWED_HOSTS` avec l'URL donnée par Render

La route **`/health`** répond `{"statut": "ok"}` — c'est celle que Render surveille.

En local, la base reste SQLite (aucune configuration requise).

### Variables d'environnement

Toutes les valeurs par défaut conviennent au développement ; en production, seules
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG` et `DJANGO_ALLOWED_HOSTS` sont indispensables.

| Variable | Rôle | Défaut |
|---|---|---|
| `DJANGO_SECRET_KEY` | Clé secrète Django | clé de développement |
| `DJANGO_DEBUG` | Mode debug | `True` |
| `DJANGO_ALLOWED_HOSTS` | Domaines autorisés | vide |
| `DATABASE_URL` | Base PostgreSQL (sinon SQLite) | — |
| `REDIS_URL` | Cache partagé entre workers (sinon local) | — |
| `DATAVISION_MAX_ROWS` | Lignes analysées au maximum | `500000` |
| `DATAVISION_CACHE_MAX_ROWS` | Lignes au-delà desquelles un analyseur n'est plus mis en cache (`0` = sans limite) | `200000` |
| `DATAVISION_MAX_UPLOAD_MB` | Taille d'upload maximale | `100` |
| `DATAVISION_LOG_LEVEL` | Niveau de journalisation (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `DATAVISION_DEMO_LOGIN` | Afficher les identifiants démo sur la page de connexion (`False` sur Render) | `True` |
| `DATAVISION_DEMO_USER` / `DATAVISION_DEMO_PASSWORD` | Identifiants du compte démo | `demo` / `DataVision2026` |

## 🌐 CI (GitHub Actions)

`.github/workflows/ci.yml` lance deux jobs à chaque push : **311 tests Python**
(Python 3.11 et 3.12) et **112 tests JavaScript** (Node 22). Chaque job Python
exécute aussi `manage.py check`, puis `manage.py check --deploy` **avec un
`DEBUG` éteint** : c'est la configuration réelle de Render, et c'est elle qui
attrape les erreurs invisibles en développement (HTTPS, HSTS, clé secrète,
e-mails). Ajoute le badge en
haut du README :

```markdown
![CI](https://github.com/TON_PSEUDO/DataVision/actions/workflows/ci.yml/badge.svg)
```

## 🧹 Conception

- `analyzer.py` est **indépendant de Django** : le moteur d'analyse peut être réutilisé dans un script, un notebook ou une autre application.
- Chaque analyse est **rechargée à la volée depuis le fichier** puis mise en cache (`core/cache.py`) — Redis si `REDIS_URL` est défini, cache local sinon. Pas d'état permanent : redémarrer le serveur ne perd aucune donnée.
- Les gros fichiers sont **tronqués à `LIMITE_LIGNES`** (`analyzer.py`) : la mémoire reste bornée quelle que soit la taille du fichier importé.
- L'API `/api/donnees` renvoie du JSON : le frontend se contente de mettre à jour les graphiques Chart.js.

## 📄 Licence

MIT — voie libre pour l'apprentissage et le portfolio.
