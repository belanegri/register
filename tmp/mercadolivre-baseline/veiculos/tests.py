from datetime import date
from django.test import TestCase
from .catalogo import CATALOGO
from .forms import VeiculoAdminForm
from .models import ModeloVeiculo, Veiculo


class CatalogoTests(TestCase):
    def test_marcas_disponiveis_em_pecas_e_veiculos(self):
        from estoque.forms import PecaAdminForm
        from .marcas import MARCAS
        self.assertEqual(len(MARCAS), 56)
        for form in [VeiculoAdminForm(), PecaAdminForm()]:
            self.assertTrue(set(MARCAS).issubset(dict(form.fields["marca"].choices)))

    def test_nova_marca_permite_informar_modelo(self):
        form = VeiculoAdminForm(data=self.dados(marca="Tesla", modelo="Model 3"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_jac_motors_usa_modelos_existentes(self):
        form = VeiculoAdminForm(data=self.dados(marca="JAC Motors", modelo="J3"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_lista_completa_importada(self):
        esperados = {(marca, nome) for marca, nomes in CATALOGO.items() for nome in nomes.split(", ")}
        self.assertEqual(len(CATALOGO), 41)
        self.assertTrue(esperados.issubset(set(ModeloVeiculo.objects.values_list("marca", "nome"))))

    def dados(self, **extra):
        return {"codigo": "V-TESTE", "marca": "Chevrolet", "modelo": "Onix",
                "data_entrada": date.today(), "situacao": "recebido", **extra}

    def test_cadastro_com_modelo_da_marca(self):
        form = VeiculoAdminForm(data=self.dados())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().modelo, "Onix")

    def test_rejeita_modelo_de_outra_marca(self):
        form = VeiculoAdminForm(data=self.dados(modelo="Gol"))
        self.assertFalse(form.is_valid())
        self.assertIn("modelo", form.errors)

    def test_preserva_veiculo_antigo_fora_do_catalogo(self):
        dados = self.dados(marca="Marca antiga", modelo="Modelo antigo")
        veiculo = Veiculo.objects.create(**dados)
        form = VeiculoAdminForm(data=dados, instance=veiculo)
        self.assertTrue(form.is_valid(), form.errors)
