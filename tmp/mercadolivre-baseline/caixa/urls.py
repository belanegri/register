from django.urls import path
from . import views
app_name = "caixa"
urlpatterns = [path("", views.painel, name="painel"), path("<int:pk>/", views.detalhe, name="detalhe")]
