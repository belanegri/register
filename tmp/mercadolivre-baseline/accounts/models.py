from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Usuário próprio desde a primeira migration; papéis via auth.Group."""

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
