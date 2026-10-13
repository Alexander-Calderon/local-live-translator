# Leer subtítulos mientras hablan

## App web

Ejecutar ./app.sh con el entorno preparado. La página abre en el navegador del equipo. Desde ahí se elige modo, audio del sistema o micrófono, tamaño de bloques, vocabulario y guardado.

Iniciar crea una sesión. Aplicar y reiniciar reemplaza solo esa sesión. Detener cierra su motor de audio y deja el último texto visible. Cerrar la pestaña no detiene la captura; Ctrl+C cierra la app y su sesión.

La app escucha en 127.0.0.1, con ruta aleatoria y controles protegidos contra peticiones de otra página. No expone un servicio público ni acepta comandos arbitrarios desde el formulario.

## Lectura estable

El original confirmado y su continuación provisional aparecen a la izquierda. La última traducción confirmada permanece a la derecha hasta que llega otra completa. Debajo se indica el original de esa traducción, porque la transcripción puede ir por delante.

El borrador de traducción es opcional y aparece aparte. Puede cambiar al llegar contexto nuevo; nunca sustituye la traducción confirmada. Desactivarlo evita trabajo de traducción provisional en CPU.

La app agrupa fragmentos cortos y evita ciertos cierres después de negaciones incompletas. Mantiene respuestas breves comunes y libera texto confirmado durante pausas. Es una política conservadora, no un analizador semántico. Elegir Más contexto puede mejorar continuidad del bloque con mayor espera.

El historial conserva 100 bloques. El guardado opcional conserva la transcripción completa en la carpeta privada de la app y permite descargarla. Pausar lectura congela la vista, no la captura; desplazarse por el historial no obliga a seguir el final.

## Modos

- Whisper base: opción inicial para salida progresiva.
- Whisper small: variante mayor; no mejoró base en el corpus comparado.
- Whisper medium: segmentos de hasta ocho segundos, más la inferencia; no es instantáneo.
- Whistle: CPU por segmentos. Se habilita si sus pesos y binario están preparados.

El visor muestra motor, dispositivo, precisión y pistas de vocabulario. En streaming también muestra duración de la pasada y cola aproximada. Esa cola no es la latencia total de confirmación/traducción.

## Vocabulario

Activar Vocabulario técnico y editar los nombres esperados. El ejemplo incluye tmux. Las pistas nativas no garantizan reconocimiento. Los nombres reconocidos se protegen durante la traducción; variantes exactas de tmux se normalizan solo en ese paso y el original se conserva.

Los términos editados desde la web se guardan en la carpeta privada de la app, fuera de Git. El código público contiene únicamente un ejemplo de nombres de herramientas.

## Experimentales

La separación por pausas está desactivada por defecto y solo se aplica a Whisper en vivo. Las pruebas no justificaron activarla como mejora general.

Marcar posibles muletillas requiere pesos FDT de investigación preparados aparte. No borra palabras ni clasifica con fiabilidad comentarios al chat. Los pesos no se distribuyen con el proyecto y tienen límites de uso de investigación.

Ventana flotante usa Document Picture-in-Picture donde está disponible. La apertura nativa no pudo verificarse en el navegador integrado. No afirmar soporte universal en escritorios Linux, Windows o macOS a partir del botón. Cerrar esa ventana devuelve el panel a la página; no detiene la captura.

## CLI

Se conserva para dispositivos concretos y ajustes avanzados. --live abre el visor con Whisper; --view web sirve para Whistle por segmentos. --translation-preview habilita el borrador separado; --min-phrase-words ajusta el agrupado conservador. Para salir, Ctrl+C.
