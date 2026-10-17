from django.urls import path
from . import views

app_name = "mercadolivre"
urlpatterns = [
    path("", views.painel, name="painel"),
    path("oauth/conectar/", views.autorizar, name="autorizar"),
    path("oauth/callback/", views.callback, name="callback"),
    path("desconectar/", views.desconectar, name="desconectar"),
    path("importar/", views.importar, name="importar"),
    path("anuncios/<int:pk>/vincular/", views.vincular, name="vincular"),
    path("anuncios/<int:pk>/desvincular/", views.desvincular, name="desvincular"),
    path("pecas/<int:pk>/", views.selecionar, name="selecionar"),
    path("pecas/<int:pk>/preparar/", views.preparar_publicacao, name="preparar_publicacao"),
    path("publicacoes/<uuid:pk>/", views.revisar_publicacao, name="revisar_publicacao"),
]
