"""Split confirmed words using their existing timestamps; no added model."""
class PauseBoundaries:
    def __init__(self, pause=1.0):
        self.pause = pause
        self.last_word_end = None
        self.used_until = -1.0
        self.audio_until = 0.0
        self.silent_tail = False

    def observe(self, audio, offset, rate=16000):
        import numpy as np
        self.audio_until = offset+len(audio)/rate
        tail = audio[-int(self.pause*rate):]
        self.silent_tail = len(tail)>=int(self.pause*rate) and float(np.sqrt(np.mean(tail**2))) < 0.004

    def emit(self, words, offset, output):
        text = ''
        for word in words:
            start, end = offset+word.start, offset+word.end
            if self.last_word_end is not None and start-self.last_word_end >= self.pause:
                if text: output.add(text); text = ''
                output.flush()
                self.used_until = self.last_word_end
            text += word.word
            self.last_word_end = end
        if text: output.add(text)

    def settle(self, pending_hypothesis, output):
        if (not pending_hypothesis and self.last_word_end is not None and self.silent_tail
            and self.last_word_end > self.used_until
            and self.audio_until-self.last_word_end >= self.pause):
            output.flush()
            self.used_until = self.last_word_end
