# Modelos, recursos y vocabulario

## Tres tamaños disponibles

```bash
./run.sh --live --model base --offline --save
./run.sh --live --model small --offline --save
./run.sh --live --model medium --offline --save
```

`base` es el menor de estos tres; `small`, el intermedio; `medium`, el mayor. Whistle es otro motor con los pesos configurados actualmente, no tres variantes de esos tamaños. No se descargaron modelos nuevos para esta comparación: se reutilizaron los tres ya presentes.

El visor muestra el motor, dispositivo, precisión numérica y número de pistas cargadas. Cambiar el modelo requiere reiniciar el proceso; la vista no hace cambios de modelo en caliente. Abrir la URL nueva después de reiniciar.

El selector recomienda base en vivo y ofrece medium por segmentos. Medium en streaming es experimental: la comparación de clips completos no lo validó como opción de baja latencia. En una ejecución de uso real, su visor permaneció seis segundos sin actualización durante la observación; el proceso estaba en CUDA, con unos 1080 MiB de VRAM y sin swap propio. Eso no mide la latencia de cada frase ni excluye influencia del contenido de audio y de la carga del equipo.

El visor nuevo muestra audio analizado, duración de la pasada ASR y cola aproximada de captura. Estos indicadores permiten distinguir cálculo lento y cola acumulada. La cola no representa el tiempo total hasta confirmar palabras o traducirlas. El modo por segmentos calcula cada segmento una vez, pero espera un cierre por pausa o longitud: tampoco es instantáneo.

## Comparación ejecutada

12 de octubre de 2026, i5-12500H, RTX 3050 4 GiB, Linux. 12 muestras de LibriSpeech y 8 de FLEURS en inglés: 191,67 s, 444 palabras de referencia. Una pasada por muestra y modelo, configuración común. LibriSpeech tiene una sola voz en este subconjunto; no se midió una reunión con conversaciones superpuestas.

Configuración: CUDA, int8_float16, beam=3, temperatura 0, timestamps de palabra, VAD activo, contexto de texto previo desactivado y umbral de posibles alucinaciones en silencio de 1 s. Los resultados miden ASR de clips completos; no incluyen traducción ni navegador ni son latencia de streaming.

| Medida | base | small | medium |
|---|---:|---:|---:|
| Errores / 444 palabras | 39 | 42 | 29 |
| WER | 8,78 % | 9,46 % | 6,53 % |
| Cálculo ASR total | 11,94 s | 20,32 s | 38,01 s |
| Cálculo / duración de audio | 0,062 | 0,106 | 0,198 |
| Pico RAM del proceso | 847 MiB | 897 MiB | 1680 MiB |
| Pico VRAM del proceso | 280 MiB | 504 MiB | 1240 MiB |
| Carga del modelo | 1,47 s | 3,33 s | 14,14 s |
| p95 de cálculo por clip | 1,04 s | 1,75 s | 3,17 s |

RSS incluye Python, bibliotecas y modelo. VRAM se tomó por PID cada 250 ms con nvidia-smi; puede omitir picos breves. El traductor preexistente siguió activo. Carga y tiempos dependen de caché, RAM libre y otras tareas; no atribuir una diferencia pequeña al modelo sin más pruebas.

Interpretación: base fue la opción de menor coste y obtuvo un resultado parecido a small en este conjunto. Medium redujo errores, con aproximadamente 3,18 veces el cálculo de base. Para uso en vivo hay que comprobar si mantiene el ritmo del audio: una pasada sobre un clip completo no predice el coste de reprocesar ventanas solapadas.

La interfaz diaria usa beam=1 por defecto para responder antes. `--beam-size 3` permite elegir el ajuste utilizado en el benchmark. Cambiar beam puede alterar precisión, memoria y tiempo. Para comparar por segmentos con ese ajuste:

```bash
./run.sh --model medium --beam-size 3 --mode phrase --view web --offline --save
```

Informes, fuentes del ensayo y logs: `benchmarks/2026-10-12-models-vocabulary/`. Los pesos llevan las revisiones fijadas en cada JSON. Versiones: faster-whisper 1.2.1, CTranslate2 4.8.2, NumPy 2.5.3, tokenizers 0.23.2, ONNX Runtime 1.29.0 y SentencePiece 0.2.2.

## Vocabulario compartido

`--keywords ARCHIVO` carga nombres que se esperan, una línea por término. Se admite UTF-8, hasta 8 KiB y 100 líneas. Evitar listas de palabras comunes: la pista puede sesgar el resultado aunque el término no se pronuncie.

```bash
./run.sh --live --model small --keywords vocab/tech-example.txt --save
```

En Whisper se pasan a `hotwords`, una función nativa del backend. En Whistle se utiliza `--audio-keywords`. No se añadió un modelo extra para ello. La cadena de pistas consume parte del contexto del modelo; una lista demasiado larga puede ser truncada por el backend.

El ensayo histórico incluyó seis pistas, una de ellas omitida del registro público. Se conservan `Warp Terminal`, `Excalidraw`, `Mr. Quilter`, `Javanese` y `Colombia`. Tres términos corresponden al contenido del corpus; las aplicaciones de ejemplo no se pronuncian en esas muestras. Los errores bajaron de 42 a 37/444 y no aparecieron las aplicaciones ausentes. El cálculo subió de 20,32 a 21,89 s y la VRAM quedó en 504 MiB. No equivale a validar audio humano de referencia pronunciando esas aplicaciones: esa comprobación forma parte de la guía manual de publicación.

## Agrupación y conservación de nombres

Si un límite de palabras cae dentro de un término del vocabulario, el cierre se desplaza al final del término. La prueba comprobó `GitHub Actions` en la palabra 22/23: quedó en el mismo bloque. Esto evita dividir nombres compuestos; no es un analizador semántico de oraciones.

Antes de traducir, los términos reconocidos se sustituyen por marcadores y se restauran después. El original no se reescribe. Si la traducción pierde o duplica un marcador, se utiliza la traducción normal del texto original; no se inventa un nombre para rellenarlo. No se garantiza conservación en ese fallback, por lo que la prueba lo registra.

Prueba con el traductor compacto real, cinco frases escritas, siete apariciones de nombres:

| Ejemplo | Antes | Con vocabulario |
|---|---|---|
| We use Laravel and GitHub Actions. | Usamos acciones de Laravel y GitHub. | Usamos Laravel y GitHub Actions. |
| Open Warp Terminal and run Docker Compose. | Open Warp Terminal y ejecutar Docker Compose. | Abra Warp Terminal y ejecute Docker Compose. |

Se conservaron las siete apariciones y no hubo fallbacks en esas frases. Es una comprobación de términos y ejemplos de traducción, no una evaluación humana completa de traducción. Los tiempos de la llamada protegida fueron 0,35–0,74 s, incluyendo el traductor; no se aisló un porcentaje de sobrecoste del wrapper.

Fuente de la función nativa: [faster-whisper transcribe](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py). Corpus y atribuciones: [FLEURS](https://huggingface.co/datasets/google/fleurs) y [LibriSpeech dummy](https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy).
