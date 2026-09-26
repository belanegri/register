from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "PontoCar Comércio de Peças"
admin.site.site_title = "PontoCar"
admin.site.index_title = "Cadastros e administração"
urlpatterns = [
    path("admin/", admin.site.urls),
    path("conta/", include("accounts.urls")),
    path("estoque/", include("estoque.urls")),
    path("clientes/", include("clientes.urls")),
    path("vendas/", include("vendas.urls")),
    path("contas-a-pagar/", include("contas.urls")),
    path("caixa/", include("caixa.urls")),
    path("", include("dashboard.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
