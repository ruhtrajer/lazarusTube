# Checklist de vérification manuelle — iPad 2 / iOS 9 (Safari 9)

Environnement : `python3 app.py`, `http://127.0.0.1:3616`, cache vidé entre les séries si besoin.
Résultat : cochez ✅ ou ❌, complétez la colonne « Résultat ».

## 1. Accueil et recherche

| # | Cas de test | Résultat attendu | Résultat |
|---|-------------|------------------|----------|
| 1.1 | Ouvrir `http://<ip>:3616/` | Page s'affiche immédiatement, formulaire présent, pas de zoom forcé | |
| 1.2 | Rechercher un mot-clé (ex. « jazz ») | Résultats s'affichent en 2 colonnes à 1024 px, 1 colonne sous 700 px | |
| 1.3 | Chaque résultat affiche miniature, titre, chaîne, durée, vues | Données présentes, texte français | |
| 1.4 | Cliquer sur une miniature | Ouverture de `/watch?v=<id>` | |
| 1.5 | Coller une URL YouTube (`youtu.be/...`) dans la recherche | Redirection vers la page de lecture de cette vidéo | |
| 1.6 | Recherche vide | Message « Veuillez saisir un terme de recherche. » | |
| 1.7 | Recherche sans résultat | « Aucun résultat pour … » | |
| 1.8 | Recherche en erreur (simuler) | Message en français + lien « Réessayer » | |
| 1.9 | Champ de recherche focus au clavier | Anneau de focus visible | |

## 2. Miniatures

| # | Cas de test | Résultat attendu | Résultat |
|---|-------------|------------------|----------|
| 2.1 | Miniature d'une vidéo connue (`mq`) | Image s'affiche | |
| 2.2 | Miniature d'une vidéo inexistante | 404, pas de blocage de la page, placeholder CSS visible | |
| 2.3 | Recharger plusieurs fois une même miniature | Pas de martelage réseau (cache disque) | |

## 3. Lecture

| # | Cas de test | Résultat attendu | Résultat |
|---|-------------|------------------|----------|
| 3.1 | Ouvrir `/watch?v=<id>` sur une vidéo non mise en cache | Page immédiate, overlay « Préparation de la vidéo », barre de progression qui avance | |
| 3.2 | Attendre la fin du préparation | Lecteur disponible, `playsinline` + `webkit-playsinline`, pas d'autoplay | |
| 3.3 | Lire la vidéo | Lecture fluide, pas de coupure, seeking fonctionnel (206 Range) | |
| 3.4 | Pause puis reprise | Reprise à la bonne position | |
| 3.5 | Recharger la page pendant la lecture | Reprise proposée à la position sauvegardée (si > 5 s et < durée − 10 s) | |
| 3.6 | Redémarrer le serveur, puis rouvrir une vidéo déjà en cache | Reprise depuis le sidecar, pas de re-téléchargement | |
| 3.7 | Vidéo disponible uniquement en 720p60 ou VP9 | Fallback 480p, puis message clair « Format incompatible avec cet appareil » si échec (jamais écran noir) | |
| 3.8 | Lien YouTube « Ouvrir sur YouTube » | Ouvre `https://www.youtube.com/watch?v=<id>` dans un nouvel onglet | |
| 3.9 | Boutons ±10 s | Déplace la lecture de 10 s, clampé aux bornes | |
| 3.10 | Bouton plein écran | `webkitEnterFullscreen` / `requestFullscreen` fonctionne | |

## 4. Erreurs et reprise

| # | Cas de test | Résultat attendu | Résultat |
|---|-------------|------------------|----------|
| 4.1 | URL d'un direct / première | Erreur claire avant tout téléchargement long (« Les directs ne sont pas disponibles. ») | |
| 4.2 | ID vidéo invalide (`abc`) | 400 sur `/watch`, `/api/prepare`, `/api/status`, `/stream` | |
| 4.3 | Téléchargement coupé (réseau retiré) | Message d'erreur + bouton « Réessayer » | |
| 4.4 | Cliquer « Réessayer » après échec | Nouveau préparé avec `retry=1` | |
| 4.5 | Vidéo en cours de lecture sur un autre appareil | `409` si `force=1` (« Cette vidéo est en cours de lecture ») | |

## 5. Bibliothèque (historique / favoris)

| # | Cas de test | Résultat attendu | Résultat |
|---|-------------|------------------|----------|
| 5.1 | Lire deux vidéos différentes | `/history` affiche deux cartes, plus récente en tête | |
| 5.2 | Cliquer « Retirer » sur une carte | Carte retirée, mise à jour immédiate | |
| 5.3 | Cliquer « Vider » (+ confirmation) | Historique vidé, état vide affiché | |
| 5.4 | Marquer une vidéo en favori (♡) | Apparaît dans `/favorites` | |
| 5.5 | Retirer un favori | Disparaît de `/favorites` | |
| 5.6 | Naviguer entre Accueil / Historique / Favoris | Lien actif souligné, pas de 404 | |

## 6. URL collée et ID invalide

| # | Cas de test | Résultat attendu | Résultat |
|---|-------------|------------------|----------|
| 6.1 | `/watch?v=abc` | 400 | |
| 6.2 | `/stream?v=abc` | 400 | |
| 6.3 | `/api/prepare?v=abc` | 400 JSON | |
| 6.4 | `/api/status?v=abc` | 400 JSON | |
| 6.5 | `/thumb/abc.jpg` | 404 | |
| 6.6 | `/check?v=...` | 404 (route supprimée) | |

## 7. Vidéo longue et cache

| # | Cas de test | Résultat attendu | Résultat |
|---|-------------|------------------|----------|
| 7.1 | Vidéo longue (> 10 min) | Préparation en arrière-plan, progression visible, lecture sans coupure | |
| 7.2 | Vider le cache média | Re-téléchargement nécessaire à la prochaine lecture | |
| 7.3 | Redémarrage du conteneur | Vidéo déjà en cache réutilisée (sidecar conservé) | |

## 8. Mode privé (Safari)

| # | Cas de test | Résultat attendu | Résultat |
|---|-------------|------------------|----------|
| 8.1 | Ouvrir l'app en navigation privée | Aucune erreur visible, recherche et lecture fonctionnent | |
| 8.2 | Reprise / favoris / historique en privé | Pas de persistance (localStorage indisponible), pas de crash | |

## Critère d'acceptation

Tous les items ci-dessus sont cochés ✅ sur un véritable iPad 2 (iOS 9) ou, à défaut, reproduits de façon équivalente sur Safari 9 / WebKit ancien.
