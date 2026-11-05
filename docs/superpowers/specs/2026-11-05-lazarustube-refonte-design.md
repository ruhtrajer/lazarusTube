# lazarusTube — Refonte P0/P1 + quick wins P2 — Design

- **Date** : 2026-11-05
- **Statut** : proposé, en attente de validation
- **Cible** : iPad 2 (1024×768), Safari 9 / iOS 9 — contrainte stricte
- **Stack conservée** : Python 3.11, Flask, yt-dlp, ffmpeg, node, Docker

## 1. Intention et pourquoi

L'application fonctionne, mais elle n'est pas fiable pour de longues vidéos et son
interface ne donne pas envie de l'utiliser :

- `/stream` télécharge la vidéo **avant** d'envoyer le premier octet ; Safari peut
  attendre plusieurs minutes, voire abandonner, sans aucun retour visuel.
- `/check` renvoie toujours `200`, donc les erreurs de préparation ne remontent
  jamais au lecteur.
- Les résultats de recherche n'ont **pas de miniatures** avec les versions
  récentes de yt-dlp (`--flat-playlist` ne renvoie plus `thumbnail`).
- Les cartes de résultats sont pleine largeur : 10 résultats = beaucoup de
  défilement sur un écran 1024×768.
- La page de lecture n'affiche ni titre, ni chaîne, ni durée.
- Aucune reprise de lecture, aucun historique, aucun favori.
- Le rouge de l'interface ne correspond pas au logo (palette réelle :
  bleu marine, bleu, turquoise, corail, fond clair).

Objectif : une application **fiable**, **lisible** et **agréable** sur iPad 2,
sans sacrifier la compatibilité iOS 9.

## 2. Objectifs, non-objectifs, anti-objectifs

### Objectifs

1. La page de lecture s'affiche immédiatement ; la préparation est visible et
   progressive ; aucun appel HTTP ne reste bloqué pendant le téléchargement.
2. Les vidéos sont téléchargées dans un format que l'iPad 2 décode réellement
   (H.264 `avc1` + AAC `m4a`, ≤ 720p), avec validation avant diffusion.
3. Les résultats affichent miniature, durée, chaîne et nombre de vues, en grille
   de 2 colonnes sur 1024×768.
4. Une identité visuelle cohérente, dérivée du logo, partagée par toutes les pages.
5. Reprise de lecture, historique, favoris, recherches récentes et collage d'une
   URL YouTube.
6. Code structuré, testé (pytest) et maintenable, sans build ni framework JS.
7. Aucune régression sur Safari 9 : ES5, CSS compatible, pas de fonctionnalité
   moderne non supportée.

### Non-objectifs (cette phase)

- Pagination / « plus de résultats ».
- Mode audio seul.
- File d'attente et lecture automatique de la suivante.
- Sous-titres.
- Comptes utilisateurs, synchronisation entre appareils.
- HTTPS, proxy live YouTube, service worker / mode hors-ligne complet.
- Refonte en SPA ou ajout de React/Vue.

### Anti-objectifs

- Ajouter une étape de build, un bundler ou un framework front.
- Utiliser CSS Grid, variables CSS, `position: sticky`, `gap` flex ou `aspect-ratio`.
- Bloquer un thread HTTP pendant un téléchargement.
- Servir un fichier partiel ou non validé.
- Supprimer un fichier pendant qu'il est lu.
- Dépendre du champ `thumbnail` de yt-dlp.
- Télécharger en 1080p par défaut sur un A5.

## 3. Contraintes

### Safari 9 / iOS 9

- **JS** : ES5 uniquement — pas de `const`/`let`, flèches, templates literals,
  `fetch`, `async`/`await`, classes, modules. `XMLHttpRequest`, `JSON`,
  `localStorage`, `addEventListener` sont disponibles.
- **DOM** : pas de `NodeList.forEach`, pas de `Element.closest`, pas de
  `classList.toggle` avec second argument. Utiliser des boucles `for` et
  `className`.
- **CSS** : flexbox avec préfixes `-webkit-`, `inline-block`, `calc()`, `rem`,
  `@media`, animations CSS avec `-webkit-`. Interdits : Grid, variables CSS,
  `position: sticky`, `gap`, `aspect-ratio`, `clamp()`, `:focus-visible`.
  `-webkit-line-clamp` est disponible pour tronquer les titres.
- **Vidéo** : `playsinline` **et** `webkit-playsinline`; H.264 + AAC dans MP4;
  `preload="metadata"`; pas d'autoplay sans geste utilisateur.
- **Métadonnées** : `apple-touch-icon` et `apple-mobile-web-app-capable`
  fonctionnent ; pas de service worker (Safari 11.1+).
- **Inputs** : police ≥ 16px pour éviter le zoom automatique au focus.
- **Cibles tactiles** : ≥ 44×44 px.

### Réseau / matériel

- HTTP simple sur le port 3616, pas de TLS (contrainte iOS 9 existante).
- iPad 2 : A5, 512 Mo de RAM. Pages légères, miniatures 320×180, pas de librairie
  JS lourde.
- Les téléchargements peuvent durer plusieurs minutes ; l'interface ne doit pas
  en dépendre pour s'afficher.
- yt-dlp évolue souvent : ne pas dépendre de champs instables, valider les
  formats, journaliser les erreurs.
- `ffmpeg`, `ffprobe` et `node` sont présents dans l'image Docker.
- Le cache doit survivre aux redémarrages du conteneur (volume Docker).

## 4. Approches considérées

### A. Chirurgie ciblée

Modifier les deux templates et `app.py` sur place, ajouter un gestionnaire de
téléchargement en mémoire et du localStorage dans les scripts existants.

- **Avantages** : rapide, peu de fichiers, aucun risque de build.
- **Inconvénients** : CSS dupliqué entre accueil et lecture, templates longs,
  logique métier mélangée aux routes, difficile à tester et à étendre.

### B. Refonte structurée — **choisie**

Même stack, mais organisation claire : `base.html` + partiels Jinja, CSS et JS
partagés dans `static/`, modules Python dédiés (`ids`, `formats`, `cache`,
`jobs`, `ytdlp`, `streaming`), tests pytest.

- **Avantages** : design partagé, logique testable, base saine pour les
  fonctionnalités suivantes, toujours zéro build et compatible iOS 9.
- **Inconvénients** : un peu plus de fichiers et de travail initial.

### C. Interface type « app »

Le serveur ne renvoie que du JSON ; tout l'écran est rendu en JS ES5 avec XHR et
localStorage ; navigation sans rechargement.

- **Avantages** : navigation fluide, file d'attente et état global faciles.
- **Inconvénients** : beaucoup de code ES5 à maintenir, gestion du back/forward,
  debugging plus difficile sur Safari 9, surdimensionné pour 10 résultats.

**Décision** : B. A est trop à l'étroit pour les fonctionnalités ; C ajoute du
risque pour un gain limité sur un iPad 2.

## 5. Architecture cible

```
app.py                     # create_app(), routes, filtres, error handlers
config.py                  # lecture des variables d'environnement + défauts
ids.py                     # validation / extraction d'un ID YouTube
formats.py                 # sélecteur de format yt-dlp + validation ffprobe
ytdlp.py                   # wrapper subprocess : recherche, métadonnées, download
jobs.py                    # Job, JobRegistry, état, progression, retry, sémaphore
cache.py                   # MediaCache (LRU, publication atomique), SearchCache,
                           # MetaCache, ThumbCache, StreamRegistry
streaming.py               # parsing Range + réponse 200/206/416
templates/
  base.html                # shell commun (header, nav, footer, assets)
  index.html               # accueil + résultats
  watch.html               # page de lecture
  library.html             # historique / favoris (coquille statique)
  errors/400.html
  errors/404.html
  errors/500.html
static/
  css/app.css              # design system complet, CSS compatible Safari 9
  js/app.js                # namespace Lazarus + helpers ES5 (XHR, storage, format)
  js/search.js             # recherches récentes, état de chargement
  js/watch.js              # préparation, polling, lecteur, reprise, favoris
  js/library.js            # rendu historique / favoris
  img/logo.png             # logo redimensionné (généré depuis la source)
  img/apple-touch-icon.png # 152×152
  img/favicon.png          # 32×32
tests/
  conftest.py
  test_ids.py
  test_formats.py
  test_streaming.py
  test_cache.py
  test_jobs.py
  test_routes.py
  test_js_es5.py
requirements.txt
requirements-dev.txt       # pytest
```

### Responsabilités

- **`config.py`** : valeurs par défaut + surcharge par variables d'environnement.
  Aucune lecture d'environnement ailleurs.
- **`ids.py`** : `extract_video_id(text)` et `is_valid_video_id(value)`.
- **`formats.py`** : `FORMAT_SELECTOR`, `FORMAT_SELECTOR_FALLBACK`,
  `validate_mp4(path)` via `ffprobe`.
- **`ytdlp.py`** : `YtDlp` avec `search(query, limit)`,
  `download(video_id, tmpdir, on_progress, on_meta)`. Détecte le chemin de node.
- **`jobs.py`** : registre thread-safe, machine à états, sémaphore de concurrence,
  timeout avec kill du groupe de processus, snapshot JSON.
- **`cache.py`** :
  - `MediaCache` : chemins, publication atomique (MP4 + sidecar JSON), éviction
    LRU par taille et âge, refcount des flux actifs.
  - `SearchCache` : TTL 10 min, max 100 requêtes.
  - `MetaCache` : cache mémoire TTL 1 h (max 200) au-dessus des sidecars JSON
    persistants ; une méta manquante est relue depuis `<id>.json`.
  - `ThumbCache` : téléchargement + cache disque des miniatures.
  - `StreamRegistry` : `begin(path)` / `end(path)` pour protéger la lecture.
- **`streaming.py`** : `parse_range(header, size)` et `range_response(path, ...)`.
- **`app.py`** : `create_app(overrides=None)`, construit les services, les expose
  dans `app.extensions["lazarus"]`, enregistre routes, filtres et erreurs.

### Injection de dépendances

Pas de variable globale métier. `create_app()` construit un objet `Services`
(config, cache, jobs, ytdlp, thumbs, search_cache, meta) et le stocke dans
`app.extensions["lazarus"]`. Les tests peuvent injecter des faux services via
`overrides` ou remplacer `app.extensions["lazarus"].ytdlp`.

## 6. Flux de données

### 6.1 Recherche

```
GET /search?q=...&refresh=0|1
  → normalisation de q (trim, max 200 caractères)
  → si q est une URL/ID YouTube : redirect 302 vers /watch?v=<id>
  → SearchCache.get(q) si refresh=0
  → sinon YtDlp.search(q, limit=10)
  → parsing JSON lines, validation des IDs
  → miniature dérivée : /thumb/<id>.jpg
  → MetaCache.put(id, meta)
  → SearchCache.put(q, results)
  → rendu index.html
```

- Champs utilisés : `id`, `title`, `duration`, `channel`/`uploader`,
  `view_count`, `live_status`.
- `thumbnail` n'est pas utilisé : l'URL est reconstruite côté serveur.
- Les directs et les premieres (`is_live`, `is_upcoming`) sont marqués et
  refusés à la lecture avec un message clair.
- En cas d'échec : message générique, détail technique dans les logs, lien
  « Réessayer » (`/search?q=...&refresh=1`).

### 6.2 Préparation et lecture

```
GET /watch?v=<id>
  → validation de l'ID
  → méta depuis MetaCache, puis sidecar `<id>.json`, sinon placeholders
  → rendu watch.html (immédiat, sans téléchargement)
  → JS : POST /api/prepare?v=<id>
       → JobRegistry.start(id)
          - fichier final déjà présent et valide → état ready
          - job existant queued/downloading → renvoyer l'état
          - job existant error → renvoyer l'erreur (sauf retry=1)
          - sinon créer un job, lancer un thread worker
  → JS : GET /api/status?v=<id> toutes les 1–2 s
       → {state, progress, meta, error}
  → quand state=ready : player.src = /stream?v=<id>
  → Safari émet des requêtes Range ; streaming.py répond 206
```

Le worker :

1. Acquiert le sémaphore (max 2 téléchargements simultanés).
2. Télécharge dans `<cache>/tmp/<id>-<uuid>/` avec yt-dlp.
3. Émet les métadonnées tôt (`--print before_dl:...`) et met à jour la progression
   (`[download] xx.x%`).
4. Remux faststart si nécessaire (`ffmpeg -c copy -movflags +faststart`).
5. Valide le MP4 avec `ffprobe` (h264 profil/level/fps/pix_fmt + AAC-LC).
6. Publie atomiquement vers `<cache>/media/<id>.mp4` via `os.replace`, avec un
   sidecar `<cache>/media/<id>.json` (titre, chaîne, durée, vues, live_status).
7. Passe l'état à `ready`, met à jour MetaCache, déclenche l'éviction.
8. En cas d'échec : état `error`, message utilisateur, nettoyage du dossier tmp.

Les directs et premieres sont refusés avant tout téléchargement long : immédiatement
si `live_status` est déjà en cache, sinon dès la ligne `before_dl` (le worker tue
alors le groupe de processus).

Un redémarrage de l'application perd les jobs en mémoire, mais pas les fichiers
ni les sidecars : `/watch` et `/api/prepare` relisent `<id>.json`, et
`/api/prepare` détecte un fichier final valide et crée un job `ready` sans
retélécharger. Les dossiers tmp orphelins de plus d'1 h sont supprimés au
démarrage.

### 6.3 Reprise, historique, favoris

Tout est côté client, dans `localStorage`, avec des clés préfixées `lazarus.v1.` :

- `lazarus.v1.resume` : objet `{ "<id>": {t, d, ts} }`, max 50 entrées.
- `lazarus.v1.history` : tableau `{id, title, channel, duration, view_count, ts}`,
  max 50, dédupliqué par id, plus récent en tête.
- `lazarus.v1.favorites` : même structure, max 200.
- `lazarus.v1.searches` : tableau de chaînes, max 8, dédupliqué.

Écritures protégées par `try/catch` (mode privé / quota). En cas de quota
dépassé, on supprime l'entrée la plus ancienne et on réessaie une fois.

### 6.4 Bibliothèque

`GET /history` et `GET /favorites` renvoient `library.html` (coquille vide).
`library.js` lit `localStorage`, construit les cartes avec `createElement` /
`textContent` (pas de `innerHTML` avec des données utilisateur), et gère :
suppression d'une entrée, vidage complet avec `confirm()`.

## 7. API HTTP

| Méthode | Route | Rôle | Réponse |
|---|---|---|---|
| GET | `/` | Accueil | HTML |
| GET | `/search?q=&refresh=` | Recherche | HTML |
| GET | `/watch?v=` | Page de lecture | HTML |
| POST | `/api/prepare?v=&retry=&force=` | Démarre/relance un job | JSON, 202 (ou 200 si ready) |
| GET | `/api/status?v=` | Snapshot du job | JSON, 200 |
| GET | `/stream?v=` | MP4 local | 200/206, 400/404/425 |
| GET | `/history` | Coquille historique | HTML |
| GET | `/favorites` | Coquille favoris | HTML |
| GET | `/healthz` | Santé | JSON, 200/503 |
| GET | `/thumb/<id>.jpg?size=mq\|hq` | Miniature proxifiée | image/jpeg |

### Snapshot de job

```json
{
  "id": "y-JqH1M4Ya8",
  "state": "downloading",
  "progress": 42.5,
  "downloaded_bytes": 1234567,
  "total_bytes": 9876543,
  "error": null,
  "meta": {
    "title": "...",
    "channel": "...",
    "duration": 249,
    "view_count": 68318877,
    "live_status": null
  }
}
```

- `state` : `idle | queued | downloading | ready | error`.
- `progress` : `-1` si inconnu (barre indéterminée).
- `error` : message français destiné à l'utilisateur, jamais de stack trace.
- `/api/status` d'un ID inconnu renvoie `200` avec `state="idle"`.
- `/api/prepare` d'un ID invalide renvoie `400` JSON ; `202` si un job est créé
  ou relancé, `200` si l'état est déjà `ready` ou `error`.
- `/stream` sert **tout fichier final validé présent** dans `<cache>/media/`,
  indépendamment de l'état du job (les jobs sont en mémoire et peuvent avoir été
  nettoyés) ; il recrée un job `ready` à la volée si nécessaire. `425` si aucun
  fichier validé n'existe, `404` si le fichier a disparu, `400` si l'ID est
  invalide.
- `force=1` supprime le fichier en cache et relance (refusé si un flux est actif).
- `retry=1` relance uniquement un job en `error`.

### `/stream` et Range

- Supporte `bytes=start-end`, `bytes=start-`, `bytes=-suffix`.
- Un seul range par requête ; les ranges multiples sont servis en `200` complet.
- `start >= size`, `start > end` ou range invalide → `416` avec
  `Content-Range: bytes */<size>`.
- `HEAD` renvoie les en-têtes sans corps.
- En-têtes : `Accept-Ranges: bytes`, `Content-Length`, `Content-Type: video/mp4`,
  `Content-Range` en 206, `Cache-Control: no-store`.
- Lecture par blocs de 64 Kio.
- Le fichier est enregistré dans `StreamRegistry` pendant toute la réponse ; il ne
  peut pas être évincé.

## 8. Machine à états des jobs

```
idle ──prepare──> queued ──slot──> downloading ──ok──> ready
                                      │
                                      └──erreur──> error ──retry──> queued
```

- Un seul job par `video_id` ; un verrou par vidéo évite les doublons.
- `MAX_CONCURRENT_DOWNLOADS` (défaut 2) via `threading.Semaphore`.
- Threads daemon ; aucun contexte Flask dans le worker.
- Timeout global (`DOWNLOAD_TIMEOUT`, défaut 1800 s) appliqué par un
  `threading.Timer` qui tue le groupe de processus (`start_new_session=True` +
  `os.killpg`), pour ne pas laisser ffmpeg orphelin.
- Progression lue sur stdout avec `--newline` ; mise à jour limitée à ~4 Hz.
- Nettoyage des jobs terminés après 1 h (ou quand le registre dépasse 200 entrées)
  pour éviter la croissance mémoire. Cela n'affecte pas `/stream`, qui se base
  sur les fichiers validés et non sur le registre.
- Les jobs sont en mémoire : après redémarrage, l'état est reconstruit à partir
  des fichiers et sidecars présents.
- Directs/premieres : refus immédiat si `live_status` est connu, sinon abandon
  dès la ligne `before_dl` avant le début du téléchargement.
- Si le lecteur échoue sur un fichier pourtant `ready` (fichier corrompu, cache
  évincé), `watch.js` relance `/api/prepare` et restaure `currentTime` après
  `loadedmetadata`.

## 9. Sélection de format et validation

### Sélecteur principal

```
bv*[height<=720][fps<=30][vcodec^=avc1]+ba[ext=m4a]
/b[height<=720][fps<=30][ext=mp4][vcodec^=avc1]
/b[height<=720][fps<=30][ext=mp4]
```

- `--merge-output-format mp4`
- `--postprocessor-args "ffmpeg:-movflags +faststart"`
- Remux final `ffmpeg -y -i <tmp> -c copy -movflags +faststart <final>` pour
  garantir le faststart même quand yt-dlp n'a pas fusionné (format combiné).
- `--no-playlist`
- `--no-warnings`
- `--newline`
- `--retries 3`, `--fragment-retries 3`, `--socket-timeout 15`
- `--js-runtimes node:<chemin>` si `shutil.which("node")` trouve un binaire,
  sinon `node` (le chemin explicite évite l'avertissement « No supported
  JavaScript runtime »).
- `--concurrent-fragments 4` (accélère les téléchargements DASH ; configurable).

### Repli

Si le téléchargement ou la validation échoue, une seule nouvelle tentative avec
`height<=480`, `fps<=30` et le même codec. Si elle échoue aussi, état `error` avec
un message clair (« Format incompatible avec cet appareil »).

### Validation

`ffprobe -v error -show_entries stream=codec_name,codec_type,profile,level,pix_fmt,avg_frame_rate -of json <file>` :

- une piste vidéo `h264`, profil `Baseline`/`Main`/`High`, `level <= 41`,
  `avg_frame_rate <= 30`, `pix_fmt = yuv420p` ;
- une piste audio `aac` (AAC-LC) ;
- durée > 0 et taille > 0.

Un fichier qui ne passe pas est supprimé et jamais publié. Cela empêche de servir
du VP9/AV1 dans un MP4, ou du 720p60 / H.264 High 4.2 que l'A5 ne décode pas de
façon fiable. Le niveau 4.1 est accepté (spec iPad 2), mais on privilégie le
720p30.

### Cas refusés

- Directs (`is_live`) et premieres (`is_upcoming`) : message explicite, pas de
  téléchargement de 30 minutes.
- Vidéos nécessitant une connexion / un contrôle anti-bot : message générique +
  conseil de mise à jour de yt-dlp dans les logs/README.

## 10. Cache et disque

### Arborescence

```
<cache>/
  media/<id>.mp4      # fichiers validés, servis par /stream
  media/<id>.json     # sidecar métadonnées (titre, chaîne, durée, vues, live)
  tmp/<id>-<uuid>/    # téléchargements en cours, supprimés après succès/échec
  thumbs/<id>-mq.jpg  # miniatures 320×180
  thumbs/<id>-hq.jpg  # miniatures 480×360 (poster)
```

### Politique

- `MAX_CACHE_BYTES` : 5 Gio par défaut, configurable.
- `MAX_CACHE_AGE` : 7 jours par défaut.
- Éviction LRU par date de dernière lecture (`os.utime` à chaque `/stream`),
  en sautant les fichiers actifs (`StreamRegistry`). Le sidecar JSON est supprimé
  avec le MP4 ; une méta manquante est relue depuis le disque, ce qui permet à
  l'historique et à la page de lecture de garder leurs titres après redémarrage.
- Éviction déclenchée après chaque téléchargement réussi et au démarrage, jamais
  sur le chemin d'une requête utilisateur.
- Publication atomique : le fichier final n'apparaît qu'une fois complet et
  validé.
- Miniatures : cache disque, TTL 30 jours, limite 200 Mio, négatif cache mémoire
  5 min pour éviter de marteler i.ytimg.com en cas d'échec.
- Vérification de l'espace libre avant un téléchargement : si < 500 Mio, erreur
  « Espace disque insuffisant ».
- Dossier cache non inscriptible : l'application démarre mais `/healthz` renvoie
  503 et les téléchargements échouent avec un message clair.

### Volume Docker

```yaml
volumes:
  - lazarus-cache:/cache
environment:
  - LAZARUS_CACHE_DIR=/cache
```

## 11. Design visuel et ergonomie

### Palette (extraite du logo)

| Rôle | Couleur |
|---|---|
| Fond | `#F4F8F9` |
| Surface / cartes | `#FFFFFF` |
| Marine (titres, header) | `#1B3A5A` |
| Bleu profond (boutons) | `#175071` |
| Bleu (liens) | `#1A6A8D` |
| Turquoise (accent, progression) | `#3EADBA` |
| Corail (favoris) | `#CF6957` |
| Texte secondaire | `#62788A` |
| Bordures | `#DCE6EA` |
| Lecteur | `#0E1A24` |
| Erreur | fond `#FDECEA`, bord `#F2B8B5`, texte `#8A1C17` |

Pas de variables CSS (Safari 9) : les valeurs sont répétées dans `app.css`, avec
un commentaire de palette en tête de fichier.

### Shell commun

- Header blanc, bordure basse, logo à gauche (hauteur 40 px), navigation
  « Accueil / Historique / Favoris » à droite, lien actif souligné en turquoise.
- Largeur max 1000 px, padding 16 px.
- Footer discret avec la mention de compatibilité.
- Même shell sur l'accueil, la lecture et la bibliothèque ; seule la zone vidéo
  est sombre.

### Accueil

```
┌──────────────────────────────────────────────┐
│ [logo] LazarusTube              [Historique] │
│ ┌──────────────────────────────────────────┐ │
│ │ Rechercher…                         [→]  │ │
│ └──────────────────────────────────────────┘ │
│ Colle un lien YouTube ou cherche des mots…   │
│ Récents : jazz · documentaire · …            │
│ ┌───────────────┐ ┌───────────────┐          │
│ │   miniature   │ │   miniature   │          │
│ │         12:34 │ │          8:02 │          │
│ │ Titre sur 2 l.│ │ Titre sur 2 l.│          │
│ │ Chaîne · 1 M  │ │ Chaîne · 45 k │          │
│ └───────────────┘ └───────────────┘          │
└──────────────────────────────────────────────┘
```

- Grille 2 colonnes ≥ 700 px, 1 colonne en dessous.
- Carte : miniature 16:9 (source 320×180, largeur 100 %, hauteur auto), badge de
  durée en bas à droite, titre sur 2 lignes (`-webkit-line-clamp`), chaîne +
  vues. Si la miniature échoue : bloc marine avec triangle « play » en CSS.
- Badge « Direct » pour les lives.
- État initial : message d'aide + recherches récentes.
- Résultats : « Résultats pour « q » », nombre, lien « Actualiser ».
- Aucun résultat : message + suggestion.
- Recherche en cours : bouton « Recherche… », spinner CSS, soumission unique.

### Lecture

```
← Retour
┌──────────────────────────────────────────────┐
│                                              │
│              vidéo 16:9                      │
│         (poster + overlay préparation)       │
│                                              │
└──────────────────────────────────────────────┘
Titre de la vidéo
Chaîne · 1,2 M vues · 12:34
[♡ Favori] [−10 s] [+10 s] [Plein écran]
[Ouvrir sur YouTube]
Reprendre à 12:34 ? [Reprendre] [Recommencer]
```

- Poster = miniature HQ proxifiée.
- Overlay de préparation : barre de progression + pourcentage + « Préparation de
  la vidéo… ». En erreur : message + « Réessayer ».
- Une fois prêt : overlay masqué, `src` affecté, lecteur natif utilisable.
- Pas d'autoplay (iOS l'interdit sans geste).
- Boutons ±10 s, plein écran (`webkitEnterFullscreen`), favori.
- Reprise proposée explicitement, pas de seek automatique surprise.
- Lien « Ouvrir sur YouTube » en secours.
- `aria-live="polite"` sur la zone de statut.

### Bibliothèque

- `/history` et `/favorites` : même grille de cartes, avec bouton de suppression.
- État vide : « Aucune vidéo pour le moment » + lien vers l'accueil.
- Bouton « Vider » avec confirmation.

### Accessibilité

- `label` (même visuellement masqué) pour le champ de recherche.
- Contraste texte/fond conforme.
- Focus visible (`outline` turquoise).
- Cibles ≥ 44 px.
- `alt=""` sur les miniatures (le titre est juste à côté).
- Retrait de `user-scalable=no` pour permettre le zoom.

### Assets

- Générer depuis `logoLazarusTube.png` :
  - `static/img/logo.png` (≈ 352×192, affiché 176×96 max) ;
  - `static/img/apple-touch-icon.png` (152×152, logo centré sur fond clair) ;
  - `static/img/favicon.png` (32×32).
- Garder la source à la racine ; exclure la source de l'image Docker via
  `.dockerignore`.
- Meta iOS : `apple-mobile-web-app-capable`, `apple-mobile-web-app-title`,
  `apple-mobile-web-app-status-bar-style`, `apple-touch-icon`.

## 12. Fonctionnalités P2 (détail)

### Reprise de lecture

- Sauvegarde sur `timeupdate`, au plus toutes les 5 s, si `currentTime > 5` et
  `< duration - 10`.
- À `loadedmetadata`, si une position existe : afficher la barre « Reprendre à
  mm:ss ? ». « Reprendre » fait `currentTime = t` ; « Recommencer » supprime
  l'entrée.
- Suppression à `ended`.

### Historique

- Ajout à l'événement `play` (pas à la simple ouverture), avec les métadonnées
  connues (titre, chaîne, durée, vues), lues depuis `/api/status` ou le sidecar.
- Déduplication par id, plus récent en tête, max 50.

### Favoris

- Bouton sur la page de lecture, état lu depuis `localStorage`.
- Bibliothèque dédiée, suppression individuelle.

### Recherches récentes

- Ajout à la soumission d'une recherche (et après collage d'URL).
- Chips cliquables sur l'accueil, max 8.

### Collage d'URL

- Côté serveur : `youtu.be/<id>`, `youtube.com/watch?v=<id>`, `/shorts/<id>`,
  `/embed/<id>`, `/live/<id>`, `/v/<id>`, `music.youtube.com`, `m.youtube.com`,
  `youtube-nocookie.com`, ID brut de 11 caractères.
- Redirection vers `/watch?v=<id>` ; `list`/`t` ignorés.
- Une URL non YouTube reste une recherche textuelle.

## 13. Gestion d'erreurs et observabilité

- Messages utilisateur en français, sans détail technique.
- Logs structurés (`logging`) : démarrage, recherche (cache hit/miss, durée,
  nombre de résultats), job (début, fin, taille, durée, erreur), flux (range,
  statut), miniature (échec).
- `/healthz` vérifie : yt-dlp, ffmpeg, ffprobe, node, cache inscriptible.
- Erreurs HTML stylées (400/404/500) ; erreurs API en JSON.
- Erreurs yt-dlp tronquées à 500 caractères dans le log, jamais renvoyées brutes.
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`.
- `Cache-Control` : `no-cache` pour le HTML, `public, max-age=604800` pour les
  assets statiques (avec `?v=<asset_version>`), `no-store` pour l'API et le flux.

## 14. Sécurité et robustesse

- Validation stricte des IDs ; aucune URL arbitraire passée à yt-dlp.
- `subprocess` avec liste d'arguments, jamais de shell.
- Longueur de requête limitée à 200 caractères ; nombre de résultats limité.
- Proxy de miniatures limité à `i.ytimg.com`, ID validé, taille max 200 Kio,
  content-type `image/*` vérifié.
- Pas de traversée de répertoire : noms de fichiers dérivés d'IDs validés.
- Téléchargements concurrents plafonnés ; jobs et méta-caches bornés.
- Nettoyage des processus enfants (groupe de processus) en cas de timeout.
- Cache non inscriptible / disque plein : erreurs explicites, pas de crash.

## 15. Tests

### Unitaires

- `ids` : IDs valides/invalides, toutes les formes d'URL, URL non YouTube.
- `formats` : sélecteur contient `height<=720`, `fps<=30` et `avc1` ; validation
  ffprobe (profil, level, fps, pix_fmt, AAC-LC) avec un faux exécutable ou
  monkeypatch.
- `streaming` : range normal, ouvert, suffixe, invalide, au-delà de la taille,
  `HEAD`.
- `cache` : publication atomique MP4 + sidecar, éviction LRU, âge, fichier actif
  conservé, quota de miniatures, relecture de la méta depuis le disque.
- `jobs` : transitions idle→queued→downloading→ready, erreur, retry, force,
  limite de concurrence, timeout (avec un faux downloader), abandon d'un direct
  sur `before_dl`, snapshot JSON.
- `SearchCache` : TTL, rafraîchissement, taille max.
- `test_js_es5` : les fichiers `static/js/*.js` ne contiennent pas `=>`, `const `,
  `let `, `async `, `await `, backticks, `fetch(`.

### Routes (Flask test client, sans réseau)

- `/` rend le formulaire.
- `/search` avec un faux `YtDlp` : résultats, miniatures dérivées, cache,
  `refresh=1`, erreur.
- `/search?q=<url>` redirige vers `/watch`.
- `/watch` : ID invalide → 400 ; méta depuis le cache.
- `/api/prepare` / `/api/status` : idle, queued, downloading, ready, error,
  retry, force, ID invalide.
- `/stream` : fichier valide → 200/206 même sans job en mémoire, pas de fichier
  → 425, ID invalide → 400, fichier disparu → 404.
- `/watch` après redémarrage : le titre vient du sidecar, pas d'un placeholder.
- `/thumb/<id>.jpg` : cache hit, fetch simulé, échec → placeholder.
- `/healthz`.
- Pages d'erreur.

### Manuels (iPad 2 / Safari 9)

Recherche, miniatures, lecture, seek, pause/reprise, reprise de position,
historique, favoris, URL collée, ID invalide, erreur de téléchargement + retry,
vidéo longue, 720p, cache vidé, redémarrage du conteneur, mode privé (localStorage
indisponible).

### Dépendances

- `requirements-dev.txt` : `pytest`.
- Pas de réseau dans les tests ; pas de vrais téléchargements.

## 16. Ordre d'implémentation

1. **Socle** : `config`, `ids`, `formats`, `streaming`, `cache` + tests unitaires.
2. **P0 lecture** : `jobs`, `ytdlp`, API `/api/prepare` + `/api/status`, `/stream`
   gaté, page watch + JS de préparation/progression/retry + tests.
3. **P1 accueil** : `base.html`, `app.css`, refonte index, miniatures proxifiées,
   méta (chaîne/vues), cache de recherche, état de chargement + tests.
4. **P1 lecture** : refonte watch, poster, boutons ±10 s, plein écran, favoris,
   reprise + tests.
5. **P2** : historique, favoris, bibliothèque, recherches récentes, collage d'URL
   + tests.
6. **Finitions** : assets logo/favicon/touch icon, Docker (volume, healthcheck,
   waitress), README, `.dockerignore`, test manuel iPad.

Chaque étape est livrable ; P0 peut être déployé avant le relooking.

## 17. Docker et exploitation

- `requirements.txt` : `flask`, `requests`, `waitress`, `yt-dlp` (non épinglé).
- `requirements-dev.txt` : `pytest`.
- `Dockerfile` : identique + `waitress` ; CMD
  `waitress-serve --listen=0.0.0.0:3616 --threads=16 --call app:create_app`.
  `python app.py` reste disponible pour le développement local.
- `docker-compose.yml` : volume nommé `lazarus-cache:/cache`, variables
  `LAZARUS_CACHE_DIR`, `LAZARUS_MAX_CACHE_BYTES`,
  `LAZARUS_MAX_CONCURRENT_DOWNLOADS`, healthcheck sur `/healthz`.
- `.dockerignore` : `.git`, `__pycache__`, `*.pyc`, `.pytest_cache`, `tests`,
  `docs`, `logoLazarusTube.png`, `.DS_Store`.
- `waitress` évite le serveur de développement Flask et gère les réponses
  streaming. `--threads=16` : Safari peut ouvrir plusieurs connexions Range pour
  une même vidéo ; on vise un iPad principal et jusqu'à 3 lectures simultanées.
  Au-delà, il faudra un serveur asynchrone (hors scope).

### Variables d'environnement

| Variable | Défaut |
|---|---|
| `LAZARUS_CACHE_DIR` | `/tmp/lazarus_cache` |
| `LAZARUS_MAX_CACHE_BYTES` | `5368709120` (5 Gio) |
| `LAZARUS_MAX_CACHE_AGE` | `604800` (7 j) |
| `LAZARUS_MAX_CONCURRENT_DOWNLOADS` | `2` |
| `LAZARUS_SEARCH_TTL` | `600` |
| `LAZARUS_SEARCH_LIMIT` | `10` |
| `LAZARUS_MAX_HEIGHT` | `720` |
| `LAZARUS_REQUEST_TIMEOUT` | `30` |
| `LAZARUS_DOWNLOAD_TIMEOUT` | `1800` |
| `LAZARUS_LOG_LEVEL` | `INFO` |
| `LAZARUS_YTDLP_BIN` | `yt-dlp` |
| `LAZARUS_FFMPEG_BIN` | `ffmpeg` |
| `LAZARUS_FFPROBE_BIN` | `ffprobe` |
| `LAZARUS_NODE_BIN` | auto (`shutil.which`) |
| `LAZARUS_THUMB_CACHE_BYTES` | `209715200` (200 Mio) |
| `LAZARUS_MAX_QUERY_LENGTH` | `200` |

## 18. Critères d'acceptation

1. Ouvrir une vidéo longue affiche la page de lecture en < 1 s, avec titre et
   progression ; aucun appel HTTP ne reste bloqué plus de 2 s.
2. `/stream` répond en < 100 ms quand le fichier est prêt et ne télécharge jamais.
3. Une vidéo disponible seulement en 1080p/VP9/720p60 affiche soit une lecture
   720p30 H.264 + AAC-LC fluide, soit une erreur claire — jamais un écran noir
   silencieux.
4. La recherche affiche des miniatures et des métadonnées en 2 colonnes à
   1024×768, sans défilement horizontal.
5. Une recherche répétée est servie depuis le cache en < 200 ms ; l'état de
   chargement est visible.
6. La reprise de lecture fonctionne après rechargement ; historique et favoris
   persistent ; coller une URL YouTube ouvre la lecture.
7. Toutes les pages sont utilisables au doigt (cibles ≥ 44 px) et au clavier.
8. `pytest` passe.
9. `docker compose up` fonctionne ; le cache, les titres et les métadonnées
   survivent à un redémarrage.
10. Aucune syntaxe JS non supportée par Safari 9 (vérifiée par test).

## 19. Risques et mitigations

| Risque | Mitigation |
|---|---|
| yt-dlp casse après une mise à jour YouTube | Non épinglé + logs + README de mise à jour ; validation de format |
| Contrôle anti-bot YouTube | Message clair ; cookies hors scope ; mise à jour yt-dlp |
| Format non décodable par l'A5 | Sélecteur avc1/720p + validation ffprobe + repli 480p |
| Téléchargement très long | Progression, timeout 30 min, retry, threads séparés |
| Safari 9 et Range | Parser testé (suffixe, ouvert, invalide), HEAD |
| Cache qui remplit le disque | Quota 5 Gio + LRU + âge 7 j |
| Suppression pendant lecture | `StreamRegistry` + éviction hors requête |
| localStorage vidé / privé | Dégradation silencieuse, pas de crash |
| Perte des jobs au redémarrage | Reconstruction depuis les fichiers validés |
| Mémoire du serveur | Jobs et caches bornés, threads daemon |

## 20. Décisions prises (appel du builder)

- **Waitress** plutôt que le serveur Flask en production.
- **Proxy de miniatures** côté serveur avec cache disque (évite i.ytimg.com sur
  l'iPad, réutilise `requests`, accélère).
- **Shell clair + lecteur sombre** (cohérence, lisibilité en extérieur).
- **Bibliothèque en pages dédiées** (`/history`, `/favorites`) plutôt qu'un panneau
  sur l'accueil.
- **Pas d'autoplay** ; reprise proposée explicitement.
- **Repli 480p** après échec du 720p.
- **Cache 5 Gio / 7 jours** par défaut, configurable.
- **Suppression de `/check`** au profit de `/api/prepare` + `/api/status` (aucun
  client externe connu).
- **Retrait de `user-scalable=no`**.
- **`--print before_dl:` + `--no-simulate --progress`** pour les métadonnées
  précoces (vérifié avec yt-dlp 2026.08.19).
- **Chemin node explicite** dans `--js-runtimes` (vérifié : sans chemin, yt-dlp
  émet un avertissement et peut ignorer le runtime).
- **Sidecar JSON** `<cache>/media/<id>.json` : les métadonnées survivent au TTL
  mémoire et aux redémarrages, sans re-probe yt-dlp.
- **`/stream` découplé du registre de jobs** : tout fichier validé est servi,
  même si le job a été nettoyé ou si l'application a redémarré.
- **Validation codec étendue** : H.264 Baseline/Main/High, level ≤ 4.1, ≤ 30 fps,
  `yuv420p`, AAC-LC — pas seulement « h264 + aac ».
- **Refus des directs/premieres** dès `before_dl`, avant le début du
  téléchargement, pour tenir la promesse « pas de téléchargement de 30 min ».
- **Cible de concurrence** : 3 appareils maximum en lecture simultanée,
  16 threads waitress. Au-delà, serveur asynchrone hors scope.

## 21. Ce qui reste à décider par le builder

- Forme exacte du logo dans le header (le logo source contient probablement le
  nom ; ne pas le dupliquer) et cadrage de l'icône d'écran d'accueil.
- Détail du template de progression (`--progress-template` vs regex sur
  `[download]`) — la regex est suffisante et stable.
- Faut-il exposer la position dans la file (`queue_position`) — optionnel.
- Faut-il ajouter un bouton « Actualiser » sur la page de lecture — optionnel.
- Faut-il conserver un alias `/check` pour compatibilité — non nécessaire, mais
  sans coût.
