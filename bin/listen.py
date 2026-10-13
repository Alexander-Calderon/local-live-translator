#!/usr/bin/env python3
"""
Captura local de audio en Linux, reconocimiento y traducción en CPU.
Whisper en vivo reutiliza el backend de WhisperLive con un modelo precargado.
Whistle y el modo por frases procesan segmentos cerrados. El streaming propio
anterior queda disponible como motor legacy experimental.
"""
import argparse, subprocess, sys, time, os, queue, threading, re, wave, json
from collections import deque
import numpy as np

TTY = sys.stdout.isatty()      # los codigos de escape solo tienen sentido en terminal
CAPTION_VIEW = None
DISFLUENCY_MARKER = None
VOCABULARY_PATTERN = None
MIN_SENTENCE_WORDS = 3
TRANSLATION_PREVIEW = False
CLEAR = "\r\033[K" if TTY else ""
DIM, RESET = ("\033[2m", "\033[0m") if TTY else ("", "")

RATE = 16000
BLOCK = 1600                # 0.1 s por bloque leido

# --- modo phrase ---
SILENCE_RMS = 0.006
SILENCE_HOLD = 0.8
MIN_SPEECH = 0.5
MAX_SEGMENT = 20.0

# --- modo stream ---
# Cada cuanto se lanza una pasada. ES EL PARAMETRO QUE MANDA EN LA LATENCIA:
# LocalAgreement-2 necesita DOS pasadas que coincidan para confirmar texto, asi
# que la latencia minima es 2 x MIN_CHUNK. Con 1.0 s el texto tardaba 2 s en
# aparecer aunque la inferencia solo costase 0.17 s.
# Se puede bajar mientras la inferencia siga por debajo de este valor.
MIN_CHUNK = 0.4
# 16 s y no 28: Whisper trabaja en ventanas de 30 s y el coste se dispara al
# acercarse al limite. Medido en RTX 3050 con small/int8_float16:
#   buffer 10 s -> 0.32 s | 20 s -> 0.56 s | 28 s -> 4.39 s  (8x mas lento)
# Con 28 s la inferencia tardaba mas que MIN_CHUNK y el sistema se atascaba.
MAX_BUFFER = 14.0
TRIM_KEEP = 3.0             # segundos de contexto que se conservan al recortar
IDLE_RMS = 0.004            # por debajo de esto no se lanza inferencia
SENT_END = re.compile(r"[.!?…]$")


def default_monitor() -> str:
    sink = subprocess.run(["pactl", "get-default-sink"],
                          capture_output=True, text=True).stdout.strip()
    return f"{sink}.monitor"


def default_mic() -> str:
    return subprocess.run(["pactl", "get-default-source"],
                          capture_output=True, text=True).stdout.strip()


def list_devices() -> None:
    print("SALIDA DEL SISTEMA (monitores) — lo que suena en el PC:\n")
    subprocess.run(["pactl", "list", "short", "sources"])
    print(f"\nPor defecto se usa: {default_monitor()}")


def capture(device: str, q: "queue.Queue") -> None:
    cmd = ["parec", f"--device={device}", "--format=s16le",
           f"--rate={RATE}", "--channels=1", "--latency-msec=100"]
    p = None
    nbytes = BLOCK * 2
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        while True:
            raw = p.stdout.read(nbytes)
            if not raw or len(raw) < nbytes:
                break
            q.put(np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0)
    finally:
        if p:
            p.terminate()
            try:p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                p.kill();p.wait()
        q.put(None)


def common_prefix(a: list, b: list) -> int:
    """Cuantas palabras iniciales comparten dos hipotesis (comparando texto)."""
    n = 0
    for x, y in zip(a, b):
        if x.word.strip().lower() != y.word.strip().lower():
            break
        n += 1
    return n


# Palabras acumuladas antes de cerrar frase si no llega puntuacion.
# 22 y no 14: con fragmentos cortos el traductor recibe media idea y el
# resultado pierde sentido. Comparado en habla real, 22-25 da traducciones
# coherentes sin retrasar apenas la salida.
MAX_PENDING_WORDS = 22


class Output:
    """Muestra el ingles en vivo y publica cada frase JUNTO a su traduccion.

    Regla que no se puede romper: **el bloque en ingles y el bloque en espanol
    tienen que corresponderse exactamente**. Antes no era asi porque el hilo de
    traduccion cerraba la linea inglesa a medias para imprimir el espanol; la
    frase quedaba partida y el resto salia despues con otra marca de tiempo, ya
    descolgado de su traduccion.

    Ahora:
      - la frase en curso se ve crecer en una linea viva (se reescribe sola)
      - al cerrarse, la linea viva se borra y el bloque se publica ENTERO:
        ingles + traduccion, en una sola escritura atomica
    """

    def __init__(self, translate, log_path=None):
        self.translate = translate
        self.log = open(log_path, "a", encoding="utf-8") if log_path else None
        self.lock = threading.Lock()
        self.pending = ""
        self.live_len = 0
        self.view = CAPTION_VIEW
        self.draft_lock = threading.Lock()
        self.draft_text = ''
        self.draft_generation = 0
        self.q: "queue.Queue" = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def _clear_live(self) -> None:
        if TTY and self.live_len:
            sys.stdout.write("\r" + " " * min(self.live_len + 4, 200) + "\r")
            self.live_len = 0

    def _live(self) -> None:
        if self.view:
            self.preview('')
            return
        if not TTY:
            return
        txt = self.pending.strip()
        if not txt:
            return
        if len(txt) > 130:
            txt = "…" + txt[-129:]
        with self.lock:
            self._clear_live()
            sys.stdout.write(f"{DIM}▸ {txt}{RESET}")
            sys.stdout.flush()
            self.live_len = len(txt) + 2

    def _publish(self, sentence: str, identity=None) -> None:
        """Un bloque = una frase inglesa + SU traduccion. Nunca se parten."""
        sentence = sentence.strip()
        if not sentence:
            return
        if self.view and DISFLUENCY_MARKER:
            try:
                self.view.annotate(identity, DISFLUENCY_MARKER(sentence))
            except Exception as error:
                self.view.status(f'No se pudieron marcar disfluencias: {error}')
        es = None
        if self.translate:
            try:
                es = self.translate(sentence)
            except Exception as e:
                es = f"(error traduciendo: {e})"
        stamp = time.strftime("%H:%M:%S")
        bloque = f"[{stamp}] {sentence}\n"
        if es is not None:
            bloque += f"{DIM}           → {es}{RESET}\n"
        bloque += "\n"
        with self.lock:
            if self.view:
                self.view.finish(identity, es)
            else:
                self._clear_live()
                sys.stdout.write(bloque)      # una sola escritura: no se entrelaza
                sys.stdout.flush()
            if self.log:                  # transcripcion limpia, sin colores
                self.log.write(f"[{stamp}] {sentence}\n")
                if es is not None:
                    self.log.write(f"           -> {es}\n")
                self.log.flush()

    def _cut(self) -> int:
        """Donde termina la frase actual, o -1 si aun no hay corte.

        Las posiciones se miden sobre `pending` TAL CUAL. Normalizar espacios
        antes de medir desplaza el indice y el corte cae a mitad de palabra.
        """
        for m in re.finditer(r"[.!?…]", self.pending):
            if VOCABULARY_PATTERN and any(term.start() < m.end() < term.end() for term in VOCABULARY_PATTERN.finditer(self.pending)):
                continue
            if m.group() == '.':
                # A period within a number/name/URL or an abbreviation is not
                # a sentence boundary (Mr., Dr., U.N., version 3.12).
                if m.end() < len(self.pending) and not self.pending[m.end()].isspace():
                    continue
                prefix = self.pending[:m.start()]
                token = re.search(r"([\w.]+)$", prefix)
                token = token.group(1) if token else ''
                if token.lower() in {'mr','mrs','ms','dr','prof','sr','jr','sra','srta','etc'}:
                    continue
                if len(token) == 1 and token.isalpha():
                    continue
                if re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]", token):
                    continue
            candidate=self.pending[:m.end()].strip()
            short_reply=candidate.lower() in {'yes.','no.','okay.','ok.','thanks.','thank you.','i agree.',"that's right."}
            if not short_reply and len(candidate.split())<MIN_SENTENCE_WORDS:
                continue
            if m.group()=='.' and re.search(r'\b(?:not|and|or|because|although|to|the|of|with)\.$',candidate,re.I):
                continue
            return m.end()
        words = list(re.finditer(r"\S+", self.pending))
        if len(words) > MAX_PENDING_WORDS:
            limit = words[MAX_PENDING_WORDS - 1].end()
            marks = list(re.finditer(r"[,;:]", self.pending[:limit]))
            cut=marks[-1].end() if marks else limit
            if VOCABULARY_PATTERN:
                for term in VOCABULARY_PATTERN.finditer(self.pending):
                    if term.start() < cut < term.end():cut=term.end()
            return cut
        return -1

    def add(self, text: str) -> None:
        if not text.strip():
            return
        self.pending += text
        while True:
            cut = self._cut()
            if cut < 0:
                break
            self._enqueue(self.pending[:cut])
            self.pending = self.pending[cut:].lstrip()
        self._live()

    def preview(self, text):
        if not self.view:
            return
        source = self.pending.strip()
        self.view.current(source, text.strip())
        with self.draft_lock:
            self.draft_text = (source + ' ' + text.strip()).strip()

    def _enqueue(self, sentence):
        identity = self.view.begin(sentence.strip()) if self.view else None
        with self.draft_lock:
            self.draft_generation += 1
            self.draft_text = ''
        self.q.put((identity, sentence))

    def flush(self, sentence: str = None) -> None:
        """Modo phrase: frase completa de una vez."""
        if sentence is None:
            sentence, self.pending = self.pending, ""
        if sentence.strip():
            self._enqueue(sentence)

    def _worker(self) -> None:
        last_draft_time = 0.0
        last_draft = None
        while True:
            try:
                identity, item = self.q.get(timeout=0.15)
            except queue.Empty:
                if not TRANSLATION_PREVIEW or not self.view or not self.translate or time.monotonic()-last_draft_time < 1.0:
                    continue
                with self.draft_lock:
                    generation, text = self.draft_generation, self.draft_text
                if len(text.split()) < 3 or (generation, text) == last_draft:
                    continue
                last_draft_time = time.monotonic()
                last_draft = (generation, text)
                try:
                    translated = self.translate(text)
                except Exception:
                    self.view.status('No se pudo actualizar la traducción provisional')
                    continue
                with self.draft_lock:
                    if generation == self.draft_generation:
                        self.view.draft(translated)
                continue
            try:
                self._publish(item, identity)
            finally:
                self.q.task_done()


def run_stream(model, q, a, translate, log_path=None) -> None:
    """Ventana deslizante + LocalAgreement-2."""
    buf = np.zeros(0, dtype=np.float32)
    offset = 0.0                 # segundos ya descartados del buffer
    prev: list = []              # hipotesis anterior (palabras no confirmadas)
    confirmed_until = 0.0        # timestamp absoluto de lo ya confirmado
    out = Output(translate, log_path)
    last_run = time.time()
    infer = 0.0
    last_word = ""               # ultima palabra confirmada, para no repetirla
    quiet_since = None
    pauses = None
    if getattr(a, 'utterance_pause', None):
        from utterance_boundaries import PauseBoundaries
        pauses = PauseBoundaries(a.utterance_pause)

    while True:
        ended = False
        while not q.empty():
            block = q.get()
            if block is None:
                ended = True
                break
            buf = np.concatenate([buf, block])
        if ended:
            if len(buf)==0:
                out.flush();out.q.join()
                if out.log:out.log.close()
                return
            if pauses: pauses.observe(buf, offset)
            # Fin del replay: confirmar dos pasadas, nunca publicar la hipótesis provisional.
            final = []
            for _ in range(2):
                segments, _ = model.transcribe(buf, language=a.lang, beam_size=getattr(a,'beam_size',1),
                                               word_timestamps=True, condition_on_previous_text=False)
                final.append([w for seg in segments for w in (seg.words or [])
                              if offset + w.end > confirmed_until + 0.20])
            n = common_prefix(final[0], final[1])
            if n:
                if pauses: pauses.emit(final[1][:n], offset, out)
                else: out.add("".join(w.word for w in final[1][:n]))
            out.flush()
            out.q.join()
            if out.log:
                out.log.close()
            return
        if len(buf) == 0:
            time.sleep(0.05)
            continue

        if time.time() - last_run < MIN_CHUNK:
            time.sleep(0.05)
            continue

        if pauses: pauses.observe(buf, offset)

        # No gastar GPU transcribiendo silencio: si la cola del buffer no tiene
        # energia, saltar la pasada. Ahorra bastante en pausas largas.
        tail = buf[-int(MIN_CHUNK * RATE):]
        if len(tail) and float(np.sqrt(np.mean(tail ** 2))) < IDLE_RMS and not prev:
            if pauses: pauses.settle(prev, out)
            if quiet_since is None:quiet_since=time.monotonic()
            if out.pending.strip() and time.monotonic()-quiet_since>=0.8:out.flush()
            if len(buf) / RATE > TRIM_KEEP * 2:      # soltar silencio acumulado
                keep = int(TRIM_KEEP * RATE)
                # OJO: sumar lo DESCARTADO, no lo que queda. Calcularlo despues
                # de recortar descuadra el offset y reaparecen palabras ya dichas.
                offset += (len(buf) - keep) / RATE
                buf = buf[-keep:]
            time.sleep(0.1)
            continue

        quiet_since=None

        last_run = time.time()
        t0 = time.time()
        segs, _ = model.transcribe(buf, language=a.lang, beam_size=getattr(a,'beam_size',1),
                                   word_timestamps=True, condition_on_previous_text=False)
        words = [w for s in segs for w in (s.words or [])]
        infer = time.time() - t0
        if CAPTION_VIEW:
            # Captura y replay en bloques de 100 ms; la cola es una aproximación,
            # no la latencia completa de confirmación y traducción.
            CAPTION_VIEW.metrics(len(buf)/RATE, infer, q.qsize()*BLOCK/RATE)
        if a.stats and CAPTION_VIEW:
            CAPTION_VIEW.status(f'Audio {len(buf)/RATE:.1f}s · reconocimiento {infer:.2f}s')
        elif a.stats:
            sys.stderr.write(f"\r[buf {len(buf)/RATE:4.1f}s  infer {infer:4.2f}s]  ")
            sys.stderr.flush()
        # Descartar lo ya confirmado. El margen NO puede ser minimo: los
        # timestamps de palabra de Whisper varian entre pasadas, y con 0.01 s
        # la ultima palabra de cada linea se colaba otra vez al principio de la
        # siguiente. 0.20 s elimina el solape sin perder palabras nuevas.
        words = [w for w in words if offset + w.end > confirmed_until + 0.20]
        # Red de seguridad por texto: si aun asi repite la ultima confirmada.
        if words and last_word and words[0].word.strip().lower() == last_word:
            words = words[1:]
        if not words:
            prev = []
            if pauses: pauses.settle(prev, out)
            continue

        n = common_prefix(prev, words)
        if n:
            agreed, words_rest = words[:n], words[n:]
            text = "".join(w.word for w in agreed)
            confirmed_until = offset + agreed[-1].end
            if pauses: pauses.emit(agreed, offset, out)
            else: out.add(text)
            prev = words_rest
        else:
            prev = words
            # Sin linea provisional: era lo que daba la sensacion de que las
            # palabras se sobrescribian. Lo confirmado ya sale al instante
            # desde Output.add(). Se puede reactivar con --preview.
            if TTY and a.preview and not CAPTION_VIEW:
                prov = "".join(w.word for w in words).strip()
                if prov:
                    sys.stderr.write(f"{CLEAR}{DIM}… {prov[-100:]}{RESET}")
                    sys.stderr.flush()

        if a.preview and out.view:
            out.preview(''.join(w.word for w in prev))
        if pauses: pauses.settle(prev, out)

        # recorte: no dejar crecer el buffer sin limite.
        # Si la inferencia tarda mas que el intervalo entre pasadas, el sistema
        # se atrasa: en ese caso se recorta antes, sin esperar a MAX_BUFFER.
        limit = MAX_BUFFER if infer < MIN_CHUNK else max(8.0, MAX_BUFFER * 0.6)
        dur = len(buf) / RATE
        if dur > limit:
            cut_at = max(0.0, (confirmed_until - offset) - TRIM_KEEP)
            if cut_at > 1.0:
                buf = buf[int(cut_at * RATE):]
                offset += cut_at
            else:                       # nada confirmado: cortar a la fuerza
                keep = int(TRIM_KEEP * RATE)
                offset += (len(buf) - keep) / RATE
                buf = buf[-keep:]
                prev = []


def run_phrase(model, q, a, translate, log_path=None) -> None:
    """Corta por silencio (modo antiguo, mas ligero)."""
    out = Output(translate, log_path)
    buf, silence, speaking = [], 0.0, False
    # Keep the onset: unvoiced consonants can precede the energy threshold.
    preroll = deque(maxlen=3)
    levels = deque(maxlen=30)
    def emit(audio):
        if len(audio) / RATE < MIN_SPEECH:
            return
        started = time.monotonic()
        segs, _ = model.transcribe(audio, language=a.lang, beam_size=getattr(a,'beam_size',1), vad_filter=True,
                                  word_timestamps=True,condition_on_previous_text=False,
                                  hallucination_silence_threshold=1.0)
        text = " ".join(s.text.strip() for s in segs).strip()
        if getattr(a, "stats", False):
            status = f"Segmento {len(audio)/RATE:.1f}s · reconocimiento {time.monotonic()-started:.2f}s"
            if CAPTION_VIEW: CAPTION_VIEW.status(status)
            else: print(f"[{status}]", file=sys.stderr)
        if text:
            out.flush(text)
    while True:
        try:
            block = q.get()
        except KeyboardInterrupt:
            if buf:
                emit(np.concatenate(buf))
            out.q.join()
            if out.log:
                out.log.close()
            raise
        if block is None:
            if buf:
                emit(np.concatenate(buf))
            out.q.join()
            if out.log:
                out.log.close()
            return
        rms = float(np.sqrt(np.mean(block ** 2)))
        levels.append(rms)
        threshold = SILENCE_RMS
        if a.profile == "balanced":
            threshold = max(0.00015, min(0.003, float(np.percentile(levels, 10))*3.0))
        dur = len(block) / RATE
        if rms > threshold:
            if not speaking:
                buf.extend(preroll)
                preroll.clear()
            speaking, silence = True, 0.0
            buf.append(block)
        elif speaking:
            buf.append(block)
            silence += dur
        else:
            preroll.append(block)
        total = sum(len(b) for b in buf) / RATE
        if speaking and (silence >= SILENCE_HOLD or total >= MAX_SEGMENT):
            audio = np.concatenate(buf)
            buf, speaking, silence = [], False, 0.0
            # When continuous speech reaches the cap, prefer a quiet point
            # near the end instead of cutting directly through a loud syllable.
            if total >= MAX_SEGMENT and len(audio) >= RATE:
                tail_start = len(audio) - RATE
                candidates = range(tail_start, len(audio)-1600+1, 1600)
                cut = min(candidates, key=lambda i: float(np.mean(audio[i:i+1600]**2))) + 1600
                remainder = audio[cut:]
                audio = audio[:cut]
                if len(remainder):
                    buf, speaking = [remainder], True
            emit(audio)


def main() -> int:
    global MIN_CHUNK, MAX_BUFFER, MAX_PENDING_WORDS   # antes de cualquier uso
    global SILENCE_HOLD, MAX_SEGMENT, SILENCE_RMS
    global CAPTION_VIEW
    global VOCABULARY_PATTERN
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["stream", "phrase"], default=None)
    ap.add_argument("--source", choices=["system", "mic"], default="system")
    ap.add_argument("--device", help="nombre exacto (ver --list)")
    ap.add_argument("--model", default=None)
    ap.add_argument('--beam-size',type=int,default=1,choices=range(1,9),help='Whisper: alternativas de decodificación (1 rápido; 3 usado en comparación)')
    ap.add_argument("--asr", choices=["whisper", "whistle"], default=None)
    ap.add_argument("--profile", choices=["custom", "light", "balanced"], default=None,
                    help="balanced: Whistle por segmentos, CPU baja; light: Whistle streaming")
    ap.add_argument("--segment", type=float, default=None,
                    help="máximo de segundos por segmento en balanced/phrase")
    ap.add_argument("--pause", type=float, default=None,
                    help="silencio necesario para cerrar un segmento")
    ap.add_argument("--utterance-pause", type=float, default=None,
                    help="separar frases confirmadas por pausas en streaming (segundos; 0 desactiva)")
    ap.add_argument("--keywords", help="archivo UTF-8: pistas para Whisper/Whistle y nombres que conservar en traducción")
    ap.add_argument('--offline', action='store_true',help='Whisper: exigir modelos ya descargados, sin descargar pesos')
    ap.add_argument("--whistle-binary")
    ap.add_argument("--whistle-weights")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--input-wav", help="replay local PCM16 mono 16kHz a velocidad real, sin micrófono")
    ap.add_argument("--stream-engine", choices=["whisperlive","legacy"], default="whisperlive", help="Whisper en vivo: backend WhisperLive o streaming antiguo experimental")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--to", default="es")
    ap.add_argument("--no-translate", action="store_true")
    ap.add_argument("--translator", choices=["argos", "compact"], default=None,
                    help="compact reutiliza el paquete Argos local para bloques, sin Stanza")
    ap.add_argument("--translation-package", help="carpeta de un paquete Argos SentencePiece instalado")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--compute", default="int8_float16",
                    help="float16 | int8_float16 (por defecto) | int8")
    ap.add_argument("--interval", type=float, default=None,
                    help=f"segundos entre pasadas (por defecto {MIN_CHUNK}). "
                         "La latencia es el doble de este valor")
    ap.add_argument("--buffer", type=float, default=None,
                    help=f"tope del buffer en segundos (por defecto {MAX_BUFFER})")
    ap.add_argument("--chunk-words", type=int, default=None,
                    help=f"palabras acumuladas antes de emitir sin puntuacion "
                         f"(por defecto {MAX_PENDING_WORDS}). Mas alto = mejor "
                         "traduccion pero llega mas tarde")
    ap.add_argument("--save", nargs="?", const="auto", default=None,
                    metavar="ARCHIVO",
                    help="guardar la transcripcion. Sin valor, usa out/<fecha>.txt")
    ap.add_argument("--preview", action="store_true",
                    help="mostrar hipotesis provisional (parpadea al corregirse)")
    ap.add_argument("--view", choices=["terminal", "web"], default="terminal",
                    help="web: original, traducción provisional e historial en paneles separados")
    ap.add_argument("--live", action="store_true",
                    help="vista legible en vivo: Whisper small, streaming y visor web local")
    ap.add_argument('--disfluency-model', help='carpeta local ONNX para marcar posibles disfluencias (experimental, inglés)')
    ap.add_argument('--translation-preview', action='store_true', help='borrador separado de traducción; puede cambiar con el contexto')
    ap.add_argument('--term-aliases', help='JSON de variantes técnicas exactas; solo se normalizan al traducir')
    ap.add_argument('--state-json', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--min-phrase-words',type=int,default=3,choices=range(1,13),help='evitar cierres prematuros de fragmentos cortos; conserva respuestas breves comunes')
    ap.add_argument("--stats", action="store_true",
                    help="mostrar tamano de buffer y tiempo de inferencia")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    global TRANSLATION_PREVIEW
    global MIN_SENTENCE_WORDS
    TRANSLATION_PREVIEW = a.translation_preview
    MIN_SENTENCE_WORDS = a.min_phrase_words
    terms=[]
    if a.keywords:
        from vocabulary import read_keywords
        try: terms=read_keywords(a.keywords)
        except (OSError,ValueError) as error:ap.error(str(error))
        if terms:
            VOCABULARY_PATTERN=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(term) for term in sorted(terms,key=len,reverse=True))+r')(?!\w)',re.I)
    aliases={}
    if a.term_aliases:
        from vocabulary import read_aliases
        try: aliases=read_aliases(a.term_aliases,terms)
        except (OSError,ValueError) as error:ap.error(str(error))
    if a.disfluency_model and a.lang != 'en':
        ap.error('--disfluency-model solo está evaluado en inglés')
    if a.disfluency_model and a.view != 'web' and not a.live:
        ap.error('--disfluency-model requiere --live o --view web')

    if a.list:
        list_devices()
        return 0

    if a.live:
        if a.profile in ("light", "balanced") or a.asr == "whistle":
            ap.error("--live usa Whisper; para Whistle elige --view web con su perfil")
        a.view, a.mode, a.profile, a.asr = "web", "stream", "custom", "whisper"

    # No flags: the measured balanced profile. Explicit --model keeps Whisper.
    if a.profile is None:
        runtime=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'.runtime','whistle')
        has_whistle=all(os.path.isfile(os.path.join(runtime,name)) for name in ('needle','whistle.cact'))
        a.profile = "custom" if a.model is not None or a.asr is not None or not has_whistle else "balanced"
    if a.model is None: a.model = "small"
    if a.asr is None: a.asr = "whisper"
    if a.segment is None: a.segment = 12.0 if a.profile == "balanced" else 20.0

    if a.profile == "light":
        a.asr = "whistle"
        if a.interval is None: a.interval = 1.5
        if a.buffer is None: a.buffer = 12.0
        if a.chunk_words is None: a.chunk_words = 22
    if a.profile == "balanced":
        a.asr = "whistle"
        if a.mode is None: a.mode = "phrase"
        if a.pause is None: a.pause = 0.8
        SILENCE_RMS = 0.003
    if a.asr=='whistle' and a.beam_size!=1:
        ap.error('--beam-size solo es configurable en Whisper')
    if a.mode is None: a.mode = "stream"
    if a.asr == 'whisper' and a.model == 'medium' and a.mode == 'stream':
        print('Aviso: medium en streaming reprocesa ventanas de audio. En una GPU pequeña puede responder tarde; usa base para lectura rápida o medium con --mode phrase --view web.',file=sys.stderr)
    if not 3 <= a.segment <= 25: ap.error("--segment debe estar entre 3 y 25")
    if a.pause is not None and not 0.2 <= a.pause <= 2: ap.error("--pause debe estar entre 0.2 y 2")
    if a.utterance_pause is not None:
        if a.asr != 'whisper' or a.mode != 'stream':
            ap.error('--utterance-pause requiere Whisper en streaming')
        if a.utterance_pause != 0 and not 0.5 <= a.utterance_pause <= 3:
            ap.error('--utterance-pause debe ser 0 o estar entre 0.5 y 3 segundos')
    MAX_SEGMENT = a.segment
    if a.pause is not None: SILENCE_HOLD = a.pause
    if a.threads < 1 or a.threads > 64: ap.error("--threads debe estar entre 1 y 64")
    if a.interval is not None and a.interval <= 0: ap.error("--interval debe ser positivo")
    if a.buffer is not None and not 3 <= a.buffer <= 30: ap.error("--buffer debe estar entre 3 y 30")
    if a.chunk_words is not None and a.chunk_words < 1: ap.error("--chunk-words debe ser positivo")
    if a.interval:
        MIN_CHUNK = a.interval
    if a.buffer:
        MAX_BUFFER = a.buffer
    if a.chunk_words:
        MAX_PENDING_WORDS = a.chunk_words

    device = a.input_wav or a.device or (default_mic() if a.source == "mic" else default_monitor())
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if a.asr == "whistle":
        from whistle_backend import WhistleModel
        binary = a.whistle_binary or os.path.join(here, ".runtime/whistle/needle")
        weights = a.whistle_weights or os.path.join(here, ".runtime/whistle/whistle.cact")
        if a.lang not in ("en", "es", "de", "fr", "it", "nl", "pl"):
            ap.error("Whistle no admite ese idioma")
        model = WhistleModel(binary, weights, a.threads, keywords=a.keywords,
                             normalize=a.profile == "balanced")
        dev, ctype = "cpu", "Whistle nativo"
    else:
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model
        model_reference=a.model
        if not os.path.isdir(a.model):
            # Reuse either existing cache before allowing a download.
            for cache in (os.path.join(here,'models'),None):
                try:
                    model_reference=download_model(a.model,cache_dir=cache,local_files_only=True)
                    break
                except Exception:
                    pass
        dev, ctype = ("cpu", "int8") if a.cpu else ("cuda", a.compute)
        print(f"cargando '{a.model}' en {dev} ({ctype})...", file=sys.stderr)
        try:
            model = WhisperModel(model_reference, device=dev, compute_type=ctype,
                                 download_root=os.path.join(here, "models"),local_files_only=a.offline)
        except Exception as e:
            print(f"fallo en {dev} ({type(e).__name__}), usando CPU", file=sys.stderr)
            dev, ctype = "cpu", "int8"
            model = WhisperModel(model_reference, device=dev, compute_type=ctype,
                                 download_root=os.path.join(here, "models"),local_files_only=a.offline)
        if terms:
            from vocabulary import WhisperVocabulary
            model=WhisperVocabulary(model,terms)

    if a.mode=='stream' and a.asr=='whisper' and a.stream_engine=='whisperlive' and not os.path.isfile(os.path.join(here,'.runtime','whisperlive','manifest.json')):
        ap.error('Falta backend en vivo: ejecuta python bin/install_streaming.py')
    if a.mode=='stream' and a.asr=='whisper' and a.stream_engine=='whisperlive' and (a.interval is not None or a.buffer is not None or a.utterance_pause is not None):
        ap.error('interval, buffer y utterance-pause pertenecen al motor legacy experimental')
    if a.translator is None: a.translator = "compact" if a.profile in ("light", "balanced") or a.view == "web" else "argos"
    translate = None
    if not a.no_translate and a.lang != a.to:
        try:
            if a.translator == "compact":
                from compact_translation import CompactTranslation
                local_package=os.path.join(here,'.runtime','translation',a.lang+'_'+a.to)
                package = a.translation_package or (local_package if os.path.isdir(local_package) else os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "argos-translate/packages", a.lang + "_" + a.to))
                translate = CompactTranslation(package, a.lang, a.to, a.threads)
            else:
                import argostranslate.translate as tr
                translate = lambda t: tr.translate(t, a.lang, a.to)
            if terms:
                from vocabulary import PreserveTerms
                translate=PreserveTerms(translate,terms,aliases=aliases)
            translate("test")
        except Exception as e:
            translate = None
            print(f"sin traduccion ({e})", file=sys.stderr)

    print(f"\n  modo   : {a.mode}" + ("  (tiempo real)" if a.mode == "stream" else "  (por frases)"),
          file=sys.stderr)
    print(f"  fuente : {device}", file=sys.stderr)
    print(f"  modelo : {a.asr} / {a.model if a.asr == 'whisper' else 'whistle'} en {dev} ({ctype})", file=sys.stderr)
    print(f"  idioma : {a.lang}" + (f" → {a.to}" if translate else " (sin traducir)"),
          file=sys.stderr)
    print("  Ctrl+C para salir\n", file=sys.stderr)

    log_path = None
    if a.save:
        if a.save == "auto":
            outdir = os.path.join(here, "out")
            os.makedirs(outdir, exist_ok=True)
            log_path = os.path.join(outdir, time.strftime("%Y-%m-%d_%H-%M") + ".txt")
        else:
            log_path = a.save
        print(f"  guardando: {log_path}", file=sys.stderr)

    if a.view == "web":
        global DISFLUENCY_MARKER
        if a.disfluency_model:
            from disfluency_marker import DisfluencyMarker
            DISFLUENCY_MARKER = DisfluencyMarker(a.disfluency_model)
        from caption_view import CaptionView
        CAPTION_VIEW = CaptionView(assisted=bool(DISFLUENCY_MARKER),info={'model':a.asr+' / '+(a.model if a.asr=='whisper' else 'Whistle'),'device':dev,'compute':ctype,'keywords':len(terms),'language':a.lang,'target':a.to,'translation_enabled':bool(translate)})
        if a.mode == "stream": a.preview = True
        print(f"  subtítulos: {CAPTION_VIEW.url}", file=sys.stderr)

    q: "queue.Queue" = queue.Queue()
    if a.input_wav:
        def replay():
            with wave.open(a.input_wav, "rb") as f:
                if (f.getnchannels(), f.getsampwidth(), f.getframerate()) != (1, 2, RATE):
                    raise ValueError("Replay requiere WAV PCM16 mono 16kHz")
                while raw := f.readframes(BLOCK):
                    q.put(np.frombuffer(raw, dtype="<i2").astype(np.float32)/32768)
                    time.sleep(len(raw)/2/RATE)
            q.put(None)
        # Validar antes de arrancar un hilo para que un archivo inválido no deje el bucle esperando.
        with wave.open(a.input_wav, "rb") as f:
            if (f.getnchannels(), f.getsampwidth(), f.getframerate()) != (1, 2, RATE):
                ap.error("Replay requiere WAV PCM16 mono 16kHz")
        threading.Thread(target=replay, daemon=True).start()
    else:
        threading.Thread(target=capture, args=(device, q), daemon=True).start()

    try:
        if a.mode == 'stream' and a.asr == 'whisper' and a.stream_engine == 'whisperlive':
            from whisperlive_adapter import run
            a.device_kind=dev
            run(model,q,a,translate,log_path,Output,CAPTION_VIEW)
        else:
            (run_stream if a.mode == "stream" else run_phrase)(model, q, a, translate, log_path)
    except KeyboardInterrupt:
        print("\nfin", file=sys.stderr)
    finally:
        if CAPTION_VIEW:
            if a.state_json:
                with CAPTION_VIEW.lock:
                    print('STATE_JSON:'+json.dumps(CAPTION_VIEW.state,ensure_ascii=False),flush=True)
            CAPTION_VIEW.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
