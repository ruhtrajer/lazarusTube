"""Cache média sur disque et caches mémoire de LazarusTube."""

import json
import os
import shutil
import tempfile
import threading
import time
from collections import OrderedDict


class StreamRegistry:
    """Compte les lectures en cours pour protéger les fichiers actifs.

    Chaque chemin peut être lu plusieurs fois en parallèle : le compteur est
    incrémenté par :meth:`begin` et décrémenté par :meth:`end`, sans jamais
    descendre sous zéro.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}

    def begin(self, path: str) -> None:
        """Marque *path* comme en cours de lecture."""
        with self._lock:
            self._counts[path] = self._counts.get(path, 0) + 1

    def end(self, path: str) -> None:
        """Termine une lecture de *path* (idempotent sous zéro)."""
        with self._lock:
            count = self._counts.get(path, 0)
            if count <= 1:
                self._counts.pop(path, None)
            else:
                self._counts[path] = count - 1

    def is_active(self, path: str) -> bool:
        """Indique si *path* est actuellement en cours de lecture."""
        with self._lock:
            return self._counts.get(path, 0) > 0


class MediaCache:
    """Cache disque des vidéos MP4 et de leurs métadonnées.

    Le fichier ``<root>/media/<video_id>.mp4`` est publié atomiquement, puis
    son sidecar ``<root>/media/<video_id>.json``. Les téléchargements en cours
    vivent dans ``<root>/tmp``.
    """

    def __init__(
        self,
        root: str,
        max_bytes: int,
        max_age: int,
        registry: StreamRegistry,
    ) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.max_age = max_age
        self.registry = registry
        self._media_dir = os.path.join(root, "media")
        self._tmp_dir = os.path.join(root, "tmp")

    def ensure_dirs(self) -> None:
        """Crée les dossiers ``media/`` et ``tmp/`` si nécessaire."""
        os.makedirs(self._media_dir, exist_ok=True)
        os.makedirs(self._tmp_dir, exist_ok=True)

    def media_path(self, video_id: str) -> str:
        """Chemin du MP4 final pour *video_id*."""
        return os.path.join(self._media_dir, video_id + ".mp4")

    def meta_path(self, video_id: str) -> str:
        """Chemin du sidecar JSON pour *video_id*."""
        return os.path.join(self._media_dir, video_id + ".json")

    def has(self, video_id: str) -> bool:
        """Indique si le MP4 existe et n'est pas vide."""
        path = self.media_path(video_id)
        try:
            return os.path.isfile(path) and os.path.getsize(path) > 0
        except OSError:
            return False

    def publish(self, video_id: str, tmp_path: str, meta: dict) -> str:
        """Publie *tmp_path* comme MP4 final puis écrit le sidecar.

        Le MP4 est déplacé atomiquement avec :func:`os.replace`. Le sidecar est
        d'abord écrit dans un fichier temporaire du même dossier, puis publié
        de la même façon : un lecteur ne voit jamais un JSON partiel.
        """
        self.ensure_dirs()
        final_path = self.media_path(video_id)
        os.replace(tmp_path, final_path)
        os.utime(final_path)

        payload = dict(meta or {})
        payload["cached_at"] = time.time()

        fd, sidecar_tmp = tempfile.mkstemp(
            dir=self._media_dir,
            prefix="." + video_id + "-",
            suffix=".json.tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(sidecar_tmp, self.meta_path(video_id))
        except BaseException:
            try:
                os.remove(sidecar_tmp)
            except OSError:
                pass
            raise

        return final_path

    def read_meta(self, video_id: str) -> dict | None:
        """Lit le sidecar de *video_id*, ou ``None`` s'il est absent/invalide."""
        try:
            with open(self.meta_path(video_id), encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def touch(self, video_id: str) -> None:
        """Rafraîchit la date de modification du MP4 (best-effort)."""
        try:
            os.utime(self.media_path(video_id))
        except OSError:
            pass

    def delete(self, video_id: str) -> bool:
        """Supprime le MP4 et son sidecar, sauf si le MP4 est en lecture."""
        path = self.media_path(video_id)
        if self.registry.is_active(path):
            return False
        return self._remove_files(path)

    def evict(self) -> None:
        """Évince les fichiers trop anciens ou au-delà du budget disque.

        Les fichiers sont examinés du plus ancien au plus récent. Un fichier
        en cours de lecture est toujours conservé, mais sa taille reste
        comptée dans le total puisqu'il occupe le disque.
        """
        now = time.time()
        try:
            names = os.listdir(self._media_dir)
        except OSError:
            return

        entries: list[tuple[float, str, int]] = []
        total = 0
        for name in names:
            if not name.endswith(".mp4"):
                continue
            path = os.path.join(self._media_dir, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            entries.append((stat.st_mtime, path, stat.st_size))
            total += stat.st_size

        entries.sort(key=lambda entry: entry[0])
        for mtime, path, size in entries:
            too_big = total > self.max_bytes
            too_old = now - mtime > self.max_age
            if not too_big and not too_old:
                continue
            if self.registry.is_active(path):
                continue
            if self._remove_files(path):
                total -= size

    def clean_tmp(self, max_age: int = 3600) -> None:
        """Supprime les entrées de ``tmp/`` plus anciennes que *max_age*."""
        now = time.time()
        try:
            names = os.listdir(self._tmp_dir)
        except OSError:
            return

        for name in names:
            path = os.path.join(self._tmp_dir, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            if now - stat.st_mtime <= max_age:
                continue
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def writable(self) -> bool:
        """Vérifie que ``root`` accepte la création et la suppression."""
        probe = os.path.join(self.root, ".probe")
        try:
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(probe)
        except OSError:
            return False
        return True

    def free_bytes(self) -> int:
        """Espace libre du système de fichiers qui héberge ``root``."""
        try:
            return shutil.disk_usage(self.root).free
        except OSError:
            return 0

    def _remove_files(self, media_path: str) -> bool:
        """Supprime un MP4 et son sidecar ; ``False`` si le MP4 résiste."""
        try:
            os.remove(media_path)
        except FileNotFoundError:
            pass
        except OSError:
            return False

        sidecar = media_path[: -len(".mp4")] + ".json"
        try:
            os.remove(sidecar)
        except OSError:
            pass
        return True


class SearchCache:
    """Cache mémoire TTL + LRU des résultats de recherche."""

    def __init__(
        self,
        ttl: int = 600,
        max_entries: int = 100,
        clock=time.time,
    ) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self.clock = clock
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[float, list]] = OrderedDict()

    def get(self, key: str) -> list | None:
        """Retourne les résultats de *key*, ou ``None`` si absents/expirés."""
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            timestamp, results = item
            if self.clock() - timestamp > self.ttl:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return results

    def put(self, key: str, results: list) -> None:
        """Enregistre *results* pour *key* et évince les plus anciens."""
        with self._lock:
            self._items[key] = (self.clock(), results)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)


class MetaCache:
    """Cache mémoire des sidecars, avec repli sur le disque."""

    def __init__(
        self,
        media: MediaCache,
        ttl: int = 3600,
        max_entries: int = 200,
        clock=time.time,
    ) -> None:
        self.media = media
        self.ttl = ttl
        self.max_entries = max_entries
        self.clock = clock
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[float, dict]] = OrderedDict()

    def get(self, video_id: str) -> dict | None:
        """Retourne les métadonnées de *video_id* (mémoire puis disque)."""
        with self._lock:
            item = self._items.get(video_id)
            if item is not None:
                timestamp, meta = item
                if self.clock() - timestamp <= self.ttl:
                    self._items.move_to_end(video_id)
                    return meta
                del self._items[video_id]

        meta = self.media.read_meta(video_id)
        if meta is None:
            return None
        # Un hit disque est mémorisé sans réécrire le sidecar.
        self.put(video_id, meta)
        return meta

    def put(self, video_id: str, meta: dict) -> None:
        """Mémorise *meta* pour *video_id* et évince les plus anciens."""
        with self._lock:
            self._items[video_id] = (self.clock(), meta)
            self._items.move_to_end(video_id)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
