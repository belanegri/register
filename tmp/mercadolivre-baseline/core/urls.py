from django.urls import path
from . import views

app_name = "core"
urlpatterns = [path("empresa/", views.configuracao_empresa, name="configuracao_empresa")]
