import json

from .output import OscOutput
from .pipeline import Pipeline
from .recording import clean


def readable_status(state, elapsed):
    status, features, visual = state["status"], state["features"], state["visual"]
    bands = " ".join(f"{key}={features[key]:.2f}" for key in ("alpha", "beta", "theta")) if status["valid"] else "EEG pendiente de ventana valida"
    reasons = ",".join(status["reasons"]) or "ninguno"
    return (f"{elapsed:5.1f} s | conexion={'SI' if status['connected'] else 'NO'} | "
            f"calidad={status['global_score']:.2f} | calibracion={'LISTA' if status['calibrated'] else 'PENDIENTE'} | "
            f"ventana={'VALIDA' if status['valid'] else 'INVALIDA'} | {bands} | "
            f"color={visual['color']:.2f} intensidad={visual['intensity']:.2f} flujo={visual['flow']:.2f} | "
            f"condicion={status['condition']} | motivos={reasons}")


def run(source, config, record=None, osc_host="127.0.0.1", osc_port=9000, osc=True,
        print_interval=1.0, duration=None, display="json"):
    if display not in ("json", "text"):
        raise ValueError("display debe ser json o text")
    pipeline = None
    output = None
    next_tick = source.now()
    origin = next_tick
    next_print = next_tick
    ticks = 0

    def publish(timestamp):
        nonlocal next_print, ticks
        state = pipeline.tick(timestamp)
        if output:
            output.send(state["osc"])
        if print_interval > 0 and timestamp >= next_print:
            if display == "text":
                diagnostic = (f" | muestras_recibidas={source.samples_received}" if hasattr(source, "samples_received") else "")
                print(readable_status(state, timestamp - origin) + diagnostic, flush=True)
            else:
                print(json.dumps(clean({"t": round(timestamp - origin, 2), "connected": state["status"]["connected"],
                                    "stale": state["status"]["stale"], "quality": state["status"]["global_score"],
                                    "valid": state["status"]["valid"], "calibrated": state["status"]["calibrated"],
                                    "condition": state["status"]["condition"],
                                    "reasons": state["status"]["reasons"], "features": state["features"],
                                    "visual": state["visual"]}), allow_nan=False), flush=True)
            next_print = timestamp + print_interval
        ticks += 1

    try:
        pipeline = Pipeline(source.metadata, config, record)
        output = OscOutput(osc_host, osc_port) if osc else None
        while not source.finished:
            block = source.read(1 / config.output_hz)
            if block is not None:
                # Publish past ticks before ingesting a future block (also in fast replay).
                while next_tick < block.received_at - 1e-8:
                    publish(next_tick)
                    next_tick += 1 / config.output_hz
                pipeline.ingest(block)
            now = source.now()
            while next_tick <= now + 1e-8:
                publish(next_tick)
                next_tick += 1 / config.output_hz
            if duration is not None and now - origin >= duration:
                break
    finally:
        if pipeline is not None:
            pipeline.close()
        source.close()
        if output:
            output.close()
    return {"output_frames": ticks, "valid_windows": pipeline.valid_windows,
            "invalid_windows": pipeline.invalid_windows, "baseline": pipeline.normalizer.to_dict(),
            "record": str(record) if record else None}
