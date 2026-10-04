# Usar Neurovisual en Windows, paso a paso

No necesitas programar ni tener el Unicorn para realizar esta prueba. Ya se incluye una grabación EEG real de OpenBCI, de ocho canales y unos 60 segundos. Nuestro programa leerá la grabación, calculará valores y enviará controles OSC. Verás números y estados; el visual artístico definitivo todavía no está construido.

## La primera prueba, con doble clic

1. Instala **Python 3.12 o 3.13 de 64 bits** desde [python.org](https://www.python.org/downloads/windows/). Si el instalador ofrece «Add Python to PATH», márcalo. Permite también instalar el lanzador `py`.
2. Abre [el repositorio en GitHub](https://github.com/Ipavlokz/artilichys), pulsa el botón verde **Code** y selecciona **Download ZIP**. Si ya tienes una copia con Git, puedes actualizarla con `git pull`.
3. Haz clic derecho sobre el ZIP y elige **Extraer todo**. Abre la carpeta extraída que contiene `README.md`, `GUIA_WINDOWS.md` y `PROBAR_EEG.cmd`. No ejecutes el archivo desde dentro del ZIP.
4. Haz doble clic en **`PROBAR_EEG.cmd`**. La primera vez prepara Python y descarga las herramientas de cálculo. Necesitas Internet durante esa instalación; la grabación ya viene incluida.
5. Deja abierta la ventana. Tras la instalación comenzará una reproducción de unos **60 segundos**. Verás una línea de estado aproximadamente cada segundo.
6. Al terminar, la ventana muestra **«Prueba terminada»** y la carpeta donde guardó los resultados. Cada ejecución crea una carpeta nueva dentro de `sessions`.

El archivo `.cmd` es una lista de instrucciones para Windows: automatiza exactamente los comandos explicados a continuación. No instala drivers del Unicorn ni cambia la política de PowerShell.

## Qué significan los resultados

Al principio verás algo parecido a:

```text
0.0 s | conexion=NO | calidad=0.00 | calibracion=PENDIENTE | ventana=INVALIDA
```

Es normal: todavía no han llegado las primeras muestras al procesamiento. Aquí «conexión» describe la fuente de reproducción, no un Unicorn conectado físicamente.

El programa debe reunir datos limpios para calibrarse. En esta grabación real empieza a producir controles válidos aproximadamente a los **18 segundos**; puede rechazar otras ventanas después. No asumas que todas las muestras grabadas son buenas.

Una línea posterior puede verse así; estos números son ilustrativos:

```text
ventana=VALIDA | alpha=0.56 beta=0.59 theta=0.36 | color=0.52 intensidad=0.56 flujo=0.50
```

| Palabra | Significado sencillo |
| --- | --- |
| `conexion=SI` | La fuente está entregando datos; en esta prueba es un archivo |
| `calidad=1.00` | Los indicadores heurísticos de esa ventana no señalan un fallo |
| `calibracion=LISTA` | Ya hay una referencia personal con la que comparar |
| `ventana=VALIDA` | Se pueden actualizar los controles con esos datos |
| `alpha`, `beta`, `theta` | Descriptores normalizados de la señal, entre 0 y 1 |
| `color`, `intensidad`, `flujo` | Números para controlar un futuro visual |
| `warming_up` | Se está reuniendo una ventana completa de datos |
| `suspected_artifact` | Hay una posible alteración de la medición; se descarta esa ventana |
| `amplitude:ch2` | El canal 2 tiene una variación excesiva |
| `motion` | La aceleración indica movimiento excesivo |
| `stale` | Dejaron de llegar muestras nuevas |

Un valor alfa de 0.8 no significa «80% de relajación». La calidad tampoco es una probabilidad ni un diagnóstico. Si la ventana se invalida, los controles conservan brevemente el valor y después vuelven suavemente a espera. Ver ventanas descartadas forma parte del funcionamiento esperado.

Esta grabación no informa las posiciones de los electrodos: por eso no se inventan alfa posterior ni balance lateral. Tampoco tiene anotaciones de música y no sirve para demostrar una respuesta musical.

## Hacer lo mismo escribiendo comandos

Una **terminal** es una ventana donde escribes instrucciones. Copia cada comando, pulsa Enter y espera a que termine antes del siguiente. No copies los símbolos que tu terminal ya muestra al inicio de la línea.

### 1. Abrir la terminal en la carpeta correcta

En el Explorador de archivos, entra en la carpeta que contiene `README.md`. Haz clic en la barra donde aparece su dirección, escribe `powershell` y pulsa Enter. Se abrirá PowerShell en esa carpeta.

Confirma dónde estás:

```powershell
Get-ChildItem README.md
```

Debe mostrar el archivo. Si dice que no existe, abriste la terminal en otra carpeta.

### 2. Preparar Python y el programa

```powershell
py --version
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

El primer comando muestra tu versión de Python. El segundo crea un entorno separado llamado `.venv`: es la carpeta donde estarán las herramientas de este proyecto. El tercero instala el programa y sus pruebas. Estos pasos se hacen una vez por copia del proyecto.

No necesitas «activar» el entorno: usamos directamente `.venv\Scripts\python.exe` en cada comando.

### 3. Comprobar que todo está instalado

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Espera un mensaje que termine en **`passed`**, acompañado del número de comprobaciones correctas. La cantidad puede aumentar con las actualizaciones; el resultado verificado está en [VERIFICATION.md](VERIFICATION.md). Si instalaste mediante el archivo de doble clic, instala primero `.[dev]` con el comando anterior para disponer de pytest.

### 4. Comprobar la grabación incluida

```powershell
.venv\Scripts\python.exe -m neurovisual inspect examples/recordings/openbci
```

Verás un resumen con `sample_rate: 250`, ocho nombres de canal y `samples: 15000`. Esto comprueba el archivo y su formato; todavía no está reproduciéndolo. Sus mediciones son reales y el reloj de reproducción se preparó a partir del contador original. La explicación y licencia están en [SOURCE.md](examples/recordings/openbci/SOURCE.md).

### 5. Reproducirla y guardar el resultado

```powershell
.venv\Scripts\python.exe -m neurovisual replay examples/recordings/openbci --display text --record sessions/mi-primera-prueba
```

Espera los 60 segundos. `--display text` muestra un estado legible. `--record` guarda el resultado en la carpeta indicada. La reproducción también envía OSC a esta computadora, en el puerto 9000, aunque todavía no hayas abierto un receptor.

Para repetir con registro usa otro nombre, como `sessions/mi-segunda-prueba`. El programa rechaza sobrescribir una carpeta existente para cuidar tus grabaciones. Para repetir sin guardar una copia del resultado:

```powershell
.venv\Scripts\python.exe -m neurovisual replay examples/recordings/openbci --display text
```

### 6. Ver los mensajes OSC

Abre **otra** terminal en la misma carpeta y ejecuta:

```powershell
.venv\Scripts\python.exe -m neurovisual listen
```

Debe decir `OSC escuchando en 127.0.0.1:9000`. Deja esa terminal abierta. En la primera terminal vuelve a ejecutar el comando de reproducción. La segunda mostrará mensajes como:

```text
/neuro/calibrated 1
/neuro/features/valid 1
/neuro/alpha 0.56
/visual/color 0.52
```

Hay muchos mensajes porque cada actualización transmite todos los valores. Es una comprobación de que las instrucciones salen y llegan al receptor. Para detener el receptor pulsa **Ctrl+C**. También puedes abrirlo haciendo doble clic en `ESCUCHAR_OSC.cmd`, después de preparar el programa.

### 7. Encontrar y reproducir tu resultado

Abre la carpeta `sessions/mi-primera-prueba` desde el Explorador. Estos son archivos de texto estructurado; no son audio ni video:

- `raw.jsonl`: medidas recibidas, sin filtros.
- `processed.jsonl`: señal filtrada.
- `quality.jsonl`: indicadores de calidad y motivos de rechazo.
- `features.jsonl`: características EEG calculadas.
- `events.jsonl`: eventos y sospechas de artefacto.
- `controls.jsonl`: instrucciones visuales y OSC.
- `metadata.json` y `baseline.json`: configuración y referencia de la sesión.

Puedes abrirlos con Bloc de notas para comprobar que existen; no necesitas entender todo su contenido para hacer la demostración. Para volver a procesar esa sesión:

```powershell
.venv\Scripts\python.exe -m neurovisual replay sessions/mi-primera-prueba --display text
```

## Cambiar qué mueve el color y cómo se llama el mensaje

Ahora puedes hacerlo sin programar. Ya viene una alternativa preparada en `examples/visual-custom.json`. Abre el receptor OSC como en el paso 6 y, en la otra terminal, escribe:

```powershell
.venv\Scripts\python.exe -m neurovisual replay examples/recordings/openbci --config examples/visual-custom.json --display text --record sessions/mis-colores
```

Este ejemplo usa **theta para el color**, **beta para la intensidad**, **alfa para el flujo** y **balance espectral para la coherencia artística**. Envía los controles con nombres como `/arte/tono` y `/arte/brillo`. Los mensajes EEG como `/neuro/alpha` conservan sus nombres. En pantalla seguirás viendo `color`, `intensidad` y `flujo`; lo que cambia de nombre es el mensaje que recibe el visual.

Para crear tu propia variante:

1. Abre la carpeta `examples`, copia `visual-custom.json` y llama a la copia `mis-reglas.json`.
2. Haz clic derecho sobre la copia y ábrela con **Bloc de notas**.
3. Para hacer que alfa mueva el color, cambia `"color": "theta"` por `"color": "alpha"` en la parte `visual_mapping`.
4. Para cambiar el nombre enviado, cambia `"color": "/arte/tono"` por `"color": "/mi_visual/color"` en la parte `osc_addresses`.
5. Conserva las comillas, comas y llaves, guarda y ejecuta el mismo comando sustituyendo `examples/visual-custom.json` por `examples/mis-reglas.json`. Usa un nombre de sesión nuevo, por ejemplo `sessions/mis-colores-2`.

JSON es el formato del archivo de opciones. Si falta una coma o escribes una entrada desconocida, el programa muestra un error; corrige el archivo y vuelve a ejecutar. Los nombres OSC deben empezar por `/`, ser distintos entre sí y no tener espacios, tildes ni `ñ`.

Hay seis entradas disponibles: `theta`, `alpha`, `beta`, `posterior_alpha`, `spectral_balance` y `lateral_balance`. Las dos que dependen de posiciones de electrodos (`posterior_alpha` y `lateral_balance`) no están disponibles en esta grabación. Si las eliges, su control queda en espera. El ejemplo `visual-custom.json` utiliza únicamente entradas disponibles en el archivo incluido.

El color enviado sigue siendo un número entre 0 y 1; el futuro visual decidirá a qué color concreto corresponde. Estas opciones no convierten las bandas en emociones. También se mantienen los bloqueos cuando la calidad falla.

Las opciones se guardan junto a la sesión. Al repetirla con `replay sessions/mis-colores --display text`, se recuperan automáticamente. Si quieres probar mezclas, `examples/visual-mix.json` contiene un ejemplo comentado en el README; para empezar basta con cambiar una entrada a la vez.

## Ensayar cómo marcar periodos con y sin música

Un **marcador** es una nota con una hora: por ejemplo, «aquí indiqué que empezó la música». Servirá para comparar periodos cuando tengamos EEG del Unicorn. Puedes practicar ahora con el simulador.

1. Después de instalar el programa, haz doble clic en **`ENSAYAR_MARCADORES.cmd`**. Se abre una sesión de tres minutos con EEG simulado y se crea una carpeta nueva para sus resultados.
2. Haz doble clic en **`MARCAR_MUSICA.cmd`**. Es una segunda ventana con un menú: **M** para música, **R** para referencia sin música y **S** para cerrar el menú.
3. Empieza sin música. En la primera ventana espera `calibracion=LISTA`. Conserva este periodo inicial de referencia durante unos 30 segundos.
4. Si quieres ensayar con audio, pon una canción en tu reproductor habitual y pulsa **M** en el menú. Espera una confirmación como `Marcador recibido: music`. La primera ventana mostrará `condicion=music`.
5. Tras unos 30–60 segundos, pausa la canción y pulsa **R**. Vuelve a esperar la confirmación. Repite si el tiempo restante lo permite.
6. Al terminar los tres minutos, la primera ventana muestra un informe y guarda `comparison.json` junto a los otros archivos de la sesión. **S** sólo cierra el menú; la sesión se detiene al cumplirse su duración o con Ctrl+C en su propia ventana.

El menú **no reproduce ni detiene música**. La hora corresponde a la recepción de tu anotación y puede retrasarse respecto al sonido real. En esta prueba, las mediciones vienen del simulador: aunque escuches música, no está midiendo tu cerebro y sus cambios siguen el programa sintético.

También puedes hacerlo con comandos. Primera terminal:

```powershell
.venv\Scripts\python.exe -m neurovisual run --duration 180 --manual-markers --display text --record sessions/ensayo-manual
```

Segunda terminal, cuando corresponda cada acción:

```powershell
.venv\Scripts\python.exe -m neurovisual mark music --label "Cancion de prueba"
.venv\Scripts\python.exe -m neurovisual mark reference --label "Musica pausada"
```

No copies los dos comandos de marcas de golpe: ejecútalos en momentos distintos. Una vez terminada la sesión, obtener el informe:

```powershell
.venv\Scripts\python.exe -m neurovisual compare sessions/ensayo-manual --display text --output sessions/ensayo-manual/comparison.json
```

El informe muestra, por canal y banda, **cambio observado**, **compatible con cambio pequeño** o **evidencia insuficiente**. La última etiqueta puede significar que faltan periodos limpios suficientemente largos. Ninguna etiqueta demuestra que la música haya causado un cambio ni mide emociones. Por ahora interpreta este ensayo como una prueba del funcionamiento del programa.

Las notas quedan guardadas y se conservan al reproducir `sessions/ensayo-manual`. No uses estas marcas actuales para afirmar que la grabación OpenBCI incluida se realizó con esa canción; esa grabación no tiene anotaciones musicales. Con el Unicorn conectado podremos usar la misma herramienta durante una sesión real, manteniendo postura, ojos y volumen constantes y repitiendo periodos.

## Probar fallos deliberados

La grabación real permite probar señal y sus problemas existentes. Para provocar específicamente una desconexión o un canal plano, usa el simulador:

```powershell
.venv\Scripts\python.exe -m neurovisual run --source simulated --scenario all --display text --record sessions/prueba-de-fallos
```

Dura 45 segundos. Incluye parpadeo sintético alrededor de 10 s, músculo a 14 s, movimiento a 18 s, canal plano a 22 s, faltantes a 26 s, desconexión a 30–32 s y datos detenidos a 36–38 s. Debe volver a obtener controles válidos al final.

Para una comprobación rápida que no respeta el tiempo de pared:

```powershell
.venv\Scripts\python.exe -m neurovisual replay examples/recordings/openbci --speed 0 --no-osc --display text
```

Este modo procesa todo en pocos segundos. Para observar OSC o mostrarlo durante el hackathon, usa la reproducción normal.

## Si aparece un error

| Mensaje o situación | Qué hacer |
| --- | --- |
| `py` no se reconoce | Instala Python con el lanzador `py` y vuelve a abrir la terminal |
| No existe `.venv\Scripts\python.exe` | Repite `py -3 -m venv .venv` desde la carpeta del proyecto |
| `No module named neurovisual` o falta NumPy/SciPy | Repite la instalación con el Python de `.venv` |
| No encuentra la grabación | Confirma que estás en la carpeta con `README.md`; descarga/extrae la versión actual completa del proyecto |
| La carpeta de sesión ya existe | Elige otro nombre después de `--record` |
| El puerto 9000 ya está en uso | Cierra el receptor OSC que abriste anteriormente |
| No ves OSC | Abre el receptor antes de reproducir y comprueba que ambas terminales usan el mismo puerto |
| Aparece `ventana=INVALIDA` | Lee los motivos; al principio y durante artefactos es esperado. En esta grabación habrá también ventanas válidas |
| `No llegó confirmación` al marcar | Comprueba que el ensayo sigue abierto con `--manual-markers`; consulta `events.jsonl` antes de repetir una marca de resultado incierto |

Por ahora no ejecutes `compare` sobre esta grabación para estudiar música: faltan esas anotaciones. El próximo paso con Unicorn es confirmar su salida y conectar su adaptador; esta demostración ya permite practicar el resto del recorrido.
