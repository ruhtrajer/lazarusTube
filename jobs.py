"""Registre de jobs de téléchargement pour LazarusTube.

Le registre garde un état en mémoire par vidéo (``idle``, ``queued``,
``downloading``, ``ready`` ou ``error``), limite le nombre de téléchargements
simultanés et relance une fois en 480p quand le MP4 720p est refusé par la
validation iPad 2.
"""

import copy
import logging
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field

from formats import FormatError, validate_mp4
from ytdlp import LiveNotSupported, YtDlpError

_IDLE_PROGRESS = -1.0
_READY_PROGRESS = 100.0
_MIN_FREE_BYTES = 500 * 1024 * 1024
_PROGRESS_INTERVAL = 0.25
_MAX_JOBS = 200
_FALLBACK_HEIGHT = 480

_LIVE_MESSAGE = "Les directs ne sont pas disponibles."
_FORMAT_MESSAGE = "Format incompatible avec cet appareil."
_DISK_MESSAGE = "Espace disque insuffisant."
_GENERIC_MESSAGE = "Impossible de préparer cette vidéo."

_LOG = logging.getLogger(__name__)


class ForceRefused(Exception):
    """Un téléchargement forcé a été refusé car la vidéo est en lecture."""


@dataclass
class Job:
    """État d'un téléchargement, partagé entre le worker et ``status``."""

    video_id: str
    state: str = "queued"
    progress: float = _IDLE_PROGRESS
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error: str | None = None
    meta: dict = field(default_factory=dict)
    finished_at: float | None = None


class JobRegistry:
    """Registre thread-safe des jobs de téléchargement."""

    def __init__(
        self,
        media,
        ytdlp,
        streams,
        max_concurrent: int = 2,
        max_height: int = 720,
        clock=time.time,
        log=None,
    ) -> None:
        self.media = media
        self.ytdlp = ytdlp
        self.streams = streams
        self.max_height = max_height
        self.clock = clock
        self.log = log
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._semaphore = threading.Semaphore(max_concurrent)
        self._video_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def start(
        self, video_id: str, retry: bool = False, force: bool = False
    ) -> dict:
        """Démarre (ou relance) le job de *video_id* et retourne son snapshot."""
        with self._lock:
            if force:
                if self.streams.is_active(self.media.media_path(video_id)):
                    raise ForceRefused("Cette vidéo est en cours de lecture.")
                self.media.delete(video_id)

            if self.media.has(video_id):
                job = Job(
                    video_id=video_id,
                    state="ready",
                    progress=_READY_PROGRESS,
                    meta=dict(self.media.read_meta(video_id) or {}),
                    finished_at=self.clock(),
                )
                self._jobs[video_id] = job
                return self._snapshot(job)

            job = self._jobs.get(video_id)
            if job is not None and job.state in ("queued", "downloading"):
                return self._snapshot(job)
            if job is not None and job.state == "error" and not retry:
                return self._snapshot(job)

            job = Job(video_id=video_id)
            self._jobs[video_id] = job
            thread = threading.Thread(
                target=self._run,
                args=(job,),
                name="job-" + video_id,
                daemon=True,
            )
            thread.start()
            return self._snapshot(job)

    def status(self, video_id: str) -> dict:
        """Retourne un snapshot de l'état du job de *video_id*."""
        with self._lock:
            job = self._jobs.get(video_id)
            if job is None:
                return {
                    "id": video_id,
                    "state": "idle",
                    "progress": _IDLE_PROGRESS,
                    "downloaded_bytes": 0,
                    "total_bytes": 0,
                    "error": None,
                    "meta": {},
                }
            return self._snapshot(job)

    def cleanup(self, max_age: int = 3600) -> None:
        """Oublie les jobs terminés trop anciens et borne leur nombre."""
        with self._lock:
            now = self.clock()
            for video_id, job in list(self._jobs.items()):
                if job.finished_at is not None and now - job.finished_at > max_age:
                    del self._jobs[video_id]

            while len(self._jobs) > _MAX_JOBS:
                finished = [
                    (job.finished_at, video_id)
                    for video_id, job in self._jobs.items()
                    if job.finished_at is not None
                ]
                if not finished:
                    break
                _, video_id = min(finished)
                del self._jobs[video_id]

    def _snapshot(self, job: Job) -> dict:
        """Copie l'état d'un job pour qu'un lecteur ne voie pas de mutation."""
        return {
            "id": job.video_id,
            "state": job.state,
            "progress": job.progress,
            "downloaded_bytes": job.downloaded_bytes,
            "total_bytes": job.total_bytes,
            "error": job.error,
            "meta": copy.deepcopy(job.meta),
        }

    def _lock_for(self, video_id: str) -> threading.Lock:
        """Retourne le verrou dédié à *video_id*, en le créant au besoin."""
        with self._locks_guard:
            lock = self._video_locks.get(video_id)
            if lock is None:
                lock = threading.Lock()
                self._video_locks[video_id] = lock
            return lock

    def _run(self, job: Job) -> None:
        """Exécute le téléchargement d'un job dans un thread démon."""
        with self._lock_for(job.video_id):
            tmpdir = None
            try:
                with self._semaphore:
                    if self.media.has(job.video_id):
                        meta = self.media.read_meta(job.video_id) or job.meta
                        self._mark_ready(job, meta)
                        return

                    with self._lock:
                        job.state = "downloading"

                    if self.media.free_bytes() < _MIN_FREE_BYTES:
                        self._fail(job, _DISK_MESSAGE)
                        return

                    tmp_root = os.path.join(self.media.root, "tmp")
                    os.makedirs(tmp_root, exist_ok=True)
                    tmpdir = tempfile.mkdtemp(
                        prefix=job.video_id + "-", dir=tmp_root
                    )

                    path = self._download(job, tmpdir)
                    self.media.publish(job.video_id, path, job.meta)
                    self._mark_ready(job)
                    self.media.evict()
            except LiveNotSupported:
                self._fail(job, _LIVE_MESSAGE)
            except FormatError as exc:
                self._fail(job, exc.user_message)
            except YtDlpError as exc:
                self._fail(job, exc.user_message)
            except Exception:
                self._log_exception(
                    "Échec inattendu du job " + job.video_id
                )
                self._fail(job, _GENERIC_MESSAGE)
            finally:
                if tmpdir is not None:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                with self._lock:
                    job.finished_at = self.clock()
                self.cleanup()

    def _download(self, job: Job, tmpdir: str) -> str:
        """Télécharge le MP4, avec une seconde tentative en 480p si besoin."""
        progress = self._progress_callback(job)
        meta = self._meta_callback(job)

        path = self.ytdlp.download(
            job.video_id,
            tmpdir,
            on_progress=progress,
            on_meta=meta,
            max_height=self.max_height,
        )
        try:
            validate_mp4(path)
        except FormatError:
            path = self.ytdlp.download(
                job.video_id,
                tmpdir,
                on_progress=progress,
                on_meta=meta,
                max_height=_FALLBACK_HEIGHT,
            )
            try:
                validate_mp4(path)
            except FormatError:
                raise FormatError(_FORMAT_MESSAGE) from None
        return path

    def _progress_callback(self, job: Job):
        """Construit un callback de progression limité à ~4 Hz."""
        last_update = [self.clock() - _PROGRESS_INTERVAL]

        def update(value, downloaded_bytes=None, total_bytes=None) -> None:
            try:
                value = float(value)
            except (TypeError, ValueError):
                return
            if not 0.0 <= value <= 100.0:
                return

            now = self.clock()
            if value < _READY_PROGRESS and now - last_update[0] < _PROGRESS_INTERVAL:
                return
            last_update[0] = now

            with self._lock:
                job.progress = value
                if downloaded_bytes is not None:
                    try:
                        job.downloaded_bytes = int(downloaded_bytes)
                    except (TypeError, ValueError):
                        pass
                if total_bytes is not None:
                    try:
                        job.total_bytes = int(total_bytes)
                    except (TypeError, ValueError):
                        pass

        return update

    def _meta_callback(self, job: Job):
        """Construit un callback qui mémorise les métadonnées précoces."""

        def update(meta) -> None:
            if not isinstance(meta, dict):
                return
            with self._lock:
                for key, value in meta.items():
                    if value is not None:
                        job.meta[key] = value
                live_status = job.meta.get("live_status")

            if live_status in ("is_live", "is_upcoming"):
                raise LiveNotSupported(_LIVE_MESSAGE)

        return update

    def _mark_ready(self, job: Job, meta: dict | None = None) -> None:
        """Passe *job* à l'état ``ready``."""
        with self._lock:
            job.state = "ready"
            job.progress = _READY_PROGRESS
            job.error = None
            if meta is not None:
                job.meta = dict(meta)

    def _fail(self, job: Job, message: str) -> None:
        """Passe *job* à l'état ``error`` avec un message utilisateur."""
        with self._lock:
            job.state = "error"
            job.error = message

    def _log_exception(self, message: str) -> None:
        """Journalise l'exception courante, sans jamais masquer l'erreur."""
        if self.log is None:
            _LOG.exception(message)
            return
        try:
            self.log(message, exc_info=True)
        except TypeError:
            try:
                self.log(message)
            except Exception:
                pass
        except Exception:
            pass
