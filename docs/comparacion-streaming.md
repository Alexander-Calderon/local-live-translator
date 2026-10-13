# Comparación de streaming

Ensayo del 12 de octubre de 2026. Se alimentaron en tiempo real seis clips públicos de LibriSpeech y seis de FLEURS, con 0,5 s entre clips y silencio final. Total: 126,805 s de replay y 271 palabras de referencia. Son voces de lectura, no una reunión con voces superpuestas. El scoring pasa a minúsculas, compara Mr como Mister y cuenta tokens alfabéticos sin puntuación.

Todos los brazos usaron los mismos pesos de Whisper small en CUDA, float16, beam=1, VAD y timestamps de palabras, sin condicionar por el texto previo. WhisperLive se fijó a la revisión f26bdd5294ace7d31020ca00e04e7b14c2b7d954. La integración usa Faster Whisper 1.2.1, un modelo precargado y detección de dispositivo con CTranslate2; WhisperLive original importa Torch y su transcriptor derivado de Faster Whisper.

| Medida | Streaming anterior | Backend WhisperLive original | Backend integrado |
|---|---:|---:|---:|
| Errores de palabras | 92 | 58 | 59 |
| WER | 33,95 % | 21,40 % | 21,77 % |
| Primer texto provisional desde inicio | 1,39 s | 1,94 s | 2,26 s |
| Pico RSS del proceso | 801 MiB | 1329 MiB | 851 MiB |
| Tiempo acumulado ASR | 66,44 s | 119,68 s | 118,86 s |

La integración redujo los errores del streaming anterior de 92 a 59 en este ensayo. Aumentó el pico de RAM en unos 50 MiB y el primer texto llegó unos 0,87 s después. Conservó prácticamente el resultado de WhisperLive original con unos 478 MiB menos de RSS, evitando cargar Torch para comprobar la GPU y evitando duplicar el modelo.

Se reutiliza la lógica de streaming de WhisperLive. Este proyecto añade la captura local, controles, traducción en CPU, protección de términos, lectura retenida y sesiones guardadas. El ahorro no proviene de cambiar los pesos de Whisper.

El ensayo mide ASR y política de streaming. Excluye traducción, navegador, servidor de controles y VRAM. El primer texto no es la latencia de cada palabra ni la de la traducción. Se ejecutó una pasada por brazo; para generalizar hacen falta más muestras y repeticiones. Los tres perfiles pueden seguir equivocándose con nombres propios.

## Cambios descartados

- Reducir el margen del streaming anterior a 10 ms e intentar deduplicar una palabra: 81 errores, WER 29,89 % en el mismo replay.
- Insertar únicamente HypothesisBuffer de Whisper Streaming en nuestro bucle: 88 errores, WER 32,47 %. El componente aislado no solucionó el tratamiento de buffers del bucle.

Estos candidatos no se activaron. El modo anterior sigue disponible solo como --stream-engine legacy, para comparar o investigar. Sus ajustes de intervalos, buffer y pausas no se aplican al nuevo backend.

## Fuentes y reproducción

- [WhisperLive y revisión fijada](https://github.com/collabora/WhisperLive/tree/f26bdd5294ace7d31020ca00e04e7b14c2b7d954).
- [LibriSpeech de prueba](https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy): primeras seis muestras clean/validation, hablante 1272.
- [FLEURS](https://huggingface.co/datasets/google/fleurs): primeras seis muestras en_us/validation; IDs fleurs-1548, fleurs-1620, fleurs-1510, fleurs-1578, fleurs-1652, fleurs-1531 según el manifiesto del ensayo.
- [Whisper Streaming](https://github.com/ufal/whisper_streaming): referencia de LocalAgreement y del candidato descartado.

Se conservaron código de replay, referencias, hashes, logs y eventos en benchmarks/2026-10-12-release/, fuera de Git. Los hashes y el código del backend preparado están en .runtime/whisperlive/manifest.json. Para una comparación propia, alimentar el mismo PCM16 mono de 16 kHz a cada backend, usar las mismas opciones y medir el texto confirmado, el primer provisional, RSS y tiempo ASR. Conservar los errores y el silencio de cierre.

El repositorio incluye bin/benchmark_streaming.py y el manifiesto público docs/streaming-corpus.json para repetir los dos brazos de la app. Con el entorno preparado y Whisper small descargado:

    python bin/benchmark_streaming.py --backend legacy --audio-dir .runtime/replay-data --download-audio --model small --device cuda --compute float16 --report .runtime/results/legacy.json
    python bin/benchmark_streaming.py --backend integrated --audio-dir .runtime/replay-data --model small --device cuda --compute float16 --report .runtime/results/integrated.json

La descarga de audio es explícita, comprueba el hash de origen y requiere ffmpeg para normalizarlo. El modelo debe estar en caché o indicarse como carpeta local. Los resultados y eventos se guardan fuera de Git. El harness mide ASR, sin grabar micrófono y sin iniciar la interfaz de controles.
