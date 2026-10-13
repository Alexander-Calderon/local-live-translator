"""Optional local annotation. Keeps every original word and never rewrites text."""
import json,re
from pathlib import Path

class DisfluencyMarker:
    def __init__(self, directory, threshold=0.95):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        ort.disable_telemetry_events()
        directory=Path(directory).resolve(strict=True)
        labels=json.loads((directory/'config.json').read_text())['id2label']
        if 'DELETE' not in labels.values():
            raise ValueError('El modelo debe declarar etiquetas KEEP/DELETE')
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(directory/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(directory/'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=128)
        self.labels=labels;self.threshold=threshold

    def __call__(self,text):
        import numpy as np
        matches=list(re.finditer(r'\S+',text))
        if not matches:return []
        encoding=self.tokenizer.encode([m.group() for m in matches],is_pretokenized=True)
        values={'input_ids':[encoding.ids],'attention_mask':[encoding.attention_mask],'token_type_ids':[encoding.type_ids]}
        logits=self.session.run(None,{item.name:np.asarray(values[item.name],dtype=np.int64) for item in self.session.get_inputs()})[0][0]
        probabilities=np.exp(logits-logits.max(axis=-1,keepdims=True))
        probabilities/=probabilities.sum(axis=-1,keepdims=True)
        seen=set();spans=[]
        for index,word in enumerate(encoding.word_ids):
            if word is None or word in seen:continue
            seen.add(word);label=int(probabilities[index].argmax());score=float(probabilities[index,label])
            if self.labels[str(label)]!='DELETE' or score<self.threshold:continue
            match=matches[word]
            # Keep negations/numbers visually prominent, even if a model errs.
            if re.search(r'\d',match.group()) or match.group().strip('.,!?;:').lower() in {'no','not','never','without','cannot',"don't"}:continue
            spans.append({'start':match.start(),'end':match.end(),'confidence':score})
        return spans
