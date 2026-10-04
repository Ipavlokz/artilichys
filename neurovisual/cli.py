import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import uuid

from .analysis import compare_conditions
from .config import Config
from .runner import run
from .sources import ReplaySource, SimulatedSource
from .sources.markers import MarkedSource
from .sources.replay import inspect_source, session_manifest
from .sources.simulated import SCENARIOS


def json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def output_options(parser):
    parser.add_argument("--config", help="Configuración JSON del procesamiento")
    parser.add_argument("--record", help="Directorio nuevo de sesión")
    parser.add_argument("--osc-host", default="127.0.0.1")
    parser.add_argument("--osc-port", type=int, default=9000)
    parser.add_argument("--no-osc", action="store_true")
    parser.add_argument("--speed", type=float, default=1, help="1 = tiempo real, 0 = acelerado; OSC acelerado sólo para pruebas")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--markers", help="Marcadores reference/music con timestamps de la fuente")


def replay_options(parser):
    parser.add_argument("path", help="Directorio de sesión, raw.jsonl o CSV")
    parser.add_argument("--metadata", help="Metadatos JSON obligatorios para CSV")
    parser.add_argument("--columns", help="Mapa JSON: nombre interno -> encabezado CSV")


def parser_for_cli():
    parser = argparse.ArgumentParser(description="EEG: calidad, descriptores y controles artísticos OSC")
    commands = parser.add_subparsers(dest="command", required=True)
    simulate = commands.add_parser("run", help="Ejecutar simulador completo")
    simulate.add_argument("--source", choices=["simulated"], default="simulated")
    simulate.add_argument("--duration", type=float)
    simulate.add_argument("--sample-rate", type=float, help="Frecuencia explícita del simulador; no especificación del Unicorn")
    simulate.add_argument("--seed", type=int)
    simulate.add_argument("--scenario", action="append", choices=["all", *SCENARIOS])
    simulate.add_argument("--sim-config", help="JSON de amplitudes bands, schedule y otros parámetros del simulador")
    simulate.add_argument("--no-record", action="store_true")
    output_options(simulate)
    replay = commands.add_parser("replay", help="Reprocesar datos crudos a ritmo original")
    replay_options(replay)
    output_options(replay)
    inspect = commands.add_parser("inspect", help="Validar esquema y resumir grabación")
    replay_options(inspect)
    compare = commands.add_parser("compare", help="Comparar periodos music/reference por canal y banda")
    compare.add_argument("path")
    compare.add_argument("--output", help="Guardar informe JSON")
    listen = commands.add_parser("listen", help="Receptor OSC local para comprobar el contrato")
    listen.add_argument("--host", default="127.0.0.1")
    listen.add_argument("--port", type=int, default=9000)
    listen.add_argument("--duration", type=float, default=0, help="0 = hasta Ctrl+C")
    return parser


def main(argv=None):
    parser = parser_for_cli()
    args = parser.parse_args(argv)
    try:
        if args.command == "listen":
            from pythonosc.dispatcher import Dispatcher
            from pythonosc.osc_server import BlockingOSCUDPServer
            dispatcher = Dispatcher()
            dispatcher.set_default_handler(lambda address, *values: print(address, *values, flush=True))
            server = BlockingOSCUDPServer((args.host, args.port), dispatcher)
            server.timeout = 0.2
            end = time.monotonic() + args.duration if args.duration else float("inf")
            print(f"OSC escuchando en {args.host}:{args.port}", flush=True)
            try:
                while time.monotonic() < end:
                    server.handle_request()
            finally:
                server.server_close()
            return 0
        if args.command == "compare":
            report = compare_conditions(args.path)
            encoded = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
            if args.output:
                Path(args.output).write_text(encoded + "\n", encoding="utf-8")
            print(encoded)
            return 0
        if args.command == "run":
            params = json_file(args.sim_config) or {}
            for key in ("duration", "sample_rate", "seed"):
                if getattr(args, key) is not None:
                    params[key] = getattr(args, key)
            if args.scenario:
                params["scenarios"] = list(SCENARIOS) if "all" in args.scenario else args.scenario
            source = SimulatedSource(speed=args.speed, **params)
            record = None if args.no_record else args.record or str(Path("sessions") / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]))
            config = Config.load(args.config)
        else:
            source = ReplaySource(args.path, speed=0 if args.command == "inspect" else args.speed,
                                  metadata_path=args.metadata, column_map=json_file(args.columns))
            if args.command == "inspect":
                print(json.dumps(inspect_source(source), indent=2, ensure_ascii=False, allow_nan=False))
                return 0
            record = args.record
            if args.config:
                config = Config.load(args.config)
            elif Path(args.path).suffix.lower() != ".csv":
                config = Config(**session_manifest(args.path)["config"])
            else:
                config = Config()
        if args.markers:
            source = MarkedSource(source, args.markers)
        summary = run(source, config, record=record, osc_host=args.osc_host, osc_port=args.osc_port,
                      osc=not args.no_osc, print_interval=0 if args.quiet else 1)
        print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    except KeyboardInterrupt:
        print("Sesión detenida; archivos abiertos cerrados.")
        return 130
