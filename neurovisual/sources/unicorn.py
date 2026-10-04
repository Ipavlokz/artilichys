"""Official UnicornPy adapter. Native SDK acquisition runs off the OSC thread."""
import importlib
import os
from pathlib import Path
import queue
import sys
import threading
import time
import numpy as np
from .base import Source
from ..model import Block, SourceMetadata


def load_sdk(path):
    if sys.platform != 'win32':
        raise ValueError('UnicornPy requiere Windows de 64 bits; usar simulated en este sistema')
    folder = Path(path).resolve()
    if not (folder / 'UnicornPy.pyd').is_file():
        raise ValueError(f'No se encontro UnicornPy.pyd en {folder}; ejecutar CONECTAR_UNICORN.cmd')
    # Retain DLL search handle throughout the process lifetime.
    handle = os.add_dll_directory(str(folder))
    sys.path.insert(0, str(folder))
    try:
        sdk = importlib.import_module('UnicornPy')
        sdk._neurovisual_dll_handle = handle
        return sdk
    except Exception as exc:
        handle.close()
        raise ValueError(f'No se pudo cargar UnicornPy: {exc}. Revisar licencia Python API y runtime Visual C++ x64.') from exc


class UnicornSource(Source):
    def __init__(self, sdk_path=None, serial=None, sdk=None):
        self.sdk = sdk if sdk is not None else load_sdk(sdk_path)
        try:
            devices = list(self.sdk.GetAvailableDevices(True) or [])
        except Exception as exc:
            raise ValueError(f'No se pudo buscar el Unicorn por Bluetooth: {exc}') from exc
        if serial is None:
            if len(devices) != 1:
                raise ValueError(f'Se requiere exactamente un Unicorn emparejado, o --device SERIAL. Encontrados: {devices}')
            serial = devices[0]
        try:
            self.device = self.sdk.Unicorn(serial)
        except Exception as exc:
            raise ValueError(
                f'El SDK no pudo abrir el Unicorn {serial}. '
                'Cerrar COMPLETAMENTE Unicorn Suite, Recorder y otros programas que usen el equipo; '
                'comprobar que esta encendido, con bateria y emparejado en Windows. '
                f'Si persiste, probar primero la conexion en Suite y cerrarlo antes de reintentar. Detalle SDK: {exc}'
            ) from exc
        cfg = self.device.GetConfiguration()
        eeg = list(cfg.Channels)[int(self.sdk.EEGConfigIndex):int(self.sdk.EEGConfigIndex)+int(self.sdk.EEGChannelsCount)]
        if len(eeg) != 8 or not all(c.Enabled for c in eeg):
            raise ValueError('La configuracion del Unicorn debe habilitar ocho canales EEG')
        scales = {'uv': 1., 'µv': 1., 'μv': 1., 'mv': 1000., 'v': 1e6}
        try:
            self.scales = np.array([scales[c.Unit.strip().lower()] for c in eeg])
        except KeyError as exc:
            raise ValueError(f'Unidad EEG no reconocida: {exc}') from exc
        self.count = int(self.device.GetNumberOfAcquiredChannels())
        self.indices = [int(self.device.GetChannelIndex(c.Name)) for c in eeg]
        self.counter = int(self.device.GetChannelIndex(cfg.Channels[int(self.sdk.CounterConfigIndex)].Name))
        if len(set(self.indices)) != 8 or any(i < 0 or i >= self.count for i in self.indices+[self.counter]):
            raise ValueError('Indices de canales invalidos en el SDK')
        self.metadata = SourceMetadata(float(self.sdk.SamplingRate), [c.Name for c in eeg], 'uV', 'unicorn',
            auxiliary={'serial': serial, 'sdk_version': str(self.sdk.GetApiVersion()),
                       'native_units': [c.Unit for c in eeg],
                       'timestamp_method': 'sample counter anchored to host monotonic reception',
                       'imu_available': False, 'anatomical_positions_confirmed': False})
        self.metadata.validate()
        self.finished = False
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._acquire, daemon=True)
        self._thread.start()

    def now(self):
        return time.monotonic()

    def _acquire(self):
        started = False
        previous = None
        timestamp = None
        try:
            self.device.StartAcquisition(False)
            started = True
            buffer = bytearray(self.count * 4)
            while not self._stop.is_set():
                self.device.GetData(1, buffer, len(buffer))
                row = np.frombuffer(buffer, dtype=np.float32).copy()
                received = self.now()
                counter = float(row[self.counter])
                if not np.isfinite(counter):
                    raise ValueError('Contador de muestras no finito')
                if previous is None:
                    timestamp = received
                else:
                    delta = counter - previous
                    if delta <= 0:
                        raise ValueError('Contador reiniciado o repetido; reiniciar sesion para reconectar')
                    timestamp += delta / self.metadata.sample_rate
                previous = counter
                # No wall-clock jitter is hidden by changing sample spacing.
                received = max(received, timestamp)
                self._queue.put(Block(np.array([timestamp]), (row[self.indices]*self.scales)[None, :], received))
        except Exception as exc:
            self.error = str(exc)
            print(f'Unicorn: adquisicion detenida: {exc}. Reiniciar para reconectar.', file=sys.stderr, flush=True)
            self._queue.put(Block.empty(self.now(), connected=False))
        finally:
            if started:
                try:
                    self.device.StopAcquisition()
                except Exception:
                    pass

    def read(self, timeout):
        try:
            return self._queue.get(timeout=max(0, timeout))
        except queue.Empty:
            return None

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
        # A stuck native call cannot be safely killed from Python. The daemon
        # exits with the process; never StopAcquisition concurrently with GetData.
