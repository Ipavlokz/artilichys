# Verificación de la fase 1

Verificado el 3 de octubre de 2026 (America/Mexico_City), en este workspace Linux. No se conectó un Unicorn. Windows tiene instrucciones y un workflow de CI, pero no se ejecutó manualmente en este entorno.

**Estado actual:** la suite tiene **82 pruebas**, todas correctas. Incluye una muestra oficial OpenBCI lista para reproducción, guía para principiantes en Windows, configuración de reglas visuales/nombres OSC y anotaciones manuales de música/referencia. Los resultados iniciales siguientes corresponden a la primera implementación; las verificaciones de las actualizaciones aparecen al final.

## Instalación y pruebas

- Python 3.12.14.
- NumPy 2.5.3, SciPy 1.18.1, python-osc 1.10.2; pytest 9.1.1.
- Instalación limpia en `.venv` mediante `python -m pip install -e '.[dev]'`: correcta.
- `python -m pytest -q`: **38 pruebas pasaron en 8.38 s**.
- `python -m pip check`: sin dependencias incompatibles.
- Compilación de módulos: correcta.

Pruebas significativas: metadatos incompletos/incoherentes, booleano de conexión explícito, forma de bloques, timestamps duplicados/invertidos/futuros, muestreo declarado erróneo, orden de canales, filtrado causal, continuidad entre bloques, atenuación de deriva/60 Hz y conservación de 10 Hz, potencia de bandas conocidas, faltantes/plano/IMU, parpadeo y separación de picos musculares, referencia personal/rangos, rechazo de controles, retención y espera, fuente detenida sin bloques, recuperación de conexión, persistencia de crudos rechazados, reproducción exacta, CSV/mapeo, CLI y OSC recibido por socket real.

## Demostraciones ejecutadas

### Todos los fallos, 45 segundos de señal

```bash
python -m neurovisual run --scenario all --duration 45 --speed 0 --no-osc --quiet --record sessions/faults-final
python -m neurovisual replay sessions/faults-final --speed 0 --no-osc --quiet --record sessions/replay-final
python -m neurovisual inspect sessions/faults-final
```

Resultados de simulación y replay: 676 frames de salida, 58 ventanas válidas y 147 inválidas; línea base lista. Se recibieron 10,242 muestras, 250 valores faltantes y 42 bloques desconectados. Se marcaron parpadeo, músculo, movimiento, canal plano y faltantes. Desconexión a 30.048 s, reconexión a 32.064 s; pausa de muestras detectada y reinicio a 38.064 s. El frame final a 45 s volvió a ser válido.

`raw.jsonl`, `processed.jsonl` y `features.jsonl` del replay son idénticos byte a byte a los originales. Los crudos incluyen los valores faltantes como `null` y los bloques vacíos de desconexión. El movimiento puede marcar también sospecha muscular: estas heurísticas no pretenden una clasificación exclusiva de artefactos.

### OSC local en tiempo real, procesos independientes

Se inició `python -m neurovisual listen --duration 14` y, tras confirmar que escuchaba, una simulación de 12 segundos con OSC y registro en `sessions/realtime-osc`.

- 180 bundles recibidos: cadencia de 15 Hz durante 12 s.
- 5,760 mensajes recibidos, con las 32 direcciones del contrato.
- 46 frames recibidos con `/neuro/features/valid=1` y `/neuro/calibrated=1`.
- Ambos procesos terminaron correctamente.

La suite verifica además tipos int/float y direcciones de eventos y características en un datagrama OSC real. El modo acelerado se probó sin OSC para evitar confundir la cadencia simulada con tiempo de pared.

### Comparación de condiciones conocidas

```bash
python -m neurovisual run --duration 96 --speed 0 --no-osc --quiet --record sessions/study-final
python -m neurovisual compare sessions/study-final --output sessions/study-final/comparison.json
```

Se seleccionaron 12 ventanas válidas no solapadas por condición. Cuatro resultados `cambio_observado`: alfa de ch1–4, con cambios de aproximadamente +187% a +188%, coherentes con la amplitud sintética programada. Los otros 20 resultados fueron `compatible_con_cambio_pequeno`; alfa ch5–8 cambió entre −0.16% y +0.59%. Este resultado comprueba controles conocidos del simulador, no una relación causal con música real.

### Ejemplo e importación

`inspect examples/sample.csv --metadata examples/sample.metadata.json --columns examples/columns.json` validó 100 muestras, ocho canales ordenados, 100 Hz y timestamps 0–0.99 s. El ejemplo es deliberadamente pequeño y no alcanza para la calibración.

Los registros de demostración quedan en `sessions/` de este workspace y se excluyen de Git. Los ejemplos pequeños, la suite, la configuración y esta evidencia sí están versionados. Usar directorios nuevos para repetir los comandos.

## Pendientes concretos

1. Confirmar modelo/montaje y la interfaz que realmente exporte Unicorn Suite Hybrid Black.
2. Implementar su transporte sobre `sources.base.Source` con frecuencia, unidades, orden y reloj confirmados.
3. Ejecutar la misma secuencia con una grabación real, desconexión y reconexión del dispositivo.
4. Ajustar umbrales de calidad/artefactos y comprobar latencia y salida OSC en el consumidor del evento.
5. Registrar audio y marcadores reales en bloques repetidos/controlados antes de interpretar cambios como asociados a música.

No se han verificado hardware, LSL/UDP del fabricante, exactitud clínica ni causalidad musical. La fase de software simulada y de reproducción sí es ejecutable y está probada.

## Actualización: grabación real OpenBCI y uso en Windows

Fuente: [muestra oficial OpenBCI GUI](https://github.com/OpenBCI/OpenBCI_GUI/tree/e23869e7b5cc621e733d8fa0d81f05d477264306/OpenBCI_GUI/data/EEG_Sample_Data), archivo original `OpenBCI_GUI-v6-meditation.txt`, bajo la licencia MIT del repositorio. Se incluyó un recorte de 15,000 mediciones, con los ocho canales originales a 250 Hz y acelerómetro. Procedencia, hashes, unidades y transformación temporal en `examples/recordings/openbci/SOURCE.md`.

El recorte ocupa unos 2.2 MB incluyendo el original comprimido. Conserva valores EEG/IMU sin prefiltrar y tres pérdidas de muestras del contador. El reloj relativo deriva del contador y la frecuencia declarada, ya que los timestamps nativos de recepción se repiten; todos los originales permanecen en el recorte comprimido. No se inventan posiciones de electrodos ni anotaciones musicales.

La grabación reveló casos ausentes del simulador inicial. Se corrigieron:

- Calidad de amplitud relativa a la mediana pasada del canal, manteniendo crudos intactos y rechazo de picos/plano.
- Inicialización causal del filtro con un pasado constante igual a la primera muestra, para evitar un transitorio artificial por grandes offsets de electrodos.
- Exclusión de la frecuencia de red de la proporción y amplitud empleadas para sospecha muscular.
- Reinicio del filtro y de la ventana ante un paquete perdido, incluso dentro de un bloque; conservación de todas las muestras crudas y procesadas recibidas.
- `inspect` ahora informa `timestamp_gaps`; `--display text` muestra estado y resumen legibles.

Comandos verificados:

```bash
python -m neurovisual inspect examples/recordings/openbci
python -m neurovisual replay examples/recordings/openbci --speed 0 --no-osc --display text --record sessions/openbci-real-check
python -m pytest -q
python -m pip check
```

Resultados actuales: **44 pruebas pasaron en 11.72 s**, sin dependencias incompatibles, y compilación correcta de módulos y del importador. La grabación produjo 901 frames, 117 ventanas válidas y 183 descartadas; referencia lista y primer frame válido alrededor de 18.33 s. `inspect` confirmó 15,000 muestras, tres huecos de timestamps y ningún valor individual faltante.

Se reprodujeron además los 60 segundos en tiempo real con un receptor UDP separado: **901 bundles OSC**, 32 direcciones, 275 frames con características válidas y 16 pulsos de sospecha muscular. Los registros crudos, procesados y de características resultaron idénticos byte a byte entre la reproducción rápida y la real. Las sospechas de artefacto no se han contrastado contra anotaciones expertas.

Los accesos `PROBAR_EEG.cmd` y `ESCUCHAR_OSC.cmd`, y `GUIA_WINDOWS.md`, se prepararon para Windows. La lógica Python está probada en Linux; los archivos de comandos Windows se revisaron, pero no se ejecutaron en una máquina Windows desde este entorno. El Unicorn y el experimento musical siguen pendientes de verificación.

## Actualización: reglas visuales y nombres OSC configurables

Se añadieron `visual_mapping` y `osc_addresses` a la configuración, manteniendo los valores iniciales. Se pueden seleccionar entradas, combinar pesos e invertir respuestas sin editar Python. Las posiciones anatómicas desconocidas dejan el control dependiente en espera. Las direcciones EEG permanecen reservadas; los nombres visuales se validan para evitar colisiones. La configuración artística se registra y se recupera al reproducir; las opciones parciales conservan los filtros guardados. Se acepta JSON UTF-8 con BOM para archivos guardados desde editores de Windows.

Verificaciones ejecutadas en Linux:

- `python -m pytest -q`: **65 pruebas pasaron en 15.90 s**.
- `python -m pip check`: sin dependencias incompatibles; no se añadieron dependencias.
- Compilación de `neurovisual` y `tests`, y `git diff --check`: correctas.
- 21 pruebas nuevas: selección y mezcla de entradas, inversión, balance lateral, calidad/retención/recuperación, disponibilidad anatómica, errores claros, persistencia y cambios parciales, recepción UDP con nombres personalizados y conservación de los datos EEG reales al cambiar el arte.

Grabación real con el ejemplo nuevo:

```bash
python -m neurovisual replay examples/recordings/openbci --config examples/visual-custom.json --speed 0 --no-osc --display text --record sessions/visual-custom-check
python -m neurovisual replay sessions/visual-custom-check --speed 0 --no-osc --quiet --record sessions/visual-custom-replay-check
```

Ambas ejecuciones produjeron 901 actualizaciones, 117 ventanas válidas y 183 descartadas, con referencia lista. Los archivos `raw.jsonl`, `processed.jsonl`, `quality.jsonl`, `features.jsonl`, `events.jsonl`, `controls.jsonl` y `baseline.json` fueron idénticos byte a byte. El replay recuperó theta → color y `/arte/tono` desde los metadatos.

Una simulación de 12 segundos con parpadeo, `examples/visual-custom.json` y receptor UDP independiente produjo **180 bundles**, 32 direcciones por bundle, 19 frames con características válidas y un pulso en `/arte/pulso`. Se recibieron las seis direcciones `/arte/...`; todos los controles continuos permanecieron en 0–1. La frecuencia nominal de salida fue 15 Hz.

Los ejemplos `visual-custom.json` y `visual-mix.json` y sus comandos están explicados en README y GUIA_WINDOWS. No se ha ejecutado esta actualización en una computadora Windows ni en un Unicorn físico desde este workspace.

## Actualización: anotaciones manuales e informe legible

Se añadió `ManualMarkedSource`, un wrapper del contrato de fuentes con recepción local de anotaciones, sin cambiar la señal ni sus timestamps. `run/replay --manual-markers` recibe comandos `mark music/reference`; exige tiempo real y registro. El operador inicia sin música y las anotaciones reemplazan las condiciones anteriores. La respuesta confirma el timestamp de la fuente y la incorporación al siguiente bloque elegible. Se agregó `compare --display text`, sin cambiar el informe JSON ni su interpretación descriptiva.

Verificaciones:

- `python -m pytest -q`: **82 pruebas pasaron en 24.76 s**, en Linux.
- 17 pruebas nuevas cubren reloj absoluto, orden de marcas/bloques, conservación de muestras, ausencia de datos y desconexión, rechazo si la fuente termina antes de incorporar la marca, recepción y confirmación UDP, receptor ausente, argumentos incompatibles, esquema de archivo y reemplazo de condiciones, liberación del puerto ante configuración inválida, reproducción y comparación de señal conocida.
- Compilación de módulos y `git diff --check`: correctas. `pip check`: sin dependencias incompatibles. No se añadieron dependencias.
- El ensayo automatizado de 96 segundos de señal simulada, con anotaciones por UDP y ejecución acelerada mediante el reloj de prueba, recuperó el cambio alfa de ch1–4 y conservó byte a byte crudos, características, eventos y controles al reproducirse. El modo acelerado es sólo de la prueba del wrapper; la CLI manual exige velocidad 1.

Se ejecutaron además procesos independientes en tiempo real durante 18 segundos, con 4,500 muestras simuladas. Dos invocaciones reales de `mark` obtuvieron confirmación: `music` a 10.564 s y `reference` a 14.644 s, más la referencia inicial a 0 s. Los registros conservaron las etiquetas y su origen manual; nunca aparecieron marcas posteriores a `received_at` en un bloque. Hubo 70 ventanas EEG válidas y 30 ventanas etiquetadas como transición.

```bash
python -m neurovisual run --duration 18 --manual-markers --display text --no-osc --record sessions/manual-markers-realtime
# En otra terminal, con separación temporal:
python -m neurovisual mark music --label "Ensayo de anotacion; EEG simulado"
python -m neurovisual mark reference --label "Fin del periodo"
python -m neurovisual compare sessions/manual-markers-realtime --display text --output sessions/manual-markers-realtime/comparison.json
python -m neurovisual replay sessions/manual-markers-realtime --speed 0 --no-osc --quiet --record sessions/manual-markers-replay-check
```

El ensayo ejecutado usó un puerto local libre pasado en `--marker-port` y `mark --port`; los comandos anteriores muestran el puerto inicial 9001. `raw.jsonl`, `processed.jsonl`, `quality.jsonl`, `features.jsonl`, `events.jsonl` y `baseline.json` resultaron idénticos byte a byte al reproducirlo. `compare` seleccionó cuatro ventanas de referencia y una de música: mostró correctamente evidencia insuficiente en los 24 resultados, ya que el ensayo breve verifica transporte y registro y no alcanza el mínimo de cinco por condición. Los controles en tiempo real y replay pueden tener distinta fase de ticks OSC; la cronología de las mediciones y marcas se conserva.

Se prepararon `ENSAYAR_MARCADORES.cmd` y `MARCAR_MUSICA.cmd`, con instrucciones en GUIA_WINDOWS. Los accesos Windows se revisaron, pero no se ejecutaron en Windows desde este entorno. Las anotaciones son manuales y no verifican el audio ni su inicio acústico; el retraso del operador y del comando sigue pendiente de una sincronización automática. El Unicorn físico y un experimento musical humano continúan pendientes.
