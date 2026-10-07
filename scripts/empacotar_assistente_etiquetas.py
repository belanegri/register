"""Executar no Windows com PyInstaller, pypdfium2, pypdf e Pillow instalados."""
from pathlib import Path
import shutil
import zipfile
import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / '.local' / 'etiquetas-distribuicao'
PyInstaller.__main__.run(['--noconfirm','--clean','--onedir','--windowed','--noupx',
    '--name','REGISTER-Etiquetas','--distpath',str(BUILD/'dist'),'--workpath',str(BUILD/'work'),
    '--specpath',str(BUILD),'--collect-all','pypdfium2','--collect-all','pypdfium2_raw',
    str(ROOT/'scripts/servidor_etiqueta_windows.py')])
destino=ROOT/'scripts/releases';destino.mkdir(exist_ok=True)
arquivo=destino/'REGISTER-Etiquetas-Windows.zip'
with zipfile.ZipFile(arquivo,'w',zipfile.ZIP_DEFLATED) as pacote:
    pasta=BUILD/'dist'
    for item in (pasta/'REGISTER-Etiquetas').rglob('*'):
        if item.is_file():pacote.write(item,item.relative_to(pasta))
    for origem,nome in [('instalar_assistente_etiquetas.ps1','instalar_assistente_etiquetas.ps1'),
                         ('Instalar-Etiquetas.cmd','Instalar-Etiquetas.cmd'),('GUIA-ETIQUETAS.txt','GUIA-ETIQUETAS.txt')]:
        pacote.write(ROOT/'scripts'/origem,nome)
print('PACOTE:',arquivo,'BYTES:',arquivo.stat().st_size)
