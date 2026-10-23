"""Plantillas ZPL, impresoras, consecutivos por tablet e impresiones."""
from django.db import models
from django.db.models import F, Q

from core.models import CapturaBase, CatalogoBase, UUIDModel


class PlantillaEtiqueta(CatalogoBase):
    """Plantilla ZPL versionada de etiqueta de lote, de paquete, de equipo o de canastilla."""

    class Tipo(models.TextChoices):
        LOTE = "lote"
        PAQUETE = "paquete"
        EQUIPO = "equipo", "Equipo (QR resistente al lavado)"
        CANASTILLA = "canastilla", "Canastilla (reposición de un QR dañado, mismo código)"

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    version_plantilla = models.PositiveIntegerField(default=1)
    zpl = models.TextField()

    class Meta:
        verbose_name = "plantilla de etiqueta"
        verbose_name_plural = "plantillas de etiqueta"
        constraints = [models.UniqueConstraint(fields=["tipo", "version_plantilla"], name="plantilla_version_unica")]


class Impresora(CatalogoBase):
    """Impresora de transferencia térmica de una estación.

    Por defecto va por USB a la pantalla y se le envía ZPL con Zebra Browser Print;
    la IP solo aplica si se compra el módulo Ethernet.
    """

    class Conexion(models.TextChoices):
        USB = "usb", "USB (Zebra Browser Print)"
        RED = "red", "Red local"

    nombre = models.CharField(max_length=60)
    modelo = models.CharField(max_length=60, default="Zebra ZD421t")
    conexion = models.CharField(max_length=5, choices=Conexion.choices, default=Conexion.USB)
    ip = models.GenericIPAddressField(null=True, blank=True)
    puerto = models.PositiveIntegerField(default=9100)
    estacion = models.ForeignKey("core.Estacion", on_delete=models.PROTECT, related_name="impresoras")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(conexion="usb") | Q(ip__isnull=False), name="impresora_red_exige_ip"),
        ]

    def __str__(self):
        return self.nombre


class BloqueConsecutivo(UUIDModel):
    """Rango de códigos reservado para una tablet, para numerar sin conexión."""

    class Estado(models.TextChoices):
        ACTIVO = "activo"
        AGOTADO = "agotado"

    dispositivo = models.ForeignKey("core.Dispositivo", on_delete=models.PROTECT, related_name="bloques")
    prefijo = models.CharField(max_length=10)
    desde = models.PositiveIntegerField()
    hasta = models.PositiveIntegerField()
    ultimo_usado = models.PositiveIntegerField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "bloque de consecutivos"
        verbose_name_plural = "bloques de consecutivos"
        constraints = [
            models.CheckConstraint(condition=Q(hasta__gte=F("desde")), name="bloque_rango_valido"),
            models.UniqueConstraint(fields=["prefijo", "desde"], name="bloque_sin_solape_inicio"),
        ]


class Etiqueta(CapturaBase):
    """Cada impresión o reimpresión de una etiqueta de lote, paquete, equipo o canastilla."""

    codigo = models.CharField(max_length=40)
    plantilla = models.ForeignKey(PlantillaEtiqueta, on_delete=models.PROTECT, related_name="+")
    version_plantilla = models.PositiveIntegerField()
    impresora = models.ForeignKey(Impresora, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    lote = models.ForeignKey(
        "inventario.Lote", on_delete=models.PROTECT, null=True, blank=True, related_name="etiquetas"
    )
    paquete = models.ForeignKey(
        "inventario.Paquete", on_delete=models.PROTECT, null=True, blank=True, related_name="etiquetas"
    )
    equipo = models.ForeignKey(
        "equipos.Equipo", on_delete=models.PROTECT, null=True, blank=True, related_name="etiquetas"
    )
    canastilla = models.ForeignKey(
        "canastillas.Canastilla", on_delete=models.PROTECT, null=True, blank=True, related_name="etiquetas"
    )
    es_reimpresion = models.BooleanField(default=False)
    etiqueta_origen = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reimpresiones"
    )
    motivo_reimpresion = models.CharField(max_length=255, blank=True)
    impresa_en = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(lote__isnull=False) & Q(paquete__isnull=True) & Q(equipo__isnull=True) & Q(canastilla__isnull=True))
                | (Q(lote__isnull=True) & Q(paquete__isnull=False) & Q(equipo__isnull=True) & Q(canastilla__isnull=True))
                | (Q(lote__isnull=True) & Q(paquete__isnull=True) & Q(equipo__isnull=False) & Q(canastilla__isnull=True))
                | (Q(lote__isnull=True) & Q(paquete__isnull=True) & Q(equipo__isnull=True) & Q(canastilla__isnull=False)),
                name="etiqueta_de_un_solo_objeto",
            ),
            models.CheckConstraint(
                condition=Q(es_reimpresion=False)
                | (Q(etiqueta_origen__isnull=False) & ~Q(motivo_reimpresion="")),
                name="reimpresion_con_motivo",
            ),
        ]