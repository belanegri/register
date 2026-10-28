from django.urls import path
from . import views
app_name = "clientes"
urlpatterns = [path("dados-fiscais/", views.dados_fiscais, name="dados_fiscais"), path("cep/", views.consultar_cep, name="consultar_cep"), path("", views.lista, name="lista"), path("novo/", views.editar, name="novo"),
    path("<int:pk>/", views.detalhe, name="detalhe"), path("<int:pk>/editar/", views.editar, name="editar")]
