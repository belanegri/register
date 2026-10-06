from django.urls import path
from . import views
from . import financeiro_views
app_name='comercial'
urlpatterns_financeiro = [
path('receber/<int:pk>/parcelamento/', financeiro_views.parcelamento, name='conta_parcelamento'),
path('receber/<int:pk>/excluir/', financeiro_views.excluir, name='conta_excluir'),
path('receber/<int:pk>/imprimir/', financeiro_views.imprimir, name='conta_imprimir'),
]
urlpatterns=[
path('servicos/',views.servicos,name='servicos'),path('servicos/novo/',views.servico_editar,name='servico_novo'),path('servicos/<int:pk>/',views.servico_editar,name='servico_editar'),
path('documentos/<str:tipo>/',views.documentos,name='documentos'),path('documentos/<str:tipo>/novo/',views.documento_editar,name='novo'),
path('documento/<int:pk>/',views.detalhe,name='detalhe'),path('documento/<int:pk>/excluir/',views.orcamento_excluir,name='excluir'),path('documento/<int:pk>/editar/',views.documento_editar,name='editar'),path('documento/<int:pk>/converter/<str:destino>/',views.conversao,name='converter'),path('documento/<int:pk>/pdf/<str:formato>/',views.imprimir,name='pdf'),
path('receber/',views.contas,name='contas'),path('receber/nova/',views.conta_nova,name='conta_nova'),path('receber/<int:pk>/',views.conta,name='conta'),path('receber/<int:pk>/cancelar/',views.conta_cancelar,name='conta_cancelar')] + urlpatterns_financeiro
