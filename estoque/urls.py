from django.urls import path
from . import views
app_name = "estoque"
urlpatterns = [path("<int:pk>/codigo-barras.svg", views.codigo_barras, name="codigo_barras"), path("<int:pk>/", views.detalhe, name="detalhe"), path("", views.lista, name="lista"), path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/etiqueta/", views.etiqueta, name="etiqueta"), path("imprimir.pdf", views.imprimir_pdf, name="imprimir_pdf")]
