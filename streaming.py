"""Réponses HTTP Range (200/206/416) compatibles Safari 9."""

import os
import re
from collections.abc import Callable, Iterator

from flask import Response

CHUNK_SIZE = 64 * 1024

_CONTENT_TYPE = "video/mp4"
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeNotSatisfiable(Exception):
    """Range invalide ou non satisfaisable pour la taille demandée."""

    def __init__(self, size: int) -> None:
        super().__init__(f"Range non satisfaisable pour {size} octets")
        self.size = size


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Analyse un en-tête ``Range``.

    Retourne ``(start, end)`` inclusif pour une réponse 206, ou ``None``
    lorsqu'il faut renvoyer la ressource complète en 200. Lève
    ``RangeNotSatisfiable`` pour un range invalide.
    """
    if size <= 0:
        raise RangeNotSatisfiable(size)
    if not header:
        return None
    # Un range multiple n'est pas pris en charge : réponse 200 complète.
    if "," in header:
        return None

    match = _RANGE_RE.fullmatch(header)
    if match is None:
        raise RangeNotSatisfiable(size)

    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise RangeNotSatisfiable(size)

    if not start_text:
        suffix = int(end_text)
        if suffix == 0:
            raise RangeNotSatisfiable(size)
        return (max(0, size - suffix), size - 1)

    start = int(start_text)
    if start >= size:
        raise RangeNotSatisfiable(size)

    end = size - 1 if not end_text else int(end_text)
    if start > end:
        raise RangeNotSatisfiable(size)

    return (start, min(end, size - 1))


def _make_on_end(
    path: str,
    registry: object | None,
) -> Callable[[], None] | None:
    """Construit une fermeture idempotente appelant ``registry.end(path)``."""
    if registry is None:
        return None

    called = False

    def on_end() -> None:
        nonlocal called
        if called:
            return
        called = True
        registry.end(path)

    return on_end


def _iter_file(
    path: str,
    start: int,
    length: int,
    on_end: Callable[[], None] | None = None,
) -> Iterator[bytes]:
    """Générateur lisant *length* octets depuis *start*, par blocs de 64 Kio."""
    try:
        with open(path, "rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    finally:
        if on_end is not None:
            on_end()


def _base_headers(length: int) -> dict[str, str]:
    return {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Type": _CONTENT_TYPE,
        "Cache-Control": "no-store",
    }


def _text_response(
    message: str,
    status: int,
    head: bool,
    headers: dict[str, str] | None = None,
) -> Response:
    """Réponse texte dont la version HEAD annonce la taille sans corps."""
    body = message.encode("utf-8")
    response_headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Length": str(len(body)),
    }
    if headers is not None:
        response_headers.update(headers)

    if head:
        response = Response(b"", status=status, headers=response_headers)
        # ``set_data`` force Content-Length à 0 ; on annonce la taille du GET.
        response.headers["Content-Length"] = str(len(body))
        return response
    return Response(body, status=status, headers=response_headers)


def range_response(
    path: str,
    range_header: str | None,
    registry: object | None = None,
    head: bool = False,
) -> Response:
    """Construit une réponse 200, 206 ou 416 pour le fichier *path*.

    Le registre, s'il est fourni, est duck-typé : ``begin(path)`` est appelé
    avant l'envoi et ``end(path)`` à la fin de la lecture (ou immédiatement
    pour une réponse ``HEAD``).
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return _text_response("Fichier introuvable.", 404, head)

    try:
        byte_range = parse_range(range_header, size)
    except RangeNotSatisfiable as exc:
        return _text_response(
            "Range non satisfaisable.",
            416,
            head,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes */{exc.size}",
            },
        )

    if byte_range is None:
        status = 200
        start, length = 0, size
        content_range = None
    else:
        start, end = byte_range
        status = 206
        length = end - start + 1
        content_range = f"bytes {start}-{end}/{size}"

    headers = _base_headers(length)
    if content_range is not None:
        headers["Content-Range"] = content_range

    if head:
        if registry is not None:
            registry.begin(path)
            registry.end(path)
        response = Response(b"", status=status, headers=headers)
        # ``set_data`` force Content-Length à 0 ; on rétablit la taille réelle.
        response.headers["Content-Length"] = str(length)
        return response

    if registry is not None:
        registry.begin(path)

    on_end = _make_on_end(path, registry)
    response = Response(
        _iter_file(path, start, length, on_end),
        status=status,
        headers=headers,
    )
    if on_end is not None:
        # Couvre une fermeture avant la première itération du générateur.
        response.call_on_close(on_end)
    return response
