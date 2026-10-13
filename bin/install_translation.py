"""Install official EN<->ES Argos data without importing Stanza or torch."""
import argparse,json,os,urllib.request,zipfile,tempfile,shutil,stat,hashlib
from pathlib import Path

def safe_extract(archive,destination):
    destination=destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            path=(destination/member.filename).resolve()
            if not path.is_relative_to(destination) or stat.S_ISLNK(member.external_attr>>16):
                raise ValueError('Ruta inválida en el paquete')
        if sum(member.file_size for member in bundle.infolist())>512*1024*1024:
            raise ValueError('El paquete excede el límite de 512 MiB descomprimidos')
        bundle.extractall(destination)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package-file',type=Path,help='paquete .argosmodel descargado previamente')
    parser.add_argument('--pair',choices=['en_es','es_en'],default='en_es')
    parser.add_argument('--target',type=Path)
    args=parser.parse_args();source,dest=args.pair.split('_');target=(args.target or Path(__file__).resolve().parents[1]/'.runtime/translation'/args.pair).resolve()
    url='https://data.argosopentech.com/argospm/v1/translate-'+args.pair+'-1_0.argosmodel'
    global_package=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'argos-translate/packages'/args.pair
    if args.target is None and not target.exists() and (global_package/'metadata.json').is_file():
        metadata=json.loads((global_package/'metadata.json').read_text())
        if (metadata.get('from_code'),metadata.get('to_code'))==(source,dest) and (global_package/'sentencepiece.model').is_file() and (global_package/'model/model.bin').is_file():
            print('Se reutiliza el paquete global '+args.pair+'.');return
    if target.exists():
        metadata=json.loads((target/'metadata.json').read_text())
        if (metadata.get('from_code'),metadata.get('to_code'))!=(source,dest):raise ValueError('El destino contiene otro paquete')
        print('El paquete '+args.pair+' ya existe; se conserva.');return
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent,prefix='install-'+args.pair+'-') as directory:
        staging=Path(directory);archive=args.package_file
        if archive is None:
            archive=staging/(args.pair+'.argosmodel')
            with urllib.request.urlopen(url,timeout=45) as response,archive.open('wb') as output:
                shutil.copyfileobj(response,output)
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        safe_extract(archive,staging/'unpacked')
        candidates=list((staging/'unpacked').rglob('metadata.json'))
        if len(candidates)!=1:raise ValueError('Estructura inesperada del paquete')
        package=candidates[0].parent;metadata=json.loads(candidates[0].read_text())
        if (metadata.get('from_code'),metadata.get('to_code'))!=(source,dest) or metadata.get('target_prefix'):
            raise ValueError('Paquete no compatible con el traductor compacto')
        if not (package/'model/model.bin').is_file() or not (package/'sentencepiece.model').is_file():
            raise ValueError('Faltan los pesos o tokenizer')
        (package/'download-manifest.json').write_text(json.dumps({'source':args.package_file.name if args.package_file else url,'sha256':digest},indent=2))
        shutil.move(str(package),str(target))
    print('Paquete '+args.pair+' instalado en '+str(target))

if __name__=='__main__':main()
