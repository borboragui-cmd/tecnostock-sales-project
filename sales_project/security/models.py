from django.conf import settings
from django.db import models

from shared.validators import validate_cedula_ec


class UserProfile(models.Model):
    """Datos adicionales del usuario que no viven en auth.User (mismo
    motivo que en el punto 5.2: no se migra a un AUTH_USER_MODEL custom
    por lo invasivo que sería reescribir las FKs existentes hacia
    auth.User — esto es una tabla nueva y separada, no un campo agregado
    a User). La relación es opcional: los usuarios creados antes de este
    punto no tienen fila de perfil, no se les hizo backfill."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile',
    )
    cedula = models.CharField(
        max_length=10, unique=True, verbose_name='Cédula',
        validators=[validate_cedula_ec],
    )

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuario'

    def __str__(self):
        return f'Perfil de {self.user.username} — {self.cedula}'
