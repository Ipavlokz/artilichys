from pythonosc.osc_bundle_builder import IMMEDIATELY, OscBundleBuilder
from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.udp_client import UDPClient

from .contracts import DEFAULT_OSC_ADDRESSES, FEATURE_KEYS


def messages(status, features, events, visual, visual_addresses=None, gestures=None):
    addresses = DEFAULT_OSC_ADDRESSES if visual_addresses is None else visual_addresses
    result = {
        "/neuro/connected": int(status["connected"]),
        "/neuro/quality/global": float(status["global_score"]),
        "/neuro/motion": float(status["motion"]),
        "/neuro/stale": int(status["stale"]),
        "/neuro/features/valid": int(status["valid"]),
        "/neuro/calibrated": int(status["calibrated"]),
        "/neuro/motion/available": int(status["motion_available"]),
        "/neuro/posterior_alpha/available": int(status["posterior_available"]),
        "/neuro/lateral_balance/available": int(status["lateral_available"]),
    }
    result.update({f"/neuro/quality/ch{i + 1}": float(q) for i, q in enumerate(status["channels"])})
    result.update({f"/neuro/{key}": float(features[key]) for key in FEATURE_KEYS})
    result.update({f"/neuro/event/{key}": int(events.get(key, 0)) for key in ("blink", "muscle", "reconnect")})
    result.update({addresses[key]: int(value) if key in ("scene", "pulse") else float(value)
                   for key, value in visual.items()})
    if gestures is not None:
        result.update({"/gesture/blink": float(gestures["blink"]),
                       "/gesture/jaw": float(gestures["jaw"]),
                       "/gesture/blink/available": int(gestures["blink_available"]),
                       "/gesture/jaw/available": int(gestures["jaw_available"])})
    return result


def bundle(values):
    builder = OscBundleBuilder(IMMEDIATELY)
    for address, value in values.items():
        message = OscMessageBuilder(address=address)
        message.add_arg(value, arg_type="i" if isinstance(value, int) else "f")
        builder.add_content(message.build())
    return builder.build()


class OscOutput:
    def __init__(self, host="127.0.0.1", port=9000):
        if not 1 <= port <= 65535:
            raise ValueError("Puerto OSC fuera de rango")
        self.client = UDPClient(host, port)

    def send(self, values):
        self.client.send(bundle(values))

    def close(self):
        self.client.close()
