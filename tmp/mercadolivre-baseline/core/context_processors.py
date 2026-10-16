from .models import ConfiguracaoEmpresa


def identidade_empresa(request):
    # Uma consulta por requisição; nunca usa cache compartilhado entre instalações.
    empresa = ConfiguracaoEmpresa.objects.only("nome_fantasia", "razao_social").first()
    return {"empresa_nome": (empresa.nome_fantasia or empresa.razao_social) if empresa else ""}
