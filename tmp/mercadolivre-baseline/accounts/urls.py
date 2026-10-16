from django.contrib.auth import views
from django.urls import path

app_name = "accounts"
urlpatterns = [
    path("entrar/", views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("sair/", views.LogoutView.as_view(), name="logout"),
    path("senha/", views.PasswordChangeView.as_view(
        template_name="registration/password_change.html", success_url="/"), name="password_change"),
]
