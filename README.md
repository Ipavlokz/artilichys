# Neurovisual — fase 1

Pipeline EEG ejecutable sin hardware: ocho canales simulados o grabados → registro crudo → calidad y artefactos → filtros causales → descriptores espectrales → línea base personal → controles → OSC UDP. No reproduce música ni dibuja el visual definitivo. Los consumidores reciben el mismo contrato al cambiar de fuente.

**Las bandas son descriptores de señal. No se infieren emociones, valencia ni activación.** El Unicorn, su montaje y la interfaz de Unicorn Suite / Hybrid Black todavía deben confirmarse. Los 250 Hz y los grupos de canales del simulador son elecciones sintéticas, nunca especificaciones del hardware.

## Inicio rápido en Windows

Instalar Python 3.10 o posterior (se recomienda 3.12), Git y ejecutar en PowerShell dentro del repositorio:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m neurovisual run --source simulated --scenario all --record sessions/demo
```

Se puede usar directamente el ejecutable del entorno sin cambiar la política de ejecución de PowerShell. En Linux/macOS: `python3 -m venv .venv`, `.venv/bin/python -m pip install -e '.[dev]'`; sustituir `python` en los comandos siguientes por el ejecutable del entorno o activar el entorno. Dependencias de ejecución: NumPy, SciPy y python-osc. Pytest sólo se usa para pruebas. No hacen falta Docker, drivers ni SDK del Unicorn para esta fase.

En otra terminal, antes de iniciar la sesión, abrir el receptor:

```powershell
.venv\Scripts\python.exe -m neurovisual listen --port 9000
```

La simulación dura 45 segundos por defecto y muestra un resumen JSON cada segundo. Primero llena la ventana, descarta el arranque de los filtros y recoge cinco segundos de características válidas de referencia. Los controles comienzan tras aproximadamente nueve segundos; `/neuro/calibrated` y `/neuro/features/valid` indican su disponibilidad. `Ctrl+C` cierra los registros. OSC sale a `127.0.0.1:9000`; configurar `--osc-host` y `--osc-port` para otro receptor.

## Comandos

```bash
# Sesión limpia, con cambios graduales conocidos y marcadores sintéticos
python -m neurovisual run --source simulated --duration 45 --record sessions/clean

# Todos los fallos y parámetros reproducibles
python -m neurovisual run --sim-config examples/simulator.json --config examples/config.json --record sessions/faults

# Un fallo, o varios mediante repetición de --scenario
python -m neurovisual run --scenario blink --scenario missing --record sessions/two-faults

# Validar todos los bloques, orden de timestamps, esquema y resumir
python -m neurovisual inspect sessions/faults

# Reprocesar los crudos usando la configuración guardada y el ritmo original
python -m neurovisual replay sessions/faults --record sessions/reprocessed

# Importar CSV con columnas explícitas
python -m neurovisual inspect examples/sample.csv --metadata examples/sample.metadata.json --columns examples/columns.json
python -m neurovisual replay examples/sample.csv --metadata examples/sample.metadata.json

# Verificar rápidamente sin envío OSC (speed 0 = sin esperar)
python -m neurovisual run --scenario all --speed 0 --no-osc --quiet --record sessions/fast

# Comparación de condiciones con controles sintéticos conocidos
python -m neurovisual run --duration 96 --speed 0 --no-osc --quiet --record sessions/study
python -m neurovisual compare sessions/study --output sessions/study/comparison.json
```

Los directorios de salida deben ser nuevos: nunca se sobrescribe una sesión existente. `run` guarda por defecto en `sessions/<fecha>_<id>`; `--no-record` permite una ejecución efímera. `replay` sólo guarda otra sesión cuando se pasa `--record`. `--quiet` oculta el estado periódico, pero conserva el resumen final. `--speed 2` reproduce a doble velocidad; para consumidores visuales usar `--speed 1`. El modo acelerado puede saturar UDP y no conserva la cadencia de pared del OSC.

El ejemplo CSV tiene un segundo de señal: permite validar/importar, pero no alcanza para calibrar. Una grabación de demostración útil necesita al menos diez segundos limpios iniciales.

## Arquitectura y separación

```text
neurovisual/
  model.py              metadatos y bloques; unidades internas explícitas
  sources/base.py       contrato de fuente en vivo y temporización de archivos
  sources/simulated.py  ocho canales, bandas y fallos programables
  sources/replay.py     sesión JSONL / CSV y validación completa
  sources/markers.py    anotaciones externas de condiciones
  acquisition.py        validación sin reordenar o reescribir timestamps/canales
  quality.py            faltantes, plano, amplitud y movimiento IMU
  processing.py         notch + Butterworth SOS causal con estado
  artifacts.py          sospecha de parpadeo y músculo
  features.py           potencias por canal/grupo y relaciones
  normalization.py      línea base robusta fija y suavizado
  mapping.py            controles, retención y vuelta gradual a espera
  output.py             contrato y bundles OSC
  recording.py          registros separados y serialización JSON estándar
  pipeline.py           coordinación; registro antes de validar/procesar
  runner.py             actualización OSC independiente de nuevas muestras
  analysis.py           comparación descriptiva de condiciones
  cli.py                run / replay / inspect / compare / listen
tests/                  pruebas de señal, fallos, reproducción, CLI y UDP real
examples/               configuración, CSV, metadatos, columnas y marcadores
.github/workflows/      pruebas en Linux y Windows
```

Cada adaptador publica `SourceMetadata` y `Block`. El procesamiento sólo consume ese contrato; nunca lee el transporte. El registro crudo se escribe y vacía al disco antes de validar o descartar una ventana. Los datos procesados, las características EEG, los eventos y los controles se guardan por separado. Una excepción de formato detiene la ejecución con un mensaje claro y deja el bloque recibido en el registro para diagnóstico.

## Procesamiento y tiempo

`examples/config.json` contiene todos los parámetros. Valores iniciales:

| Parámetro | Valor |
| --- | --- |
| Ventana espectral | 3 s |
| Características | 5 Hz, al siguiente bloque disponible |
| OSC | 15 Hz con suavizado exponencial de controles |
| Banda de estudio | 1–40 Hz |
| Butterworth | orden 4 en SOS |
| Notch de red | 60 Hz, Q=30, configurable o `null` |
| Descarte de arranque de filtro | 1 s |
| Datos detenidos | sin muestras nuevas durante 0.5 s |
| Línea base | 5 s de actualizaciones válidas en referencia |
| Suavizado | constante de tiempo 0.5 s |
| Calidad inválida | retención 1 s, vuelta a espera con constante 2 s |

Los filtros sólo usan pasado y presente, conservan estado entre bloques y se reinician al detectar discontinuidad de muestras o recuperación de conexión. Se exige una ventana íntegra posterior al descarte de arranque. Si el notch está por encima de Nyquist se omite, lo que queda registrado en `metadata.json`; la banda de estudio incompatible con el muestreo produce error. La frecuencia siempre procede de los metadatos de la fuente. Se comprueba además su concordancia con el paso mediano de timestamps (tolerancia 20% por bloque); saltos internos invalidan la ventana.

Una ventana falla si cualquier canal falta, es plano, supera la amplitud límite, presenta artefacto sospechoso, contiene discontinuidades o tiene movimiento excesivo. La calidad global es una media de indicadores heurísticos; **no es una probabilidad ni sustituye `/neuro/features/valid`**. Por seguridad se requieren los ocho canales válidos; no se reconstruyen canales ni se aplica ICA. Valores faltantes permanecen NaN en la señal procesada y `null` en JSON. Internamente el filtro mantiene el último valor para continuidad numérica durante un faltante; ninguna ventana afectada llega a extracción ni al visual.

Theta: 4–8 Hz; alfa: 8–13 Hz; beta: 13–30 Hz. Welch estima potencia en uV². Alfa posterior sólo existe si se declara el grupo `posterior`; balance lateral usa potencia alfa de los grupos `left` y `right`. Balance espectral: log(alfa/beta). La normalización usa mediana y MAD de referencia, con un intervalo mínimo para evitar dividir por variabilidad casi nula; se congela después de calibrar y limita las salidas a sus rangos. La línea base incluye ventanas solapadas: sirve para calibración artística, no como número de observaciones independientes para inferencia. Se recalibra iniciando una sesión nueva.

Los controles continuos sólo toman nuevos objetivos de ventanas válidas y calibradas. Con calidad inválida se congela el valor mostrado y después se aproxima a espera: color 0.5, intensidad 0.2, flujo 0.25, coherencia 0.5, escena 0. Los eventos se tratan aparte: un parpadeo sospechoso puede emitir un pulso visual aunque esa ventana EEG haya sido excluida. Nunca representa una emoción. La escena permanece en 0 en esta fase.

## Contrato OSC

Un bundle OSC inmediato por actualización. Flags/pulsos/escena son enteros; los valores continuos son float32. Cada pulso vale 1 una actualización y vuelve a 0; el consumidor debe detectar el flanco. UDP no garantiza entrega.

| Dirección | Rango / significado |
| --- | --- |
| `/neuro/connected` | 0/1, estado de conexión declarado por la fuente |
| `/neuro/quality/global` | 0–1, calidad heurística global |
| `/neuro/quality/ch1` … `/neuro/quality/ch8` | 0–1, según orden de `channels` |
| `/neuro/motion` | 0–1, aceleración dinámica IMU; 0 si no existe |
| `/neuro/stale` | 0/1, ausencia de datos nuevos o desconexión |
| `/neuro/theta`, `/neuro/alpha`, `/neuro/beta` | 0–1, potencia normalizada respecto a referencia personal |
| `/neuro/posterior_alpha` | 0–1, alfa del grupo posterior normalizada |
| `/neuro/spectral_balance` | 0–1, log(alfa/beta) normalizado |
| `/neuro/lateral_balance` | −1…1, (alfa izquierda − alfa derecha) / suma |
| `/neuro/event/blink`, `/neuro/event/muscle`, `/neuro/event/reconnect` | pulsos de sospecha de artefacto / recuperación |
| `/visual/color` | 0–1, objetivo basado en alfa |
| `/visual/intensity` | 0–1, objetivo basado en beta |
| `/visual/flow` | 0–1, objetivo basado en theta |
| `/visual/coherence` | 0–1, objetivo basado en alfa posterior; nombre artístico, no coherencia EEG |
| `/visual/pulse` | pulso derivado de parpadeo |
| `/visual/scene` | entero, 0 en esta fase |
| `/neuro/features/valid` | 0/1; incluye calidad, calibración y datos recientes |
| `/neuro/calibrated` | 0/1, línea base lista |
| `/neuro/motion/available` | 0/1, IMU válida disponible |
| `/neuro/posterior_alpha/available` | 0/1, grupo posterior declarado |
| `/neuro/lateral_balance/available` | 0/1, grupos laterales declarados |

Con características inválidas se conserva el último descriptor normalizado; leer siempre el flag de validez. Antes de calibrar los descriptores 0–1 valen 0.5 y el lateral 0. Si no hay posiciones confirmadas, alfa posterior queda en 0.5 y lateral en 0, con `available=0`. El visual continuo sigue la política de espera, no esos valores retenidos. Una fuente puede estar conectada y detenida a la vez: `connected=1`, `stale=1`.

## Grabaciones e importación

Una sesión contiene:

| Archivo | Contenido |
| --- | --- |
| `metadata.json` | schema_version=1, fuente, frecuencia, canales ordenados, unidades, grupos, auxiliares, configuración y coeficientes de filtros |
| `raw.jsonl` | todos los bloques recibidos, incluidos vacíos de desconexión |
| `processed.jsonl` | bloques filtrados y timestamps originales |
| `quality.jsonl` | indicadores por canal, movimiento, motivos y validez de ventana |
| `features.jsonl` | potencias uV² por canal, descriptores, normalizados, condición y validez |
| `events.jsonl` | sospechas de artefacto, marcadores y conexión |
| `controls.jsonl` | estado, características retenidas, eventos, controles y valores OSC por frame |
| `baseline.json` | límites robustos finales, duración válida y estado de calibración |

Cada línea cruda tiene este esquema (abreviado; `samples` realmente tiene ocho columnas):

```json
{"received_at": 0.048, "connected": true, "timestamps": [0.0, 0.004], "samples": [[1,2,3,4,5,6,7,8],[2,3,4,5,6,7,8,9]], "imu": null, "markers": []}
```

Timestamps y `received_at` son segundos del mismo reloj monotónico de la fuente; pueden comenzar en cero o ser absolutos. Los timestamps se preservan y deben ser finitos, únicos y crecientes. `received_at` es el tiempo de recepción, no sustituye timestamps de muestras. EEG interno en `uV`; IMU opcional con tres columnas de aceleración en `g`; faltantes como `null`. Un bloque desconectado lleva arrays vacíos y `connected=false`. No se inventan muestras para cubrir huecos.

CSV requiere encabezado, timestamp numérico en segundos y ocho canales. `--metadata` es obligatorio y `--columns` permite cualquier orden/nombre externo; el mapa enumera `timestamp` y todos los nombres internos. Sin mapa los encabezados deben coincidir exactamente. No se infieren frecuencia, unidades ni posiciones. El ejemplo de metadatos es **sintético**, no debe copiarse para Unicorn sin confirmar sus campos. CSV no contiene conexión ni IMU en esta fase: para conservarlos usar sesiones JSONL.

Replay temporiza según `received_at`, preserva timestamps y vuelve a ejecutar el pipeline usando por defecto la configuración guardada. Puede reproducirse el directorio o su `raw.jsonl` junto a `metadata.json`. `--config` permite reprocesar con otros filtros. No se restaura automáticamente `baseline.json`: la referencia se recalcula de los mismos crudos/condiciones, lo que permite verificar la reproducción. Para importar anotaciones reales: `replay ... --markers archivo.json`, con el esquema de `examples/markers.json` y timestamps del mismo reloj que la grabación.

## Cómo estudiar cambios asociados a música

El planteamiento necesita una comparación: observar alfa subir durante una canción también puede reflejar cerrar los ojos, movimiento, deriva, cansancio o ruido. La alternativa implementada guarda potencia por **canal y banda**, registra periodos `reference` / `music`, excluye artefactos y permite comparar sólo ventanas válidas completas de una condición, sin solapamiento.

`compare` exige al menos cinco ventanas por condición y calcula cambio de medianas en escala logarítmica y un intervalo bootstrap descriptivo del 95%. El umbral de cambio pequeño es ±20% de potencia. Etiquetas:

- `cambio_observado`: el intervalo queda fuera del margen de cambio pequeño.
- `compatible_con_cambio_pequeno`: el intervalo queda dentro de ese margen; no prueba que la música no afecte la señal.
- `evidencia_insuficiente`: faltan ventanas o la incertidumbre cruza los límites.

Esto no es una prueba causal: no ajusta comparaciones múltiples y las ventanas no solapadas todavía pueden tener dependencia temporal. Es una herramienta exploratoria para el hackathon. En el simulador, música/referencia alternan cada 12 s, ch1–4 aumentan alfa gradualmente y ch5–8 actúan como controles sin esa modulación. No se reproduce audio; esos marcadores sólo validan el programa. En datos reales los marcadores deben corresponder al inicio/fin real del audio, no al reloj supuesto del simulador.

Durante el evento conviene alternar bloques más largos (30–60 s), repetir condiciones, mantener postura y ojos constantes, registrar volumen/canción y contrabalancear el orden. Reservar la referencia inicial para calibrar. Mantener la misma normalización durante la comparación. Reportar descriptores, artefactos y evidencia limitada; confirmar o descartar un efecto musical requiere más datos y controles experimentales.

## Añadir una fuente Unicorn LSL o UDP

No se ha confirmado que Unicorn Suite Hybrid Black exporte LSL o UDP. No se incluye un adaptador que suponga un protocolo del fabricante. La interfaz de hardware está aislada en `sources/base.py`:

```python
from neurovisual.sources.base import Source
from neurovisual.runner import run
from neurovisual.config import Config

class ConfirmedUnicornSource(Source):
    # metadata: SourceMetadata, obtenida/verificada al conectar
    # finished: False mientras la fuente siga en ejecución
    # read(timeout): Block o None, retorna antes del timeout incluso sin datos
    # now(): segundos del mismo reloj usado en los bloques
    # close(): libera transporte y recursos
    ...

# Una vez implementados los métodos:
# run(ConfirmedUnicornSource(...), Config(), record="sessions/unicorn")
```

El ejemplo es un contrato, no un driver ejecutable. Para LSL se puede instalar el extra `python -m pip install -e ".[lsl]"` y usar `pylsl.StreamInlet.pull_chunk(timeout=...)`. Confirmar el stream exacto, consultar su frecuencia nominal y XML de canales, aplicar la corrección de reloj de LSL explícitamente y mapear los ocho canales. Para UDP usar un socket con timeout, validar el protocolo confirmado, frecuencia, secuencia, unidades y reloj; conservar huecos y no interpolar paquetes perdidos como si fueran datos reales. En ambos casos convertir unidades al entrar, declarar conexión y emitir bloques vacíos periódicos cuando la conexión cae. El `runner` sigue publicando OSC aunque `read` devuelva `None` por falta de datos.

El adaptador debe evitar bloqueos superiores al timeout y reconectar sin rebobinar timestamps; si el dispositivo reinicia su reloj, convertirlo a una cronología de sesión creciente y documentar esa transformación en los auxiliares. Los grupos `frontal`, `posterior`, `left` y `right` se configuran con nombres confirmados; nunca derivarlos del número de canal. Después registrar la opción en `cli.py`; adquisición, procesamiento, registros y receptores OSC se reutilizan sin cambios.

## Verificación y límites

Las pruebas cubren esquema, orden de canales/timestamps, filtro causal y estado entre bloques, supresión de deriva/red y conservación de alfa, bandas conocidas, faltantes, plano, movimiento, parpadeo, normalización, retención y espera, desconexión/recuperación, crudos de ventanas inválidas, reproducción exacta del procesamiento, temporización, CLI y bundles OSC recibidos por un socket UDP real. También verifican que la comparación recupera la modulación alfa simulada y sus controles.

Ejecutar `python -m pytest -q`. El resultado concreto del entorno está en `VERIFICATION.md`. GitHub Actions está configurado para Python 3.10/3.12 en Linux y Windows; configurar el workflow no implica que esas ejecuciones hayan pasado.

Pendiente con hardware: calidad de contacto real, impedancias si existen, unidades/montaje, transporte, latencia, pérdida/reconexión, reloj, comportamiento del notch y umbrales de artefactos. Las sospechas de parpadeo y músculo son heurísticas; sin canales frontales confirmados no se activa la de parpadeo. La aceleración detecta variación alrededor de la mediana y no cubre todo tipo de movimiento ni usa giroscopio. No hay rechazo experto, reconstrucción, causalidad musical demostrada ni validación clínica. El filtrado es causal, pero ventanas Welch de 3 s y dos etapas de suavizado implican latencia perceptible. La escritura cruda se vacía a disco por bloque, sin promesa de durabilidad ante corte eléctrico (`fsync` por bloque no se fuerza). Hub, navegador, TouchDesigner y Blender quedan como consumidores futuros.

## Lista para conectar hardware

- [ ] Modelo exacto del Unicorn y número de canales EEG efectivos.
- [ ] Nombre preciso de Unicorn Suite / Hybrid Black, versión, sistema operativo y SDK/licencia disponibles.
- [ ] Nombres y orden físico de los ocho canales; posiciones para grupos frontales/posteriores/laterales.
- [ ] Unidades y escala; confirmar conversión a uV con una grabación de prueba.
- [ ] Frecuencia de muestreo consultada en la fuente; concordancia con timestamps.
- [ ] Referencia eléctrica, tierra y montaje; sin suponer una referencia común.
- [ ] Interfaz realmente disponible: LSL, UDP, SDK u otra; formato y ejemplo de paquete/stream.
- [ ] Campos auxiliares: IMU, batería, contador, impedancia, unidades y orden.
- [ ] Timestamps: reloj, unidad, origen, corrección, reinicio, jitter y latencia de recepción.
- [ ] Desconexión y recuperación: timeout, huecos, contador, reinicio de reloj y reapertura del transporte.

## Procedimiento para el día del hackathon

1. Instalar con el README, ejecutar pruebas y abrir `listen` en otra terminal.
2. Ejecutar `--scenario all`; comprobar eventos, calidad, retención y recuperación, y guardar/reproducir la sesión.
3. Completar la lista de hardware; obtener primero un pequeño stream/archivo real y confirmar metadatos, antes de integrar su transporte.
4. Implementar el adaptador sobre `Source` con timeout y registrar los crudos. Validar esquema con `inspect`; verificar canales y unidades con señal/maniobras conocidas.
5. Obtener al menos diez segundos iniciales limpios de referencia y ajustar umbrales de calidad con datos reales. Confirmar OSC en el consumidor artístico.
6. Registrar periodos reales de música/referencia, repetir bloques controlados y ejecutar `compare`. Conservar crudos y anotaciones para revisar conclusiones.
