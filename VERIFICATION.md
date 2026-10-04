# Verificación de la fase 1

Verificado el 3 de octubre de 2026 (America/Mexico_City), en este workspace Linux. No se conectó un Unicorn. Windows tiene instrucciones y un workflow de CI, pero no se ejecutó manualmente en este entorno.

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
