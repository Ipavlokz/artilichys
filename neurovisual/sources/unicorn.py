"""Official UnicornPy adapter. Native SDK acquisition runs off the OSC thread."""
import multiprocessing
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


class _SdkSource(Source):
    def __init__(self, sdk_path=None, serial=None, sdk=None, frame_length=1):
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
        # Some Windows SDK builds decode UTF-8 micro signs as Windows-1252.
        # Accept only identified spellings; never guess arbitrary units.
        scales = {'uv': 1., 'µv': 1., 'μv': 1., 'âµv': 1., 'î¼v': 1.,
                  'mv': 1000., 'v': 1e6}
        try:
            self.scales = np.array([scales[c.Unit.strip().lower()] for c in eeg])
        except KeyError as exc:
            raise ValueError(f'Unidad EEG no reconocida: {exc}') from exc
        self.frame_length = frame_length
        self.count = int(self.device.GetNumberOfAcquiredChannels())
        self.indices = [int(self.device.GetChannelIndex(c.Name)) for c in eeg]
        self.counter = int(self.device.GetChannelIndex(cfg.Channels[int(self.sdk.CounterConfigIndex)].Name))
        if len(set(self.indices)) != 8 or any(i < 0 or i >= self.count for i in self.indices+[self.counter]):
            raise ValueError('Indices de canales invalidos en el SDK')
        self.metadata = SourceMetadata(float(self.sdk.SamplingRate), [c.Name for c in eeg], 'uV', 'unicorn',
            auxiliary={'serial': serial, 'sdk_version': str(self.sdk.GetApiVersion()),
                       'native_units': [c.Unit for c in eeg],
                       'timestamp_method': 'sample counter anchored to host monotonic reception',
                       'imu_available': False, 'anatomical_positions_confirmed': False,
                       'acquisition_block_samples': frame_length, 'sdk_process_isolated': True})
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
            buffer = bytearray(self.frame_length * self.count * 4)
            while not self._stop.is_set():
                self.device.GetData(self.frame_length, buffer, len(buffer))
                rows = np.frombuffer(buffer, dtype=np.float32).reshape(self.frame_length, self.count).copy()
                received = self.now()
                timestamps = []
                for index, row in enumerate(rows):
                    counter = float(row[self.counter])
                    if not np.isfinite(counter):
                        raise ValueError('Contador de muestras no finito')
                    if previous is None:
                        timestamp = received - (len(rows)-1-index)/self.metadata.sample_rate
                    else:
                        delta = counter - previous
                        if delta <= 0:
                            raise ValueError('Contador reiniciado o repetido; reiniciar sesion para reconectar')
                        timestamp += delta / self.metadata.sample_rate
                    previous = counter
                    timestamps.append(timestamp)
                received = max(received, timestamp)
                self._queue.put(Block(np.array(timestamps), rows[:, self.indices]*self.scales, received))
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


def _sdk_worker(connection, sdk_path, serial, stop, source_factory=_SdkSource):
    """Windows spawn entry point: native library is loaded only in this process."""
    source = None
    try:
        source = source_factory(sdk_path=sdk_path, serial=serial, frame_length=10)
        connection.send(('metadata', source.metadata.to_dict()))
        while not stop.is_set():
            block = source.read(.1)
            if block is not None:
                connection.send(('block', block))
                if not block.connected:
                    connection.send(('error', getattr(source, 'error', 'Adquisicion detenida')))
                    break
    except Exception as exc:
        try:
            connection.send(('error', str(exc)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        if source is not None:
            source.close()
        connection.close()


class UnicornSource(Source):
    """DSP and OSC never share a Python GIL with the native acquisition DLL."""
    def __init__(self, sdk_path=None, serial=None, worker=_sdk_worker):
        context = multiprocessing.get_context('spawn')
        self._connection, child = context.Pipe(duplex=False)
        self._stop = context.Event()
        self._process = context.Process(target=worker, args=(child, sdk_path, serial, self._stop), daemon=True)
        self.finished = False
        self.error = None
        self._failed = False
        self._last_block = time.monotonic()
        self.samples_received = 0
        try:
            self._process.start()
            child.close()
            if not self._connection.poll(30):
                raise ValueError('El SDK no respondio en 30 segundos al conectar. Cerrar Suite y revisar Bluetooth/licencia.')
            kind, payload = self._connection.recv()
            if kind != 'metadata':
                raise ValueError(str(payload))
            self.metadata = SourceMetadata(**payload)
            self.metadata.validate()
            self._last_block = self.now()
            print(f'Unicorn: API {self.metadata.auxiliary["sdk_version"]}, '
                  f'{self.metadata.sample_rate:g} Hz; adquisicion en proceso separado, bloques de 10 muestras.', flush=True)
        except BaseException:
            child.close()
            self.close()
            raise

    def now(self):
        return time.monotonic()

    def _failure(self, message):
        self._failed = True
        self.error = message
        print(f'Unicorn: {message}. Detener y reiniciar la sesion.', file=sys.stderr, flush=True)
        self._stop.set()
        return Block.empty(self.now(), connected=False)

    def read(self, timeout):
        if self._failed:
            time.sleep(max(0, timeout))
            return None
        try:
            if self._connection.poll(max(0, timeout)):
                kind, payload = self._connection.recv()
                if kind == 'block':
                    self._last_block = self.now()
                    self.samples_received += len(payload.timestamps)
                    return payload
                return self._failure(str(payload))
            if not self._process.is_alive():
                return self._failure(f'Proceso de adquisicion finalizado (codigo {self._process.exitcode})')
            if self.now() - self._last_block > 5:
                return self._failure('El SDK lleva 5 segundos sin entregar muestras; posible bloqueo de lectura o perdida Bluetooth')
            return None
        except (EOFError, OSError) as exc:
            return self._failure(f'Canal de adquisicion cerrado: {exc}')

    def close(self):
        self._stop.set()
        if self._process.pid is not None:
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=2)
        self._connection.close()
