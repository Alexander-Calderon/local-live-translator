"""Bounded vocabulary hints using the backend's own hotword support."""
from pathlib import Path
import json
import re

def read_aliases(path, terms):
    file=Path(path).resolve(strict=True)
    if file.stat().st_size>8192:raise ValueError('Las variantes admiten como máximo 8 KiB')
    data=json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or len(data)>100:raise ValueError('Variantes inválidas')
    if any(not isinstance(k,str) or not isinstance(v,str) or not k.strip() or len(k)>160 or v not in terms for k,v in data.items()):
        raise ValueError('Cada variante debe apuntar a un término del vocabulario')
    return data

def read_keywords(path):
    file=Path(path).resolve(strict=True)
    if file.stat().st_size>8192:raise ValueError('El vocabulario admite como máximo 8 KiB')
    text=file.read_text(encoding='utf-8')
    if '\0' in text or len(text.splitlines())>100:
        raise ValueError('Vocabulario inválido: máximo 100 términos sin NUL')
    terms=list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')))
    if any(len(term)>160 for term in terms):raise ValueError('Un término excede 160 caracteres')
    return terms

class WhisperVocabulary:
    def __init__(self,model,terms):
        self.model=model
        self.hints=', '.join(terms)
    def transcribe(self,*args,**kwargs):
        if self.hints:kwargs.setdefault('hotwords',self.hints)
        return self.model.transcribe(*args,**kwargs)

class PreserveTerms:
    """Keep exact glossary terms through translation, without rewriting ASR."""
    def __init__(self,translate,terms,aliases=None):
        self.translate=translate
        self.terms={term.lower():term for term in terms}
        self.pattern=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(term) for term in sorted(terms,key=len,reverse=True))+r')(?!\w)',re.I)
        self.fallbacks=0
        self.aliases=aliases or {}
        self.alias_pattern=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(term) for term in sorted(self.aliases,key=len,reverse=True))+r')(?!\w)',re.I) if self.aliases else None
        self.alias_lookup={key.lower():value for key,value in self.aliases.items()}

    def __call__(self,text):
        original=text
        if self.alias_pattern:
            text=self.alias_pattern.sub(lambda match:self.alias_lookup[match.group().lower()],text)
        replacements=[]
        if 'QZTERM' in text:return self.translate(text)
        def protect(match):
            index=len(replacements);replacements.append(self.terms[match.group().lower()])
            return f'QZTERM{index}ZQ'
        protected=self.pattern.sub(protect,text)
        if not replacements:return self.translate(text)
        translated=self.translate(protected)
        # A lost/duplicated marker is a failed preservation attempt, not a name.
        for index,term in enumerate(replacements):
            marker=f'QZTERM{index}ZQ'
            if translated.count(marker)!=1:
                self.fallbacks+=1
                return self.translate(original)
        for index,term in enumerate(replacements):
            translated=translated.replace(f'QZTERM{index}ZQ',term)
        return translated
