# Grabación EEG real incluida

Fuente: archivo `OpenBCI_GUI-v6-meditation.txt`, distribuido como muestra de EEG por el [repositorio oficial OpenBCI GUI](https://github.com/OpenBCI/OpenBCI_GUI/tree/e23869e7b5cc621e733d8fa0d81f05d477264306/OpenBCI_GUI/data/EEG_Sample_Data). El nombre «meditation» es el nombre original del archivo; no constituye una clasificación mental realizada por Neurovisual.

Se incluyen 15,000 filas consecutivas desde la fila de datos 7,500 hasta la 22,499: aproximadamente del segundo 30 al 90 de la grabación. Se empieza después del periodo inicial de ajustes y movimiento, con el propósito de demostrar el procesamiento. No se usa este recorte para justificar una conclusión experimental. La duración convertida es 60.012 s debido a tres muestras ausentes en el contador.

## Metadatos comprobados

- Ocho canales, 250 Hz y placa `OpenBCI_GUI$BoardCytonSerial`: declarados en la cabecera original.
- EEG en microvoltios: formato OpenBCI Cyton; constantes de conversión en [BoardCyton.pde](https://github.com/OpenBCI/OpenBCI_GUI/blob/e23869e7b5cc621e733d8fa0d81f05d477264306/OpenBCI_GUI/BoardCyton.pde). Aceleración en g, conservada en las tres columnas auxiliares.
- `ch1` … `ch8` corresponden respectivamente a `EXG Channel 0` … `EXG Channel 7`, sin reordenar ni duplicar canales.
- Posiciones de electrodos y referencia eléctrica: no documentadas en este archivo. No se asignan grupos anatómicos. Alfa posterior y lateral quedan indisponibles, con sus flags OSC correspondientes.
- No hay anotaciones de música/referencia. La «referencia» del programa sólo sirve para calibración técnica. Este archivo no permite estudiar un efecto musical.

## Conversión y conservación del original

Las medidas EEG y de aceleración se conservaron exactamente: no se filtraron, centraron ni interpolaron durante la conversión. Los grandes desplazamientos eléctricos de los electrodos permanecen en el registro crudo.

Los tiempos nativos son milisegundos de recepción, con 5,665 repeticiones en el fragmento. No pueden tratarse como timestamps únicos de muestras. Se creó un reloj relativo en segundos utilizando el contador de muestras de ocho bits, sus vueltas y la frecuencia explícita de 250 Hz. Los tres huecos del contador permanecen como huecos temporales; no se inventaron muestras. `received_at` utiliza el final nominal de cada bloque, de modo que replay aproxima el ritmo de adquisición, no el jitter del transporte original.

`original_excerpt.txt.gz` guarda las líneas originales del recorte, incluyendo cabecera, contador, todos los campos auxiliares y todos los timestamps nativos. Es un archivo comprimido; no hace falta abrirlo para ejecutar la demostración. `raw.jsonl` y `metadata.json` son la versión preparada para el programa.

La conversión se puede repetir sin dependencias adicionales:

```bash
python scripts/prepare_openbci_demo.py --input ruta/al/OpenBCI_GUI-v6-meditation.txt --output carpeta-nueva --start 30 --duration 60
```

El script exige que el original coincida con su SHA-256 verificado. No hace falta ejecutarlo para probar el programa: los archivos preparados ya están incluidos.

## Procedencia y licencia

- Revisión fijada del repositorio: `e23869e7b5cc621e733d8fa0d81f05d477264306`.
- [Descarga del original completo](https://raw.githubusercontent.com/OpenBCI/OpenBCI_GUI/e23869e7b5cc621e733d8fa0d81f05d477264306/OpenBCI_GUI/data/EEG_Sample_Data/OpenBCI_GUI-v6-meditation.txt).
- Original completo: SHA-256 `54588140869b984562d20f95b1badd3dc4c25592d923f09e9becf30ff9121712`.
- Recorte original descomprimido: SHA-256 `acc641a3c3a6b9ac645fa279c89928a92989e9d725f1aae38ba415fc38a9618e`.
- El repositorio oficial distribuye el material bajo licencia MIT, copyright OpenBCI. Se conserva el aviso completo en [LICENSE.txt](LICENSE.txt). No se encontró una licencia distinta para este archivo de ejemplo.

La prueba valida compatibilidad del procesamiento con esta grabación. No verifica un Unicorn, diagnóstico clínico, exactitud de todas las sospechas de artefacto ni emociones.
