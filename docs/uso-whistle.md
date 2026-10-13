# Usar el traductor con Whistle

Desde el 12 de octubre de 2026, el arranque sin opciones usa el perfil equilibrado: Whistle en CPU, audio del sistema y traducción de inglés a español.

```bash
cd /ruta/al/proyecto
./run.sh
```

Reproducir el video o la reunión en inglés. Las frases y sus traducciones aparecen juntas en la terminal. Para ver tiempos de reconocimiento y guardar el texto:

```bash
./run.sh --stats --save
```

El programa espera unos 0.8 segundos de pausa para cerrar el segmento. Si la persona habla sin parar, corta alrededor de 12 segundos, buscando un punto de menor energía en el último segundo. Después necesita ejecutar el reconocimiento y la traducción. Por eso no debe presentarse como subtítulos instantáneos: en habla continua puede tardar hasta el límite del segmento más la inferencia.

## Qué se corrigió

El streaming anterior descartaba voz de bajo volumen con un umbral fijo y podía tirar audio pendiente cuando se atrasaba. El perfil equilibrado usa un umbral adaptativo, conserva 300 ms antes del inicio detectado y procesa segmentos una vez. Aplica ganancia limitada a voces bajas; no amplifica más de 16 veces ni normaliza buffers casi silenciosos. Conserva el audio restante cuando corta un segmento.

La GPU no es necesaria. Los pesos de Whistle ocupan 16.9 MB; Python, dependencias, motor y paquetes de traducción ocupan espacio adicional. El consumo de toda la aplicación no equivale al tamaño del modelo.

## Opciones que ayudan en la práctica

```bash
# Listar fuentes; elegir otra si el audio sale por un dispositivo diferente
./run.sh --list
./run.sh --device NOMBRE_EXACTO

# Reducir el número de hilos en un equipo más limitado
./run.sh --threads 2

# Favorecer términos propios conocidos, uno por línea en un archivo UTF-8
./run.sh --keywords vocabulario.txt

# Comparar con Faster Whisper small, conservando su motor anterior
./run.sh --model small --stats --save
```

El vocabulario puede contener nombres de productos o personas que realmente se esperan. Whistle favorece esos términos; no garantiza que los reconozca ni corrige todo el texto. No rellenarlo con listas extensas de palabras ajenas a la conversación.

`--pause` y `--segment` permiten ajustar el equilibrio si hace falta. Pausas más cortas publican antes, pero pueden dividir una idea y perjudicar la traducción. El perfil antiguo `--profile light` conserva la salida incremental y sus mayores costes de reprocesamiento; no es el perfil recomendado para esta laptop tras la comparación.

## Pruebas y resultados

Se descargaron 12 clips de LibriSpeech y 8 de FLEURS, con sus transcripciones. LibriSpeech en este conjunto contiene una sola voz; FLEURS añade otras muestras de habla. No se contó el número de hablantes únicos ni se simuló una reunión con solapamiento de voces.

La comparación continua usa seis de esos clips, unidos con pausas de medio segundo: 56.995 segundos y 128 palabras de referencia. Las palabras se normalizan a minúsculas, se elimina puntuación y `Mr` se convierte en `mister`; se mantienen otras diferencias, como contracciones. Se mide distancia de edición de palabras, no calidad de traducción.

| Medida, misma pista continua | Streaming instalado antes | Perfil equilibrado final |
|---|---:|---:|
| Errores de palabras | 74/128 (57.8 %) | 23/128 (18.0 %) |
| Tiempo acumulado de inferencia ASR | 29.79 s | 9.79 s |
| Tiempo total, incluido replay a velocidad real | 60.58 s | 58.45 s |
| Inferencia por pasada, percentil 95 | 2.00 s | 2.17 s |

El nuevo perfil hace menos pasadas, con más audio cada una. Ese es el motivo de reducir el cálculo total aunque una pasada individual pueda tardar más. Los resultados son de esta pista y este equipo, no una cifra universal de precisión o ahorro.

La captura real por PulseAudio/PipeWire con el perfil final, reconocimiento, traducción y guardado midió 232 MiB de pico sumando los procesos vivos. Reconoció la frase completa del clip JFK y produjo su traducción; el sink temporal se retiró al terminar. La memoria observada no es un mínimo de RAM requerido para el sistema operativo y el resto de aplicaciones.

También se probaron silencio, ruido estacionario leve, datos inválidos, límites de parámetros y una llamada real con vocabulario. Los nombres propios, voces difíciles y frases cortadas siguen produciendo errores. La traducción puede propagar un error de reconocimiento.

## Decisión sobre el motor residente

Se probó la API C oficial con el modelo cargado en memoria. Su transcripción completa mantuvo los mismos errores que el CLI en los 12 clips de LibriSpeech. El streaming nativo utilizó más CPU y necesitó 90.55 segundos de cálculo para 54 segundos de audio en el ensayo de seis clips. El ensayo limitado a cuatro CPUs también quedó por debajo del requisito de tiempo real y se interrumpió. No se instaló esa biblioteca como motor de producción.

Equipo: i5-12500H, Linux x86_64. Whistle y el traductor compacto corrieron en CPU. Versiones del entorno: NumPy 2.5.3, CTranslate2 4.8.2 y SentencePiece 0.2.2. Pesos y motor conservan las revisiones fijadas previamente; consultar hashes en la carpeta del ensayo.

## Antes de publicar el artículo

Probar un video propio de referencia o una conversación pública durante varios minutos. Anotar errores de términos técnicos, retraso percibido y pausas que parten frases. No afirmar que se probaron entrevistas, reuniones privadas, siete idiomas o todos los equipos a partir de estas muestras en inglés. La aplicación actual está validada en Linux con PulseAudio/PipeWire; no se ha portado la captura a Windows o macOS.

Fuentes: [Whistle y su API](https://huggingface.co/Cactus-Compute/whistle), [implementación oficial](https://github.com/cactus-compute/needle), [FLEURS, CC BY 4.0](https://huggingface.co/datasets/google/fleurs), [LibriSpeech usado en la prueba](https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy).
