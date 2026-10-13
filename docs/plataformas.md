# Linux, Windows y macOS

La interfaz es la misma página local en los tres sistemas. La captura cambia según el sistema operativo. Windows y macOS se incorporan como rutas experimentales hasta completar una prueba con sus dispositivos reales; un replay de archivo no prueba el permiso ni el audio del sistema.

| Sistema | Micrófono | Audio del sistema | Sistema y micrófono | Reconocimiento |
|---|---|---|---|---|
| Linux | PulseAudio/PipeWire | Monitor del dispositivo de salida | Mezcla temporal de la app | Whisper; Whistle si está preparado |
| Windows nativo | PyAudioWPatch/PortAudio | WASAPI loopback | Dos capturas, mezcla local | Whisper CPU; CUDA si está disponible |
| macOS | SoundCard/CoreAudio | AudioTee/Core Audio taps, macOS 14.2+ | Dos capturas, mezcla local | Whisper CPU |

La mezcla conserva las voces en una sola pista. No identifica hablantes ni cancela eco; usa auriculares. No cambia los dispositivos predeterminados de Windows o macOS. En Linux retira solo los módulos temporales que creó.

## Instalar en Windows

Con Python 3.12 instalado, abre PowerShell en la carpeta del proyecto:

    py -3.12 install.py
    .\app.cmd

El instalador crea `.venv` si hace falta, instala PyAudioWPatch y prepara traducción y backend WhisperLive. No requiere WSL. En la primera ejecución de Whisper, desmarca Solo modelos descargados si no tienes los pesos en caché. La descarga requiere internet; luego puedes usar el modo sin conexión.

El audio del sistema usa el loopback de la salida WASAPI predeterminada. El micrófono usa la entrada predeterminada. Si cambias de dispositivo, detén y reinicia la captura. Permite acceso al micrófono para aplicaciones de escritorio en los ajustes de Windows. La ruta CPU no necesita CUDA ni un controlador de audio virtual.

## Instalar en macOS

Con Python 3.12 y las herramientas de línea de comandos de Apple disponibles:

    python3.12 install.py
    ./app.sh

El instalador reutiliza un entorno existente o crea `.venv`. SoundCard se usa para el micrófono. Para audio del sistema compila una revisión fijada de AudioTee dentro de `.runtime/audiotee/`; no instala un servicio ni un controlador global. Comprueba el hash de las fuentes y conserva su README con la licencia MIT. Si faltan las herramientas Swift, el instalador lo indica y no las instala por su cuenta.

La captura del sistema requiere macOS 14.2 o posterior. Al iniciar, macOS puede pedir permiso de grabación de audio del sistema; el micrófono tiene su permiso propio. Concédelos al proceso o terminal que ejecuta la app. Si deniegas un permiso, detén la app, corrige el permiso en Ajustes del Sistema y vuelve a abrirla. No se eluden esos controles.

Whisper funciona en CPU en Mac; esta implementación no usa Metal. Los perfiles Whistle permanecen deshabilitados fuera de Linux hasta preparar y verificar sus binarios para esas plataformas.

## Linux existente

Se conserva PulseAudio/PipeWire, los pesos, el vocabulario y las sesiones locales. El servidor de controles y el worker usan el entorno Python ya preparado. No necesitas instalar PyAudioWPatch ni SoundCard en Linux.

## Comprobar una instalación

1. Abre la app, elige base, idioma y traducción. Inicia con micrófono y pronuncia una frase con una negación. Comprueba original y traducción.
2. Cambia a audio del sistema, reproduce un clip público y verifica que el texto corresponde al audio. Comprueba también el silencio.
3. Prueba sistema y micrófono con auriculares. Verifica que ambos entran sin duplicación por los altavoces.
4. Detén e inicia de nuevo. Guarda, abre y retoma una sesión; comprueba que agrega texto nuevo.
5. Cierra la app. Verifica que no sigue capturando y que los dispositivos predeterminados siguen iguales.

Los registros y modelos quedan fuera de Git. En Windows, los archivos heredan las ACL de la carpeta donde clones el proyecto; `chmod` no establece permisos privados equivalentes a Unix. Usa una carpeta de tu perfil de usuario.

## Pruebas automáticas y sus límites

Las pruebas deterministas verifican conversión 48 kHz a 16 kHz con filtro antialias, mezcla de dos señales, cierre de recursos y errores de permisos. CI ejecuta la app con un archivo público: carga el modelo en CPU, transcribe, traduce y retiene el texto al finalizar. En macOS también compila el helper fijado sin iniciar captura ni pedir permisos.

El gate exige conservar las dos frases de la muestra, su traducción y cerrar sin texto provisional pendiente. El cierre espera la confirmación del motor, con un límite de 60 segundos, en lugar de cortar después de una pausa fija.

El informe de cada runner identifica sistema, Python, hash del audio y tiempo de ejecución. Los runners no sustituyen una prueba de micrófono, loopback y permisos del usuario. No se usa una VM Linux para afirmar soporte nativo de Windows o macOS.

## Fuentes

- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch): PortAudio con WASAPI loopback.
- [SoundCard](https://github.com/bastibe/SoundCard): acceso al micrófono mediante CoreAudio.
- [AudioTee](https://github.com/makeusabrew/audiotee/tree/56ac954369a09318e46b88a6eec33c2d2b0d32a3): fuentes fijadas del capturador del sistema.
- [Core Audio taps de Apple](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps).
