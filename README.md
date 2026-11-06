# lazarusTube

Application web légère pour **rechercher et lire des vidéos YouTube** sur un matériel ancien, spécialement un **iPad 2 sous iOS 9 (Safari 9)**.

## Cible et compatibilité

- **Appareil cible** : iPad 2, écran 1024×768, iOS 9 / Safari 9 (contrainte stricte).
- **JavaScript** : ES5 uniquement (pas de `const`, `let`, flèches, templates littéraux, `fetch`, `async`/`await`, classes).
- **CSS** : pas de Grid, variables CSS, `position: sticky`, `gap`, `aspect-ratio`, `clamp()`, `:focus-visible`. Flex préfixé `-webkit-` et `inline-block`.
- **Vidéo** : H.264 `avc1` + AAC `m4a`, ≤ 720p, ≤ 30 fps, level ≤ 4.1, `yuv420p`, AAC-LC. `playsinline` + `webkit-playsinline`. Pas d'autoplay.
- **Réseau** : HTTP simple sur le port **3616**, pas de TLS (évite les erreurs de certificat sur iOS 9).
- **Concurrence** : 3 appareils maximum en lecture simultanée ; 2 téléchargements simultanés.

## Fonctionnalités

- Recherche de vidéos via `yt-dlp` (`ytsearch10`), avec cache mémoire des résultats.
- Lecture fiable sans coupure : la vidéo est préparée (téléchargement + validation codec `ffprobe`) en un MP4 local optimisé (`faststart`), puis diffusée avec support des en-têtes `Range` (`206 Partial Content`) pour le déplacement/seeking sur Safari iOS 9.
- Reprise de lecture : position sauvegardée, reprise proposée après rechargement ou redémarrage.
- Historique et favoris côté navigateur (`localStorage`), jusqu'à 50 entrées d'historique et 200 favoris.
- Recherches récentes, page de lecture complète (titre, chaîne, durée, vues), miniatures YouTube avec cache disque et cache négatif.
- Refus explicite des directs et premières, fallback 480p si le format 720p n'est pas décodable par l'iPad 2.
- Messages utilisateur en français ; jamais de stack trace ni de sortie `yt-dlp` brute côté client.

## Stack

- Python 3.11 (`python:3.11-slim`), Flask 3, waitress (`--threads=16`)
- yt-dlp (version récente, **non épinglée** car YouTube évolue constamment)
- `ffmpeg` + `ffprobe` + `nodejs` (runtime JavaScript requis par yt-dlp pour décoder les signatures YouTube)
- Docker / docker-compose

## Démarrage local

```bash
python3 app.py
```

Puis ouvrez `http://127.0.0.1:3616/` depuis le navigateur. Le serveur écoute sur le port 3616.

Les variables d'environnement suivantes sont supportées (préfixe `LAZARUS_`) :

| Variable | Défaut | Rôle |
|----------|--------|------|
| `LAZARUS_CACHE_DIR` | `<tmp>/lazarus_cache` | dossier du cache média |
| `LAZARUS_MAX_CACHE_BYTES` | 5368709120 (5 Gio) | taille max du cache |
| `LAZARUS_MAX_CACHE_AGE` | 604800 (7 jours) | âge max d'un fichier mis en cache |
| `LAZARUS_MAX_CONCURRENT_DOWNLOADS` | 2 | téléchargements simultanés |
| `LAZARUS_SEARCH_TTL` | 600 | durée de vie cache recherche (s) |
| `LAZARUS_SEARCH_LIMIT` | 10 | nombre de résultats par recherche |
| `LAZARUS_MAX_HEIGHT` | 720 | hauteur max (px) |
| `LAZARUS_REQUEST_TIMEOUT` | 30 | timeout recherche (s) |
| `LAZARUS_DOWNLOAD_TIMEOUT` | 1800 | timeout téléchargement (s) |
| `LAZARUS_LOG_LEVEL` | INFO | niveau de log |
| `LAZARUS_YTDLP_BIN` | `yt-dlp` | chemin binaire yt-dlp |
| `LAZARUS_FFMPEG_BIN` | `ffmpeg` | chemin binaire ffmpeg |
| `LAZARUS_FFPROBE_BIN` | `ffprobe` | chemin binaire ffprobe |
| `LAZARUS_NODE_BIN` | `node` (résolu via PATH) | runtime JS yt-dlp |
| `LAZARUS_THUMB_CACHE_BYTES` | 209715200 (200 Mio) | taille max cache miniatures |
| `LAZARUS_MAX_QUERY_LENGTH` | 200 | longueur max d'une requête |

## Docker

```bash
docker compose build
docker compose up -d
```

Puis ouvrez `http://<ip-du-conteneur>:3616`. Le cache média est persistant via le volume nommé `lazarus-cache` monté sur `/cache`. Un healthcheck interroge `/healthz` toutes les 30 secondes.

Arrêt :

```bash
docker compose down
```

## Architecture des modules

| Fichier | Rôle |
|---------|------|
| `app.py` | `create_app()` factory, routes, filtres Jinja, gestion d'erreurs |
| `config.py` | `Config` figée + `load_config()` (lecture des variables d'environnement) |
| `ids.py` | validation et extraction des identifiants YouTube |
| `formats.py` | sélecteur de format 720p30/480p + validation `ffprobe` |
| `streaming.py` | réponses HTTP `200`/`206`/`416` compatibles Safari 9 |
| `cache.py` | `MediaCache` (publication atomique MP4 + sidecar), `StreamRegistry`, `SearchCache`, `MetaCache`, `ThumbCache` |
| `ytdlp.py` | wrapper `yt-dlp` : recherche, métadonnées précoces (`before_dl`), timeout, refus des directs |
| `jobs.py` | registre de jobs, progression, fallback 480p, reprise après redémarrage |
| `templates/` | `base.html`, `index.html`, `watch.html`, `library.html`, erreurs 400/404/500 |
| `static/css/app.css` | design system compatible Safari 9 |
| `static/js/app.js`, `search.js`, `watch.js`, `library.js` | logique client ES5 sans build |

## Tests

```bash
pip install pytest
pytest -q
```

Aucun réseau ni vrai téléchargement n'est utilisé en test.

## Dépannage yt-dlp

- Si la recherche ou le téléchargement échoue, mettez à jour yt-dlp : `pip install -U yt-dlp`.
- Si YouTube refuse les signatures, vérifiez que `node` est installé et accessible (`LAZARUS_NODE_BIN` sinon).
- En cas d'erreur anti-bot (HTTP 429 / "Sign in to confirm you're not a bot"), réessayez plus tard ; il n'y a pas de gestion de compte.

## Limites connues

- 3 appareils maximum en lecture simultanée (2 téléchargements simultanés).
- Pas de HTTPS, pas d'autoplay, pas d'audio seul, pas de sous-titres, pas de file d'attente, pas de comptes.
- Les images `static/img/` sont cassées entre la construction du shell (tâche 9) et la génération des assets (cette tâche) si le dépôt est à un état intermédiaire.
