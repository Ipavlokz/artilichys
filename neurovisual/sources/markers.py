import json
import math
from pathlib import Path
from dataclasses import replace
import socket
import uuid

from .base import Source


class MarkedSource(Source):
    """Attach externally measured condition markers, using source timestamps."""

    def __init__(self, source, path):
        self.source = source
        self.metadata = source.metadata
        self.markers = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(self.markers, list):
            raise ValueError("El archivo de marcadores debe ser una lista JSON")
        for marker in self.markers:
            if (not isinstance(marker, dict) or marker.get("condition") not in ("reference", "music")
                    or isinstance(marker.get("timestamp"), bool)
                    or not isinstance(marker.get("timestamp"), (int, float))
                    or not math.isfinite(marker["timestamp"])):
                raise ValueError("Cada marcador requiere timestamp y condition reference/music")
        self.markers.sort(key=lambda item: item["timestamp"])
        self.index = 0
        if len({marker["timestamp"] for marker in self.markers}) != len(self.markers):
            raise ValueError("Los marcadores requieren timestamps distintos")

    @property
    def finished(self):
        return self.source.finished

    def read(self, timeout):
        block = self.source.read(timeout)
        if block is not None:
            block.markers = []  # explicit annotations replace simulated/saved conditions
            while self.index < len(self.markers) and self.markers[self.index]["timestamp"] <= block.received_at:
                block.markers.append(self.markers[self.index])
                self.index += 1
            block.markers.sort(key=lambda item: item["timestamp"])
        return block

    def now(self):
        return self.source.now()

    def close(self):
        self.source.close()


class ManualMarkedSource(Source):
    """Local operator annotations, timestamped in the source clock on reception.

    Queued markers only enter blocks whose received_at is at or after the marker.
    No EEG samples or source timestamps are changed. No background thread is used.
    """

    def __init__(self, source, port=9001):
        if not 0 <= port <= 65535:
            raise ValueError("Puerto de marcadores fuera de rango")
        self.source = source
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.bind(("127.0.0.1", port))
            self.socket.setblocking(False)
        except OSError:
            self.socket.close()
            raise
        self.port = self.socket.getsockname()[1]
        self.metadata = replace(source.metadata, auxiliary={**source.metadata.auxiliary,
            "condition_markers": {"mode": "manual", "port": self.port,
                                  "initial_condition": "reference", "controls_audio": False,
                                  "timestamp": "source.now at local request reception; operator timing"}})
        self.pending = []
        self.initialized = False
        self.initial_timestamp = float(source.now())

    @property
    def finished(self):
        return self.source.finished

    def now(self):
        return self.source.now()

    def reply(self, peer, response):
        self.socket.sendto(json.dumps(response, allow_nan=False).encode("utf-8"), peer)

    def poll(self):
        for _ in range(32):  # keep the acquisition timeout bounded
            try:
                payload, peer = self.socket.recvfrom(4096)
            except BlockingIOError:
                break
            try:
                request = json.loads(payload)
                if (not isinstance(request, dict) or request.get("condition") not in ("reference", "music")
                        or not isinstance(request.get("id"), str)
                        or not isinstance(request.get("label", ""), str)
                        or len(request.get("label", "")) > 512):
                    raise ValueError("Se requiere condition reference/music, id y label de texto <= 512 caracteres")
                if len(self.pending) >= 32:
                    raise ValueError("Demasiados marcadores pendientes; esperar al siguiente bloque")
                marker = {"timestamp": float(self.now()), "condition": request["condition"],
                          "label": request.get("label", ""), "origin": "manual"}
                self.pending.append((marker, peer, request["id"]))
            except (ValueError, UnicodeError) as exc:
                self.reply(peer, {"ok": False, "error": str(exc)})

    def read(self, timeout):
        self.poll()
        block = self.source.read(timeout)
        if block is None:
            return None
        block.markers = []
        if not self.initialized:
            stamp = float(block.timestamps[0]) if len(block.timestamps) else block.received_at
            stamp = min(stamp, self.initial_timestamp)
            block.markers.append({"timestamp": stamp, "condition": "reference", "origin": "manual",
                                  "label": "Initial reference: operator must start without music"})
            self.initialized = True
        waiting = []
        for marker, peer, request_id in self.pending:
            if marker["timestamp"] <= block.received_at:
                block.markers.append(marker)
                self.reply(peer, {"ok": True, "id": request_id, **marker})
            else:
                waiting.append((marker, peer, request_id))
        self.pending = waiting
        block.markers.sort(key=lambda item: item["timestamp"])
        return block

    def close(self):
        try:
            for _, peer, request_id in self.pending:
                self.reply(peer, {"ok": False, "id": request_id,
                                  "error": "La fuente terminó antes de recibir otro bloque; marcador no incorporado"})
        finally:
            self.socket.close()
            self.source.close()


def send_marker(condition, port=9001, label="", timeout=2):
    """Send a local marker and wait for confirmation from the acquisition wrapper."""
    if condition not in ("reference", "music") or not 1 <= port <= 65535:
        raise ValueError("Usar condition reference/music y puerto entre 1 y 65535")
    if not isinstance(label, str) or len(label) > 512:
        raise ValueError("La etiqueta debe ser texto de hasta 512 caracteres")
    request_id = uuid.uuid4().hex
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(timeout)
        client.connect(("127.0.0.1", port))
        client.send(json.dumps({"id": request_id, "condition": condition, "label": label}).encode("utf-8"))
        try:
            response = json.loads(client.recv(4096))
        except (socket.timeout, ConnectionRefusedError, ConnectionResetError) as exc:
            raise ValueError("No llegó confirmación: comprobar que la sesión sigue abierta con --manual-markers y el mismo puerto. Revisar events.jsonl antes de repetir.") from exc
    if not response.get("ok"):
        raise ValueError(response.get("error", "Marcador rechazado"))
    if response.get("id") != request_id:
        raise ValueError("La confirmación no corresponde al marcador enviado")
    return response
