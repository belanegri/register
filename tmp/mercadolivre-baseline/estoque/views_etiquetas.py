from pathlib import Path
from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse, Http404


@login_required
@permission_required('estoque.view_peca', raise_exception=True)
def baixar_assistente(request):
    arquivo = Path(settings.BASE_DIR) / 'scripts' / 'releases' / 'REGISTER-Etiquetas-Windows.zip'
    if not arquivo.is_file():
        raise Http404('Assistente de etiquetas ainda não disponibilizado nesta instalação.')
    response = FileResponse(arquivo.open('rb'), as_attachment=True, filename=arquivo.name,
                            content_type='application/zip')
    response['Cache-Control'] = 'private, no-store'
    return response
