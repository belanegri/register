from django.urls import path
from . import views
from .etiquetas_entrega import etiquetas_entrega, destinatario_cliente

app_name = "core"
urlpatterns = [path("etiquetas-entrega/", etiquetas_entrega, name="etiquetas_entrega"),
    path("etiquetas-entrega/clientes/<int:pk>/", destinatario_cliente, name="destinatario_cliente"), path("empresa/", views.configuracao_empresa, name="configuracao_empresa")]
