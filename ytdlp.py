"""Wrapper yt-dlp : recherche, métadonnées précoces et téléchargement."""

import json
import os
import re
import signal
import subprocess
import threading
from collections import deque

from formats import format_selector
from ids import is_valid_video_id

META_PREFIX = "LAZARUS_META "

_SEARCH_ERROR = "Recherche impossible pour le moment."
_DOWNLOAD_ERROR = "Impossible de préparer cette vidéo."
_TIMEOUT_ERROR = "Le téléchargement a pris trop de temps."
_PROGRESS_RE = re.compile(r"(\d+(?:\.\d+)?)%")
_LOG_LINES = 20
_LOG_CHARS = 500


class YtDlpError(Exception):
    """Échec d'une opération yt-dlp avec un message destiné à l'utilisateur."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class LiveNotSupported(YtDlpError):
    """La vidéo demandée est un direct, non pris en charge."""


class YtDlp:
    """Encapsule les appels à yt-dlp pour la recherche et le téléchargement."""

    def __init__(
        self,
        bin: str = "yt-dlp",
        node_bin: str | None = None,
        ffmpeg_bin: str = "ffmpeg",
        request_timeout: int = 30,
        download_timeout: int = 1800,
        log=None,
    ) -> None:
        self.bin = bin
        self.node_bin = node_bin
        self.ffmpeg_bin = ffmpeg_bin
        self.request_timeout = request_timeout
        self.download_timeout = download_timeout
        self.log = log

    def _js_args(self) -> list[str]:
        """Arguments yt-dlp pour le moteur JavaScript, si configuré."""
        if self.node_bin:
            return ["--js-runtimes", "node:" + self.node_bin]
        return []

    def _log_message(self, message: str) -> None:
        """Transmet *message* au journal fourni, s'il y en a un."""
        if self.log is not None and message:
            self.log(message)

    @staticmethod
    def _kill_group(proc: subprocess.Popen) -> None:
        """Tue le groupe de processus de *proc* (déjà terminé toléré)."""
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except OSError:
            pass

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Cherche *query* sur YouTube et retourne les résultats normalisés."""
        args = [
            self.bin,
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
        ]
        args += self._js_args()
        args.append("ytsearch%d:%s" % (limit, query))

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.request_timeout + 30,
            )
        except (OSError, subprocess.SubprocessError):
            raise YtDlpError(_SEARCH_ERROR) from None

        results = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            video_id = data.get("id")
            if not is_valid_video_id(video_id):
                continue
            results.append(
                {
                    "id": video_id,
                    "title": data.get("title") or "",
                    "duration": data.get("duration") or 0,
                    "channel": data.get("channel") or data.get("uploader") or "",
                    "view_count": data.get("view_count"),
                    "live_status": data.get("live_status"),
                }
            )

        if result.returncode != 0 and not results:
            self._log_message((result.stderr or "")[-_LOG_CHARS:])
            raise YtDlpError(_SEARCH_ERROR)
        return results

    def download(
        self,
        video_id: str,
        tmpdir: str,
        on_progress=None,
        on_meta=None,
        max_height: int = 720,
    ) -> str:
        """Télécharge *video_id* dans *tmpdir* et retourne le MP4 produit."""
        if not is_valid_video_id(video_id):
            raise YtDlpError(_DOWNLOAD_ERROR)

        out_tmpl = os.path.join(tmpdir, "%(id)s.%(ext)s")
        args = [
            self.bin,
            "-f",
            format_selector(max_height),
            "--merge-output-format",
            "mp4",
            "--postprocessor-args",
            "ffmpeg:-movflags +faststart",
            "--no-playlist",
            "--no-warnings",
            "--newline",
            "--progress",
            "--no-simulate",
            "--retries",
            "3",
            "--fragment-retries",
            "3",
            "--socket-timeout",
            "15",
            "--concurrent-fragments",
            "4",
            "--print",
            "before_dl:"
            + META_PREFIX
            + '{"id":%(id)j,"title":%(title)j,"channel":%(channel)j,'
            '"duration":%(duration)j,"view_count":%(view_count)j,'
            '"live_status":%(live_status)j}',
            "-o",
            out_tmpl,
            "https://www.youtube.com/watch?v=" + video_id,
        ]

        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        timed_out = threading.Event()

        def _on_timeout() -> None:
            timed_out.set()
            self._kill_group(proc)

        timer = threading.Timer(self.download_timeout, _on_timeout)
        timer.daemon = True
        timer.start()

        tail: deque[str] = deque(maxlen=_LOG_LINES)
        try:
            try:
                for raw_line in proc.stdout:
                    line = raw_line.rstrip("\n")
                    if line:
                        tail.append(line)

                    if line.startswith(META_PREFIX):
                        try:
                            meta = json.loads(line[len(META_PREFIX):])
                        except ValueError:
                            continue
                        if isinstance(meta, dict) and on_meta is not None:
                            on_meta(meta)
                        continue

                    if "[download]" in line and on_progress is not None:
                        match = _PROGRESS_RE.search(line)
                        if match:
                            on_progress(round(float(match.group(1)), 1))
            except BaseException:
                self._kill_group(proc)
                proc.wait()
                raise
        finally:
            timer.cancel()
            if proc.stdout is not None:
                proc.stdout.close()

        proc.wait()

        if timed_out.is_set():
            raise YtDlpError(_TIMEOUT_ERROR)

        if proc.returncode != 0:
            self._log_message("\n".join(tail)[-_LOG_CHARS:])
            raise YtDlpError(_DOWNLOAD_ERROR)

        try:
            names = os.listdir(tmpdir)
        except OSError:
            names = []
        candidates = [
            os.path.join(tmpdir, name)
            for name in names
            if name.endswith(".mp4") and os.path.isfile(os.path.join(tmpdir, name))
        ]
        if not candidates:
            raise YtDlpError(_DOWNLOAD_ERROR)
        return max(candidates, key=os.path.getsize)
