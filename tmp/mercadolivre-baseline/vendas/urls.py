from django.urls import path
from . import views
app_name = "vendas"
urlpatterns = [path("<int:pk>/recibo/", views.recibo, name="recibo"), path("", views.lista, name="lista"), path("pdv/", views.pdv, name="pdv"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("promissorias/<int:pk>/imprimir/", views.promissoria, name="promissoria"),
    path("promissorias/<int:pk>/receber/", views.receber_promissoria, name="receber_promissoria"),
    path("carrinho/", views.carrinho, name="carrinho"), path("finalizar/", views.finalizar, name="finalizar"),
    path("relatorios/", views.relatorios, name="relatorios"), path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"), path("<int:pk>/devolver/", views.devolver, name="devolver")]
