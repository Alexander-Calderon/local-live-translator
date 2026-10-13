"""Translate already segmented caption blocks with an installed Argos SentencePiece package.
No downloads, paragraph sentencizer, pivot languages or torch imports.
"""
import json
from pathlib import Path
import ctranslate2
import sentencepiece

class CompactTranslation:
    def __init__(self, package, source='en', target='es', threads=4):
        package=Path(package).resolve(strict=True)
        metadata=json.loads((package/'metadata.json').read_text())
        if (metadata.get('from_code'),metadata.get('to_code')) != (source,target):
            raise ValueError('El paquete de traducción no coincide con los idiomas solicitados')
        if metadata.get('target_prefix'):
            raise ValueError('Este adaptador no admite paquetes con target_prefix')
        self.tokenizer=sentencepiece.SentencePieceProcessor(model_file=str(package/'sentencepiece.model'))
        self.model=ctranslate2.Translator(str(package/'model'),device='cpu',compute_type='int8',inter_threads=1,intra_threads=threads)
    def __call__(self,text):
        if not text.strip():return ''
        if len(text)>4000:raise ValueError('La traducción compacta recibe bloques de subtítulos, no documentos')
        tokens=self.tokenizer.encode(text,out_type=str)
        output=self.model.translate_batch([tokens],replace_unknowns=True,beam_size=4,num_hypotheses=1,length_penalty=.2)[0]
        return self.tokenizer.decode(output.hypotheses[0]).strip()
