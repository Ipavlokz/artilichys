import struct
import time
from types import SimpleNamespace
import numpy as np
import pytest
from neurovisual.sources.unicorn import _SdkSource as UnicornSource, load_sdk


class Device:
    def __init__(self, serial):
        self.n = 0
        self.stopped = False
    def GetConfiguration(self):
        return SimpleNamespace(Channels=[SimpleNamespace(Name=f'E{i}', Unit='mV', Enabled=True) for i in range(8)] + [SimpleNamespace(Name='Counter')])
    def GetNumberOfAcquiredChannels(self): return 9
    def GetChannelIndex(self, name): return 8 if name == 'Counter' else 7-int(name[1:])
    def StartAcquisition(self, test): assert test is False
    def GetData(self, count, buffer, length):
        time.sleep(.004)
        counters = [10, 11, 14]
        if self.n == 3: raise RuntimeError('synthetic link loss')
        buffer[:] = struct.pack('<9f', *range(8), counters[self.n])
        self.n += 1
    def StopAcquisition(self): self.stopped = True


def sdk():
    return SimpleNamespace(GetAvailableDevices=lambda paired: ['test'], Unicorn=Device,
        EEGConfigIndex=0, EEGChannelsCount=8, CounterConfigIndex=8,
        SamplingRate=250, GetApiVersion=lambda: 'fake-test')


def test_sdk_order_units_counter_gap_and_link_loss():
    source = UnicornSource(sdk=sdk())
    try:
        blocks = [source.read(.3) for _ in range(4)]
        assert source.metadata.sample_rate == 250
        assert source.metadata.channels == [f'E{i}' for i in range(8)]
        np.testing.assert_array_equal(blocks[0].samples[0], np.arange(7,-1,-1)*1000)
        times = [b.timestamps[0] for b in blocks[:3]]
        np.testing.assert_allclose(np.diff(times), [.004,.012], atol=1e-8)
        assert blocks[3].connected is False
        assert source.read(.01) is None
        assert 'link loss' in source.error
    finally: source.close()
    assert source.device.stopped


def test_multiple_devices_need_explicit_choice():
    api = sdk()
    api.GetAvailableDevices = lambda paired: ['a','b']
    with pytest.raises(ValueError, match='exactamente un'): UnicornSource(sdk=api)


def test_unknown_units_are_rejected():
    class Bad(Device):
        def GetConfiguration(self):
            cfg=super().GetConfiguration(); cfg.Channels[0].Unit='unknown'; return cfg
    api=sdk(); api.Unicorn=Bad
    with pytest.raises(ValueError, match='Unidad EEG'): UnicornSource(sdk=api)


def test_connection_failure_has_actionable_error():
    api = sdk()
    def unavailable(serial):
        raise RuntimeError("Couldn't connect to device")
    api.Unicorn = unavailable
    with pytest.raises(ValueError, match='Cerrar COMPLETAMENTE Unicorn Suite'):
        UnicornSource(sdk=api)


@pytest.mark.parametrize('unit', ['uV', 'µV', 'μV', 'ÂµV', 'Î¼V'])
def test_microvolt_spellings_preserve_amplitude(unit):
    class Microvolts(Device):
        def GetConfiguration(self):
            cfg = super().GetConfiguration()
            for channel in cfg.Channels[:8]:
                channel.Unit = unit
            return cfg
    api = sdk()
    api.Unicorn = Microvolts
    source = UnicornSource(sdk=api)
    try:
        block = source.read(.3)
        np.testing.assert_array_equal(block.samples[0], np.arange(7, -1, -1))
        assert source.metadata.auxiliary['native_units'] == [unit]*8
    finally:
        source.close()


def _process_stream(connection, path, serial, stop):
    from neurovisual.model import SourceMetadata, Block
    metadata = SourceMetadata(250., [f'E{i}' for i in range(8)], 'uV', 'unicorn',
                              auxiliary={'sdk_version': 'test'})
    connection.send(('metadata', metadata.to_dict()))
    origin = time.monotonic()
    n = 0
    while not stop.is_set():
        time.sleep(.04)
        ts = origin + np.arange(n, n+10)/250
        x = 15*np.sin(2*np.pi*10*(ts-origin))[:, None]*np.ones((1,8))
        connection.send(('block', Block(ts, x, max(time.monotonic(),ts[-1]))))
        n += 10
    connection.close()


def _process_hang(connection, path, serial, stop):
    from neurovisual.model import SourceMetadata
    connection.send(('metadata', SourceMetadata(250.,[f'E{i}' for i in range(8)],'uV','unicorn',
                                               auxiliary={'sdk_version':'test'}).to_dict()))
    time.sleep(30)  # Simulate a native call that does not honor stop.


def test_spawned_acquisition_keeps_streaming_through_processing(tmp_path):
    from neurovisual.sources.unicorn import UnicornSource as ProcessSource
    from neurovisual.runner import run
    from neurovisual.config import Config
    source = ProcessSource(worker=_process_stream)
    result = run(source, Config(window_seconds=2, baseline_seconds=1, settle_seconds=0),
                 record=tmp_path/'session', osc=False, print_interval=0, duration=4)
    assert source.samples_received >= 900
    assert result['valid_windows'] > 0
    assert result['baseline']['ready']
    assert not source._process.is_alive()


def test_blocked_sdk_does_not_block_consumer_and_can_be_terminated():
    from neurovisual.sources.unicorn import UnicornSource as ProcessSource
    source = ProcessSource(worker=_process_hang)
    try:
        start = time.monotonic()
        assert source.read(.02) is None
        assert time.monotonic()-start < .3
        source._last_block -= 6
        assert source.read(.01).connected is False
        assert 'sin entregar muestras' in source.error
    finally:
        source.close()
    assert not source._process.is_alive()


def test_native_sdk_multi_sample_blocks_keep_order_and_time():
    class Batch(Device):
        def GetData(self, count, buffer, length):
            time.sleep(count/250)
            if self.n >= 20:
                raise RuntimeError('end test')
            rows = [list(range(8))+[self.n+i] for i in range(count)]
            buffer[:] = struct.pack('<'+str(count*9)+'f', *np.array(rows).ravel())
            self.n += count
    api = sdk(); api.Unicorn = Batch
    source = UnicornSource(sdk=api, frame_length=10)
    try:
        first, second = source.read(.3), source.read(.3)
        assert first.samples.shape == (10,8)
        np.testing.assert_array_equal(first.samples, np.tile(np.arange(7,-1,-1)*1000,(10,1)))
        np.testing.assert_allclose(np.diff(np.r_[first.timestamps,second.timestamps]), .004, atol=1e-8)
        assert first.timestamps[-1] <= first.received_at
    finally:
        source.close()
