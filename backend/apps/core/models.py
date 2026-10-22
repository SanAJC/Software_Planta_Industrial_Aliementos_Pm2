import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.db import models

from .versionado import siguiente_version


# --------------------------------------------------------------------------
# Bases abstractas
# --------------------------------------------------------------------------
class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class Versionado(models.Model):
    """Marca de versión global para la sincronización de catálogos."""

    version_sync = models.BigIntegerField(default=0, db_index=True, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.version_sync = siguiente_version()
        super().save(*args, **kwargs)


class CatalogoBase(UUIDModel, Versionado):
    """[K] Catálogo versionado. Nunca se borra: se desactiva."""

    activo = models.BooleanField(default=True)

    class Meta:
        abstract = True


class CapturaBase(UUIDModel):
    """[C] Registro capturado. El UUID lo genera la tablet.

    Nada se borra: una corrección es un registro nuevo o una anulación con motivo.
    """

    evento_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False,
        help_text="Evento de sincronización que creó el registro",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    dispositivo = models.ForeignKey(
        "core.Dispositivo", on_delete=models.PROTECT, related_name="+",
        null=True, blank=True, help_text="Vacío si se capturó en el panel web",
    )
    hora_dispositivo = models.DateTimeField()
    recibido_en = models.DateTimeField(auto_now_add=True)
    anulado = models.BooleanField(default=False)
    motivo_anulacion = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Los registros capturados no se borran; se anulan con motivo.")


# --------------------------------------------------------------------------
# Usuarios, estaciones y dispositivos
# --------------------------------------------------------------------------
class Rol(models.TextChoices):
    OPERARIO = "operario", "Operario"
    SUPERVISOR = "supervisor", "Supervisor"
    INGENIERA = "ingeniera", "Ingeniera de alimentos"
    SEDE = "sede", "Sede"
    ADMIN = "admin", "Administrador"


class Usuario(AbstractUser, Versionado):
    """Persona que usa el sistema. Opera en tablet con PIN y en el panel con contraseña."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=50)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.OPERARIO)
    documento = models.CharField(max_length=20, unique=True, null=True, blank=True)
    pin_hash = models.CharField(
        max_length=128, blank=True,
        help_text="make_password(pin): el hash ya incluye la sal",
    )
    sede = models.ForeignKey(
        "catalogos.Sede", on_delete=models.PROTECT, null=True, blank=True,
        related_name="usuarios", help_text="Solo para el rol sede",
    )

    class Meta:
        verbose_name = "usuario"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(rol="sede") | models.Q(sede__isnull=False),
                name="usuario_sede_requiere_sede",
            ),
        ]

    @property
    def puede_liberar(self):
        return self.rol in (Rol.SUPERVISOR , Rol.INGENIERA)

    @property
    def puede_verificar_limpieza(self):
        return self.rol in (Rol.SUPERVISOR, Rol.INGENIERA)

class Estacion(CatalogoBase):
    """Puesto de trabajo de la planta.

    Tres pantallas en planta y un PC de oficina:
    1. Recepción: recepción, báscula y C.F. materia prima (CF1).
    2. Cocina: cocción y sus tiempos.
    3. Sala de proceso: marinado, porcionado, empaque al vacío, ultracongelador,
       C.F. producto terminado (CF2) y despacho.
    El PC de oficina usa el panel web (ingeniera, administración, reportes).
    """

    class Tipo(models.TextChoices):
        RECEPCION = "recepcion", "Recepción y C.F. materia prima"
        COCINA = "cocina", "Cocina (cocción y tiempos)"
        SALA_PROCESO = "sala_proceso", "Sala de proceso (marinado, empaque, ultracongelador, C.F. terminado y despacho)"
        OFICINA = "oficina", "PC de oficina (panel web)"

    nombre = models.CharField(max_length=80, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    ubicacion = models.ForeignKey(
        "catalogos.Ubicacion", on_delete=models.PROTECT, null=True, blank=True,
        related_name="estaciones",
    )

    class Meta:
        verbose_name = "estación"
        verbose_name_plural = "estaciones"

    def __str__(self):
        return self.nombre


class Dispositivo(UUIDModel):
    """Pantalla fija de una estación o celular personal (limpieza), con token revocable."""

    class Tipo(models.TextChoices):
        ESTACION = "estacion", "Pantalla fija de estación"
        CELULAR = "celular", "Celular personal"

    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.ESTACION)
    token_hash = models.CharField(max_length=128, unique=True)
    estacion = models.ForeignKey(
        Estacion, on_delete=models.PROTECT, null=True, blank=True, related_name="dispositivos",
        help_text="Obligatoria para pantallas fijas; vacía para celulares",
    )
    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="celulares",
        help_text="Dueño del celular; solo él puede iniciar sesión en ese dispositivo",
    )
    activo = models.BooleanField(default=True)
    revocado_en = models.DateTimeField(null=True, blank=True)
    ultima_sync = models.DateTimeField(null=True, blank=True)
    version_catalogo_descargada = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(tipo="estacion") & models.Q(estacion__isnull=False))
                | (models.Q(tipo="celular") & models.Q(propietario__isnull=False)),
                name="dispositivo_estacion_o_propietario",
            ),
        ]

    def __str__(self):
        return self.nombre


class Auditoria(UUIDModel):
    """Historial de cambios. Solo se inserta: no se edita ni se borra."""

    entidad = models.CharField(max_length=80)
    entidad_id = models.CharField(max_length=64)
    accion = models.CharField(max_length=20)
    antes = models.JSONField(null=True, blank=True)
    despues = models.JSONField(null=True, blank=True)
    motivo = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )
    dispositivo = models.ForeignKey(
        Dispositivo, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "auditoría"
        indexes = [models.Index(fields=["entidad", "entidad_id"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionDenied("La auditoría no se edita.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("La auditoría no se borra.")