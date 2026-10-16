from django.conf import settings
from .models import ConfiguracaoEmpresa


def empresa_atual():
    empresa = ConfiguracaoEmpresa.objects.first()
    if not empresa:
        return {}
    campos = ("nome_fantasia", "razao_social", "documento", "endereco", "numero",
              "complemento", "bairro", "cidade", "estado", "cep", "telefone")
    return {campo: getattr(empresa, campo) for campo in campos}


def nome_empresa(dados):
    return dados.get("nome_fantasia") or dados.get("razao_social") or "REGISTER — empresa não configurada"


def identidade_relatorio():
    # Compatibilidade somente para instalações legadas; Loja 2 desativa explicitamente.
    if settings.LEGACY_PONTOCAR_DOCUMENTS:
        return "PontoCar Comércio de Peças"
    return nome_empresa(empresa_atual())
