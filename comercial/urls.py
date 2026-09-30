from django.urls import path
from . import views
app_name='comercial'
urlpatterns=[
path('servicos/',views.servicos,name='servicos'),path('servicos/novo/',views.servico_editar,name='servico_novo'),path('servicos/<int:pk>/',views.servico_editar,name='servico_editar'),
path('documentos/<str:tipo>/',views.documentos,name='documentos'),path('documentos/<str:tipo>/novo/',views.documento_editar,name='novo'),
path('documento/<int:pk>/',views.detalhe,name='detalhe'),path('documento/<int:pk>/editar/',views.documento_editar,name='editar'),path('documento/<int:pk>/converter/<str:destino>/',views.conversao,name='converter'),path('documento/<int:pk>/pdf/<str:formato>/',views.imprimir,name='pdf'),
path('receber/',views.contas,name='contas'),path('receber/nova/',views.conta_nova,name='conta_nova'),path('receber/<int:pk>/',views.conta,name='conta'),path('receber/<int:pk>/cancelar/',views.conta_cancelar,name='conta_cancelar')]
