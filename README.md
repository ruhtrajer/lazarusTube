# lazarusTube

![Logo lazarusTube](logoLazarusTube.png)

Application web légère pour **rechercher et lire des vidéos YouTube** sur un matériel ancien, spécialement un **iPad 2 sous iOS 9 (Safari 9)**.

## Fonctionnalités

- Recherche de vidéos via `yt-dlp` (`ytsearch10`).
- Lecture fiable sans coupure : la vidéo est d'abord téléchargée (et fusionnée vidéo+audio via `ffmpeg` si besoin) en un MP4 local, puis diffusée avec support des en-têtes `Range` (`206 Partial Content`) pour le déplacement/seeking sur Safari iOS 9. Le MP4 est optimisé (`faststart`) pour une lecture progressive.
- Le téléchargement est déclenché en arrière-plan dès l'ouverture de la page, afin de limiter l'attente avant lecture.
- Interface en **JavaScript strictement ES5** (pas de `const`, `let`, fléchées, `fetch`, `async`/`await`) compatible WebKit iOS 9.
- Conteneur Docker écoutant en **HTTP sur le port 3616** (pas de HTTPS, pour éviter les erreurs de certificats sur iOS 9).

## Stack

- Python 3.11 (`python:3.11-slim`)
- Flask
- yt-dlp (version récente, **non épinglée** car YouTube évolue constamment)
- `ffmpeg` + `nodejs` (runtime JavaScript requis par yt-dlp pour décoder les signatures YouTube)
- Docker / docker-compose

## Démarrage

```bash
docker compose build
docker compose up
```

Puis ouvre `http://<ip-du-conteneur>:3616` depuis Safari sur l'iPad 2.

## Structure

| Fichier | Rôle |
|---------|------|
| `app.py` | Backend Flask (routes `/`, `/search`, `/watch`, `/stream`) |
| `templates/index.html` | Page d'accueil + résultats de recherche (ES5) |
| `templates/watch.html` | Lecteur vidéo HTML5 + gestion d'erreurs (ES5) |
| `Dockerfile` | Image `python:3.11-slim` + ffmpeg + nodejs (runtime JS yt-dlp) |
| `docker-compose.yml` | Service mappé sur le port `3616` |
| `requirements.txt` | Dépendances Python |

## Routes

- `GET /` : accueil avec formulaire de recherche.
- `GET /search?q=...` : 10 premiers résultats (`id`, titre, durée, miniature).
- `GET /watch?v=...` : page de lecture.
- `GET /check?v=...` : déclenche le téléchargement de la vidéo en arrière-plan (préparation de la lecture) ; les erreurs sont remontées par le lecteur côté client.
- `GET /stream?v=...` : diffuse le MP4 local de la vidéo (téléchargé/fusionné au préalable) avec support `Range` / `206` pour le seek.

## Notes de compatibilité

- Le lecteur utilise une balise `<video controls width="100%" src="/stream?v=...">` classique.
- Design fluide optimisé pour une résolution de `1024x768`.
- Aucune fonctionnalité moderne du navigateur n'est utilisée côté client.
