from pathlib import Path
import shutil


ARQUIVOS = [
    Path("comercial/pdf.py"),
    Path("comercial/views.py"),
    Path("templates/comercial/detalhe.html"),
]


# Sequências corrompidas -> texto correto.
# As maiores ficam primeiro para evitar substituições parciais.
CORRECOES = {
    # Corrupção dupla
    "INFORMAÃ‡Ã•ES": "INFORMAÇÕES",
    "OBSERVAÃ‡Ã•ES": "OBSERVAÇÕES",
    "CONDIÃ‡Ã•ES": "CONDIÇÕES",
    "SITUAÃ‡ÃƒO": "SITUAÇÃO",
    "DESCRIÃ‡ÃƒO": "DESCRIÇÃO",
    "EMISSÃƒO": "EMISSÃO",
    "PREVISÃƒO": "PREVISÃO",
    "CONCLUSÃƒO": "CONCLUSÃO",

    # Corrupção simples
    "PÃ¡gina": "Página",
    "CABEÃ‡ALHO": "CABEÇALHO",
    "ORÃ‡AMENTO": "ORÇAMENTO",
    "OrÃ§amento": "Orçamento",
    "OrÃ§amentos": "Orçamentos",
    "orÃ§amento": "orçamento",
    "orÃ§amentos": "orçamentos",

    "SERVIÃ‡O": "SERVIÇO",
    "SERVIÃ‡OS": "SERVIÇOS",
    "ServiÃ§o": "Serviço",
    "ServiÃ§os": "Serviços",
    "serviÃ§o": "serviço",
    "serviÃ§os": "serviços",

    "PEÃ‡AS": "PEÇAS",
    "PeÃ§as": "Peças",
    "PeÃ§a": "Peça",

    "DESCRIÃ‡ÃO": "DESCRIÇÃO",
    "DescriÃ§Ã£o": "Descrição",
    "descriÃ§Ã£o": "descrição",

    "IdentificaÃ§Ã£o": "Identificação",
    "identificaÃ§Ã£o": "identificação",

    "VEÃ\x8dCULO": "VEÍCULO",
    "VeÃ\xadculo": "Veículo",
    "veÃ\xadculo": "veículo",

    "EndereÃ§o": "Endereço",
    "endereÃ§o": "endereço",

    "CombustÃ\xadvel": "Combustível",
    "combustÃ\xadvel": "combustível",

    "MÃƒO": "MÃO",
    "MÃ£o": "Mão",

    "UNITÃ\x81RIO": "UNITÁRIO",
    "unitÃ¡rio": "unitário",

    "TÃ‰CNICO": "TÉCNICO",
    "TÃ©cnico": "Técnico",
    "tÃ©cnico": "técnico",

    "RESPONSÃ\x81VEL": "RESPONSÁVEL",
    "ResponsÃ¡vel": "Responsável",
    "responsÃ¡vel": "responsável",

    "DIAGNÃ“STICO": "DIAGNÓSTICO",
    "DiagnÃ³stico": "Diagnóstico",
    "diagnÃ³stico": "diagnóstico",

    "RODAPÃ‰": "RODAPÉ",

    "nÃ£o": "não",
    "NÃƒO": "NÃO",
    "situaÃ§Ã£o": "situação",
    "confirmaÃ§Ã£o": "confirmação",
    "invÃ¡lida": "inválida",
    "histÃ³rico": "histórico",
    "cobranÃ§a": "cobrança",
    "aÃ§Ã£o": "ação",
    "poderÃ¡": "poderá",
    "lanÃ§ado": "lançado",
    "recebimento Ã©": "recebimento é",

    "Ãºnica": "única",
    "DivisÃµes": "Divisões",
    "CabeÃ§alho": "Cabeçalho",
    "legÃ\xadvel": "legível",
    "EspaÃ§amento": "Espaçamento",
    "numÃ©ricos": "numéricos",
    "pÃ¡gina": "página",
    "SeparaÃ§Ã£o": "Separação",

    # Pontuação corrompida
    "â€¢": "•",
    "Â·": "·",
    "â€”": "—",
    "â†’": "→",
}


def corrigir(path: Path):
    if not path.exists():
        print(f"NÃO ENCONTRADO: {path}")
        return

    # Backup automático específico deste reparo
    backup = path.with_name(path.name + ".antes_correcao_encoding")
    shutil.copy2(path, backup)

    texto = path.read_text(encoding="utf-8")

    # Remove BOM real, caso exista.
    texto = texto.lstrip("\ufeff")

    total = 0

    # Maiores sequências primeiro.
    for errado, correto in sorted(
        CORRECOES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        quantidade = texto.count(errado)

        if quantidade:
            texto = texto.replace(errado, correto)
            total += quantidade

    # detalhamento comercial:
    # remove somente o botão de impressão térmica 58 mm.
    if path.as_posix() == "templates/comercial/detalhe.html":
        botao_58 = (
            '<a class="btn btn-outline-primary" target="_blank" '
            'href="{% url \'comercial:pdf\' doc.pk \'58\' %}">'
            'IMPRIMIR 58MM</a>'
        )

        if botao_58 in texto:
            texto = texto.replace(botao_58, "")
            total += 1
            print("  Botão 58 mm removido.")

    path.write_text(
        texto,
        encoding="utf-8",
        newline="\n",
    )

    print(f"OK: {path} — {total} correção(ões)")


print("=== CORREÇÃO DE ENCODING ===")

for arquivo in ARQUIVOS:
    corrigir(arquivo)

print("=== CONCLUÍDO ===")