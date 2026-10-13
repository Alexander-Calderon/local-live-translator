# Publicar el traductor

El código del wrapper tiene licencia MIT y aviso de autoría en LICENSE. Las licencias de los motores, modelos y corpus se conservan por separado. No distribuir los pesos del detector FDT de investigación.

## Revisar la beta

1. Abrir ./app.sh y usar varios minutos de conversación pública en inglés.
2. Comprobar que la traducción confirmada permanece fija y que el original indicado debajo corresponde a ella.
3. Comparar base en vivo y Whistle CPU. Medium por segmentos ofrece otra precisión con mayor demora.
4. Activar el vocabulario técnico y pronunciar tmux, Warp Terminal y Excalidraw por micrófono. Las pistas y variantes exactas están implementadas; aún no hay un benchmark acústico de esos nombres.
5. Probar Iniciar, Detener, Aplicar y reiniciar, guardado y descarga. El borrador de traducción y las opciones experimentales empiezan desactivados.

La captura está validada en Linux con PulseAudio/PipeWire. La apertura nativa de la ventana flotante no está validada. No presentarla como soporte universal de escritorios.

## Archivos publicables

La lista permite fuentes, documentación, pruebas, workflow, licencia y vocabulario de ejemplo. Excluye sesiones, logs originales, ensayos, notas antiguas, backups, modelos, entornos y vocabularios privados. Las medidas de los ensayos están resumidas en la documentación.

La revisión local detecta algunas clases de claves, rutas personales y archivos fuera de esa lista. No imprime sus contenidos y no sustituye la revisión del diff. CI repite el control después de subir; no evita una filtración que ya ocurrió.

## Primer commit

Desde la raíz del proyecto:

    python3 bin/check_publication.py
    git init -b main
    git add .
    python3 bin/check_publication.py --tracked-only
    git diff --cached --stat
    git diff --cached
    git commit -m "Add local live translator"

## GitHub

Crear un repositorio público vacío, sin generar otro README ni licencia. Copiar su URL y sustituir el marcador:

    git remote add origin URL-del-repositorio
    python3 bin/check_publication.py --tracked-only
    git push -u origin main

Usar Git para subir los archivos seleccionados; no arrastrar la carpeta de trabajo completa, con modelos y sesiones, a la web. Abrir Actions y comprobar el workflow correspondiente al último commit.

El repositorio público es https://github.com/Alexander-Calderon/local-live-translator y la beta actual es v0.1.1. La captura funciona en Linux. La comparación reproducible de streaming está en docs/comparacion-streaming.md; mide reconocimiento, demora y memoria con el mismo corpus.

## Artículo

El borrador del blog explica objetivo, pipeline, resultados y límites. Antes de publicarlo, añadir la URL real del repositorio y revisar el video de uso. Mostrar hardware y configuración; distinguir cálculo ASR de clips completos y latencia de una conversación. Los nombres técnicos y voces difíciles todavía pueden fallar.
