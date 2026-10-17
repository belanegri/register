from django import forms
from django.test import SimpleTestCase

from core.templatetags.formularios import organizar_formulario
from fiscal.forms import (ConfiguracaoForm, SolicitacaoForm, JustificativaForm,
                          InutilizacaoForm, ProdutoForm, ServicoForm, SequenciaForm)


class OrganizacaoFormularioTests(SimpleTestCase):
    def test_todos_campos_fiscais_continuam_disponiveis_uma_vez(self):
        for classe in (ConfiguracaoForm, SolicitacaoForm, JustificativaForm, InutilizacaoForm,
                       ProdutoForm, ServicoForm, SequenciaForm):
            with self.subTest(form=classe.__name__):
                form = classe()
                campos = [item["field"].name for grupo in organizar_formulario(form) for item in grupo["campos"]]
                self.assertCountEqual(campos, [f.name for f in form.visible_fields()])
                self.assertEqual(len(campos), len(set(campos)))

    def test_campo_novo_nao_desaparece_e_oculto_nao_duplica(self):
        class NovoFormulario(forms.Form):
            descricao = forms.CharField()
            chave = forms.CharField(widget=forms.HiddenInput)
        form = NovoFormulario()
        campos = [item["field"].name for grupo in organizar_formulario(form) for item in grupo["campos"]]
        self.assertEqual(campos, ["descricao"])
