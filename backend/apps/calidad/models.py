rom django.conf import settings
from django.db import models

from core.models import CapturaBase, CatalogoBase
from inventario.models import EstadoCalidad


class HistorialEstadoLote(CapturaBase):
    """Cada cambio de estado de calidad de un lote. Liberar exige rol ingeniera."""

    lote = models.ForeignKey("inventario.Lote", on_delete=models.PROTECT, related_name="historial_estados")
    estado_anterior = models.CharField(max_length=12, choices=EstadoCalidad.choices)
    estado_nuevo = models.CharField(max_length=12, choices=EstadoCalidad.choices)
    motivo = models.CharField(max_length=255, blank=True)
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "cambio de estado de lote"
        verbose_name_plural = "historial de estados de lote"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(estado_nuevo="liberado") | models.Q(autorizado_por__isnull=False),
                name="liberacion_autorizada",
            ),
        ]


class NoConformidad(CapturaBase):
    """Desviación detectada sobre un lote, un equipo o el proceso."""

    class Decision(models.TextChoices):
        PENDIENTE = "pendiente"
        REPROCESO = "reproceso"
        DESCARTE = "descarte"
        ACEPTAR_CON_CONCESION = "aceptar_con_concesion", "Aceptar con concesión"
        DEVOLUCION_PROVEEDOR = "devolucion_proveedor", "Devolución al proveedor"

    class Estado(models.TextChoices):
        ABIERTA = "abierta"
        CERRADA = "cerrada"

    codigo = models.CharField(max_length=20, unique=True)
    origen = models.CharField(max_length=40)
    descripcion = models.TextField()
    causa = models.TextField(blank=True)
    decision = models.CharField(max_length=25, choices=Decision.choices, default=Decision.PENDIENTE)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    lote = models.ForeignKey(
        "inventario.Lote", on_delete=models.PROTECT, null=True, blank=True, related_name="no_conformidades"
    )
    equipo = models.ForeignKey(
        "equipos.Equipo", on_delete=models.PROTECT, null=True, blank=True, related_name="no_conformidades"
    )
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    cierre_verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "no conformidad"
        verbose_name_plural = "no conformidades"


class AccionCorrectiva(CapturaBase):
    """Acción para corregir la causa de una no conformidad."""

    class Estado(models.TextChoices):
        ABIERTA = "abierta"
        EN_CURSO = "en_curso"
        CERRADA = "cerrada"

    no_conformidad = models.ForeignKey(NoConformidad, on_delete=models.PROTECT, related_name="acciones")
    descripcion = models.TextField()
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha_compromiso = models.DateField()
    fecha_cierre = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    lote = models.ForeignKey("inventario.Lote", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    equipo = models.ForeignKey("equipos.Equipo", on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = "acción correctiva"
        verbose_name_plural = "acciones correctivas"


class RegistroBPM(CapturaBase):
    """Revisión de Buenas Prácticas de Manufactura no ligada a un lote (por confirmar)."""

    class Resultado(models.TextChoices):
        CUMPLE = "cumple"
        NO_CUMPLE = "no_cumple"

    tipo = models.CharField(max_length=40)
    estacion = models.ForeignKey("core.Estacion", on_delete=models.PROTECT, related_name="+")
    fecha = models.DateTimeField()
    valores = models.JSONField(default=dict)
    resultado = models.CharField(max_length=10, choices=Resultado.choices)
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "registro BPM"
        verbose_name_plural = "registros BPM"


class CertificadoManipulador(CatalogoBase):
    """Soporte de BPM de un operario (Res. 2674 de 2013, art. 11 a 13).

    Cada manipulador necesita dos soportes vigentes: el certificado médico de aptitud
    (al menos una vez al año) y la constancia de capacitación en BPM (mínimo 10 horas al año).
    Es catálogo para que la pantalla lo tenga sin conexión: al iniciar sesión avisa si vence
    pronto y, si el parámetro ``bpm_bloquea_sesion`` está activo, no deja operar con uno vencido.
    """

    class Tipo(models.TextChoices):
        MEDICO_APTITUD = "medico_aptitud", "Certificado médico de aptitud"
        CAPACITACION_BPM = "capacitacion_bpm", "Capacitación en BPM"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="certificados")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    emisor = models.CharField(max_length=120, help_text="Médico o entidad que lo expide")
    numero = models.CharField(max_length=40, blank=True)
    fecha_expedicion = models.DateField()
    fecha_vencimiento = models.DateField()
    horas = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="Solo capacitación")
    soporte_url = models.URLField(blank=True, help_text="Archivo escaneado del soporte")

    class Meta:
        verbose_name = "certificado de manipulador"
        verbose_name_plural = "certificados de manipulador"
        indexes = [models.Index(fields=["usuario", "tipo", "fecha_vencimiento"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fecha_vencimiento__gt=models.F("fecha_expedicion")),
                name="certificado_vence_despues",
            ),
            models.CheckConstraint(
                condition=~models.Q(tipo="capacitacion_bpm") | (models.Q(horas__isnull=False) & models.Q(horas__gt=0)),
                name="capacitacion_con_horas",
            ),
        ]
