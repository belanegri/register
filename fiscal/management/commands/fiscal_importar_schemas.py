from pathlib import Path
from zipfile import ZipFile
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from lxml import etree


class Command(BaseCommand):
    help='Importa apenas XSD de um pacote oficial obtido na SEFAZ/Portal NFS-e.'

    def add_arguments(self,parser):
        parser.add_argument('arquivo')
        parser.add_argument('--modelo',choices=['nfe','nfse'],required=True)
        parser.add_argument('--versao',default='',help='Pasta da versão no ZIP, quando houver versões distintas.')

    def handle(self,**options):
        base=Path(settings.FISCAL_SCHEMA_DIR).resolve()
        destino=base/options['modelo'];destino.mkdir(parents=True,exist_ok=True)
        quantidade=0
        with ZipFile(options['arquivo']) as pacote:
            for info in pacote.infolist():
                if not info.filename.lower().endswith('.xsd') or (options['versao'] and options['versao'] not in info.filename):continue
                if info.file_size>5*1024*1024:raise CommandError('XSD muito grande.')
                alvo=(destino/Path(info.filename).name).resolve()
                if not alvo.is_relative_to(destino):raise CommandError('Caminho inválido.')
                dados=pacote.read(info)
                try:
                    xml=etree.fromstring(dados,etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
                    if xml.tag!='{http://www.w3.org/2001/XMLSchema}schema':raise ValueError
                    for elem in xml.xpath('//*[local-name()="include" or local-name()="import"]'):
                        ref=elem.get('schemaLocation','')
                        if ref and ('://' in ref or '/' in ref or '\\' in ref or ':' in ref):raise ValueError
                except (ValueError,etree.XMLSyntaxError):raise CommandError('Pacote contém um esquema inválido ou referência externa.') from None
                alvo.write_bytes(dados);quantidade+=1
        if not quantidade:raise CommandError('Nenhum XSD encontrado para a versão selecionada.')
        self.stdout.write(f'{quantidade} esquemas importados. Valide a homologação antes de liberar operações.')
