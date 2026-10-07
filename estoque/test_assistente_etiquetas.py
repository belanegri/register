from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AssistenteEtiquetasTests(TestCase):
    def test_download_exige_login_e_permissao(self):
        url=reverse('estoque:assistente_etiquetas')
        self.assertEqual(self.client.get(url).status_code,302)
        usuario=get_user_model().objects.create_user('sem-impressao')
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(url).status_code,403)

    def test_download_usuario_autorizado(self):
        usuario=get_user_model().objects.create_superuser('instalador-etiquetas')
        self.client.force_login(usuario)
        response=self.client.get(reverse('estoque:assistente_etiquetas'))
        self.assertEqual(response.status_code,200)
        self.assertIn('attachment',response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'],'private, no-store')
        response.close()
