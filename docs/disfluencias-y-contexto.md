# Conversaciones con pausas, muletillas e interrupciones

Revisión de código y fuentes oficiales, 12 de octubre de 2026. No se instalaron modelos nuevos ni se midieron estos candidatos con audio de reuniones en esta revisión.

## Qué hace ahora el traductor

El modo `--live` genera hipótesis sobre el audio recibido. Confirma el prefijo coincidente entre dos pasadas y conserva el texto provisional separado. No predice lo que el hablante dirá después.

En streaming, el reconocimiento usa `condition_on_previous_text=False`, timestamps por palabra y un buffer de audio con solape. La traducción compacta recibe el texto de la frase acumulada, no el historial completo: `CompactTranslation.__call__()` traduce cada bloque sin memoria entre llamadas.

`Output._cut()` separa por puntuación y, si falta, limita el bloque a 22 palabras. No detecta que una persona respondió al chat, abandonó una idea o corrigió una afirmación. Tampoco distingue automáticamente una muletilla de una respuesta con significado.

La documentación anterior de la vista mencionaba contexto acumulado: se refiere a la frase en curso, no a memoria semántica entre intervenciones.

## Opciones externas y decisión

| Opción | Qué aporta | Decisión para este proyecto |
|---|---|---|
| [Silero VAD](https://github.com/snakers4/silero-vad) | Detecta voz y pausas. Ofrece ejecución ONNX. | Primera opción para evaluar segmentación en vivo reutilizando los componentes de faster-whisper. No clasifica comentarios aparte. |
| [whisper-timestamped](https://github.com/linto-ai/whisper-timestamped#detecting-disfluencies) | Heurísticas para marcar posibles disfluencias con `[*]`, sin asegurar qué se dijo en ellas. | Útil para alineación/análisis; no incorporarlo como filtro semántico del traductor. Usa openai-whisper y no es una opción que se active directamente en nuestro backend CTranslate2. |
| [CrisperWhisper](https://github.com/nyrahealth/CrisperWhisper) | Modos literal e intended, con muletillas, repeticiones y comienzos fallidos. Publica varios tamaños, incluido small. | Candidato específico si se necesita transcripción literal/depurada. Requiere otros pesos y comparación real de consumo, precisión y streaming. El README indica licencia de investigación no comercial para los modelos estándar; no adoptarlo como dependencia de distribución general sin resolver esa condición. |
| [SimulStreaming](https://github.com/ufal/SimulStreaming) | Sistema estudiado de transcripción/traducción simultánea; componentes separables. | Referencia para políticas de contexto. Su configuración recomendada de Whisper large-v3 y EuroLLM-9B no encaja en el objetivo ligero de esta laptop. No se probó una variante pequeña. |

[faster-whisper](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py) ya ofrece `hallucination_silence_threshold` para posibles alucinaciones asociadas a silencio. No resuelve frases abandonadas ni clasifica la intención del hablante. No se activó sin una prueba que descarte pérdida de voz real.

## Mejora de menor coste que conviene probar

Separar bloques usando pausas y timestamps ya disponibles antes de añadir otro modelo de comprensión. Conservar las intervenciones cortas; `ah sí`, `no` o `actually` pueden cambiar el sentido de una conversación. No eliminar esos tokens mediante una lista de palabras.

Una opción visual podría atenuar muletillas inequívocas que el ASR sí haya transcrito, conservando el original completo. Es una regla de presentación, no una detección fiable de intención. No puede recuperar sonidos que el ASR omitió.

Para aprobar cambios de segmentación o un backend nuevo se necesitan muestras públicas de conversación con anotaciones: comienzos abandonados, autocorrecciones, comentarios aparte, negaciones y respuestas breves. Comparar pérdida de contenido, traducción, latencia, RAM/VRAM y cambios del texto provisional. Las 59 palabras de lectura limpia de la comparación anterior no cubren estos casos.

No se identificaron con certeza las herramientas llamadas `kev` y `laya`. No asumir que son KV cache o Aya sin sus enlaces.

## Resultado de las pruebas posteriores

Se ejecutaron VAD síncrono, VAD en hilo separado y separación mediante timestamps sobre un replay público de 31,755 s. El baseline tuvo 2 errores/59 palabras; las variantes tuvieron 4, 7 y 5 respectivamente. Las pasadas de ASR recibieron ventanas distintas por su temporización, con el traductor preexistente activo. No se puede atribuir toda la diferencia al separador, pero estos resultados no permiten activarlo por defecto ni afirmar una mejora de reconocimiento.

Se descartaron las dos variantes con VAD añadido. Se incorporó únicamente `--utterance-pause` como opción explícita: utiliza timestamps y energía del audio, sin cargar un modelo. Las pruebas de límites comprobaron negaciones, respuestas breves, ausencia de cortes dentro de palabras, hipótesis pendientes y recorte del buffer.

La comprobación aislada con ASR real y puntuación retirada después del reconocimiento separó tres bloques por pausas y conservó las 67 palabras reconocidas. Entre ellas había ocho palabras alucinadas en silencio: dos repeticiones de `Thank you very much`. El separador las conservó porque no es un filtro de alucinaciones. Este fallo queda registrado; no se ocultó mediante una lista que borre frases.

Ver la guía del visor para el comando opcional. No se incorporó un clasificador de intención, un LLM de limpieza ni CrisperWhisper. Los límites medidos justifican mantener la ruta actual por defecto.
