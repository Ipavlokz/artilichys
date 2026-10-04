import struct
import time
from types import SimpleNamespace
import numpy as np
import pytest
from neurovisual.sources.unicorn import UnicornSource, load_sdk


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
