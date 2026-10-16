from django.urls import path
from . import views
from . import views_etiquetas
app_name = "estoque"
urlpatterns_assistente = [path('assistente-etiquetas/', views_etiquetas.baixar_assistente, name='assistente_etiquetas')]
urlpatterns = [path("<int:pk>/codigo-barras.svg", views.codigo_barras, name="codigo_barras"), path("<int:pk>/", views.detalhe, name="detalhe"), path("", views.lista, name="lista"), path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/etiqueta/", views.etiqueta, name="etiqueta"), path("imprimir.pdf", views.imprimir_pdf, name="imprimir_pdf")] + urlpatterns_assistente
