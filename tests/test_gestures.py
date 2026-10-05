import numpy as np
from pythonosc.osc_packet import OscPacket
from neurovisual.config import Config
from neurovisual.model import Block, SourceMetadata
from neurovisual.pipeline import Pipeline
from neurovisual.output import bundle


def pipeline(frontal=True):
    names=[f'c{i}' for i in range(8)]
    return Pipeline(SourceMetadata(250,names,'uV','test',groups={'frontal':['c0','c1']} if frontal else {}),Config())


def test_blink_pulse_visible_before_calibration_and_does_not_change_band_mapping():
    p=pipeline(); t=np.arange(125)/250
    x=np.tile((180*np.exp(-.5*((t-.23)/.055)**2))[:,None],(1,8))
    p.ingest(Block(t,x,.5))
    state=p.tick(.5)
    assert not state['status']['calibrated']
    assert state['osc']['/gesture/blink']==1
    assert state['visual']['color']==.5
    assert p.tick(.6)['osc']['/gesture/blink']==1
    assert p.tick(.71)['osc']['/gesture/blink']==0
    assert p.tick(1.1)['osc']['/gesture/blink']==0


def test_muscle_activity_independent_of_invalid_eeg_and_ends_after_clear_signal():
    p=pipeline(); t=np.arange(125)/250
    muscle=np.tile((45*np.sin(2*np.pi*43*t))[:,None],(1,8))
    p.ingest(Block(t,muscle,.5))
    frame=p.tick(.5)
    assert frame['osc']['/gesture/jaw']==1
    assert not frame['status']['valid']
    values={m.message.address:m.message.params[0] for m in OscPacket(bundle(frame['osc']).dgram).messages}
    assert isinstance(values['/gesture/jaw'],float)
    t2=t+.5
    calm=np.tile((15*np.sin(2*np.pi*10*t2))[:,None],(1,8))
    p.ingest(Block(t2,calm,1))
    assert p.tick(1)['osc']['/gesture/jaw']==0
    p.ingest(Block.empty(1.1,connected=False))
    assert p.tick(1.1)['osc']['/gesture/jaw']==0


def test_unconfirmed_frontal_channels_do_not_claim_blink_detection():
    p=pipeline(False)
    state=p.tick(0)
    assert state['osc']['/gesture/blink']==0
    assert state['osc']['/gesture/blink/available']==0


def test_sustained_muscle_keeps_jaw_on_and_brief_dropout_is_held(monkeypatch):
    p=pipeline()
    active={'muscle':True,'blink':False}
    monkeypatch.setattr('neurovisual.pipeline.detect',lambda *args: active.copy())
    for i in range(20):
        t=np.arange(10)/250+i*.04
        x=np.tile((15*np.sin(2*np.pi*10*t))[:,None],(1,8))
        p.ingest(Block(t,x,(i+1)*.04))
        assert p.tick((i+1)*.04)['osc']['/gesture/jaw']==1
    active['muscle']=False
    for i in range(20,28):
        t=np.arange(10)/250+i*.04
        p.ingest(Block(t,np.tile((15*np.sin(2*np.pi*10*t))[:,None],(1,8)),(i+1)*.04))
        value=p.tick((i+1)*.04)['osc']['/gesture/jaw']
        assert value == (1 if (i+1)*.04 < .8+.25 else 0)
