from django.urls import path
from . import views
app_name="contas"
urlpatterns = [path('<int:pk>/excluir/', views.excluir, name='excluir')]
urlpatterns += [path("anexos/<int:pk>/editar/",views.editar_anexo,name="editar_anexo"),path("anexos/<int:pk>/excluir/",views.excluir_anexo,name="excluir_anexo"),path("relatorio.pdf",views.pdf_relatorio,name="pdf_relatorio"),path("<int:pk>/conta.pdf",views.pdf_individual,name="pdf_individual"),path("<int:pk>/anexar/",views.anexar,name="anexar"),path("anexos/<int:pk>/baixar/",views.baixar_anexo,name="baixar_anexo"),path("",views.lista,name="lista"),path("nova/",views.nova,name="nova"),path("<int:pk>/",views.detalhe,name="detalhe"),path("<int:pk>/editar/",views.editar,name="editar"),path("<int:pk>/pagar/",views.pagar,name="pagar"),path("<int:pk>/cancelar/",views.cancelar,name="cancelar")]
