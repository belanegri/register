from django.urls import path
from . import views

app_name='fiscal'
urlpatterns=[
    path('',views.lista,name='lista'),
    path('nfe/',views.lista,{'modelo':'55'},name='nfe'),
    path('nfce/',views.lista,{'modelo':'65'},name='nfce'),
    path('nfse/',views.lista,{'modelo':'nfse'},name='nfse'),
    path('pendentes/',views.lista,{'secao':'pendentes'},name='pendentes'),
    path('documentos/',views.lista,{'secao':'documentos'},name='documentos'),
    path('solicitar/',views.solicitar,name='solicitar'),
    path('configuracao/',views.configuracao,name='configuracao'),
    path('configuracao/sequencia/',views.sequencia,name='sequencia'),
    path('parametros/<str:tipo>/',views.parametros,name='parametros'),
    path('parametros/<str:tipo>/<int:pk>/',views.parametros,name='parametro_editar'),
    path('eventos/',views.eventos,name='eventos'),
    path('eventos/inutilizar/',views.inutilizar,name='inutilizar'),
    path('eventos/<int:pk>/',views.evento,name='evento'),
    path('eventos/<int:pk>/transmitir/',views.transmitir_evento,name='transmitir_evento'),
    path('eventos/<int:pk>/consultar/',views.consultar_evento,name='consultar_evento'),
    path('<int:pk>/',views.detalhe,name='detalhe'),
    path('<int:pk>/cancelar/',views.cancelar,name='cancelar'),
    path('<int:pk>/contingencia/',views.contingencia,name='contingencia'),
    path('<int:pk>/xml/',views.xml,name='xml'),
    path('<int:pk>/auxiliar/',views.auxiliar,name='auxiliar'),
    path('<int:pk>/<str:operacao>/',views.acao,name='acao'),
]
