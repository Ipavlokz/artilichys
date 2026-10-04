from abc import ABC, abstractmethod
import time

from ..model import Block, SourceMetadata


class Source(ABC):
    """Adapters must honor timeout; None means no block, finished distinguishes EOF.

    `now`, timestamps and received_at share a monotonic clock in seconds.
    Convert EEG to uV and IMU acceleration to g before returning blocks.
    A blocked transport must return periodically so stale and OSC keep updating.
    """

    metadata: SourceMetadata
    finished: bool = False

    @abstractmethod
    def read(self, timeout: float) -> Block | None:
        pass

    @abstractmethod
    def now(self) -> float:
        pass

    def close(self):
        pass


class TimedSource(Source):
    def __init__(self, metadata, blocks, speed=1.0):
        if speed < 0:
            raise ValueError("speed debe ser >= 0 (0 = ejecución acelerada)")
        metadata.validate()
        self.metadata = metadata
        self.speed = speed
        self._iterator = iter(blocks)
        self._next = next(self._iterator, None)
        self.finished = self._next is None
        self._origin = (float(self._next.timestamps[0]) if self._next is not None and len(self._next.timestamps)
                        else self._next.received_at if self._next is not None else 0.0)
        self._wall = time.monotonic()
        self._current = self._origin

    def now(self):
        return self._current if self.speed == 0 else self._origin + (time.monotonic() - self._wall) * self.speed

    def read(self, timeout):
        if self.finished:
            return None
        if self.speed:
            delay = (self._next.received_at - self.now()) / self.speed
            if delay > 0:
                time.sleep(min(delay, max(0, timeout)))
            if self._next.received_at > self.now():
                return None
        block = self._next
        self._current = block.received_at
        self._next = next(self._iterator, None)
        self.finished = self._next is None
        return block
