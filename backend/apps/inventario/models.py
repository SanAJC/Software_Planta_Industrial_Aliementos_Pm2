"""Lotes, trazabilidad, movimientos y paquetes.

El saldo nunca se guarda: SaldoLote es una vista de base de datos que suma los
movimientos. Cada movimiento suma kilos en su ubicación destino y los resta en
su ubicación origen (entrada: solo destino; salida, consumo y merma: solo
origen; traslado: ambas).
"""
from django.db import models
from django.db.models import F, Q

from core.models import CapturaBase

KG = dict(max_digits=10, decimal_places=3)


class EstadoCalidad(models.TextChoices):
    ACEPTADO = "aceptado"
    CUARENTENA = "cuarentena", "En cuarentena"
    LIBERADO = "liberado"
    EN_REVISION = "en_revision", "En revisión"
    RECHAZADO = "rechazado"
    BLOQUEADO = "bloqueado"
    VENCIDO = "vencido"


ESTADOS_USABLES = (EstadoCalidad.ACEPTADO, EstadoCalidad.LIBERADO)


class Lote(CapturaBase):
    """Materia prima, producto en proceso o terminado."""

    class Tipo(models.TextChoices):
        MATERIA_PRIMA = "materia_prima"
        PROCESO = "proceso"
        TERMINADO = "terminado"

    class Condicion(models.TextChoices):
        CRUDO = "crudo"
        COCIDO = "cocido"
        CONGELADO = "congelado"

    class Ruta(models.TextChoices):
        COCIDO = "cocido"
        MARINADO = "marinado"
        NINGUNA = "ninguna"

    codigo = models.CharField(max_length=30, unique=True)
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    producto = models.ForeignKey("catalogos.Producto", on_delete=models.PROTECT, related_name="lotes")
    estado_calidad = models.CharField(max_length=12, choices=EstadoCalidad.choices, default=EstadoCalidad.ACEPTADO)
    condicion = models.CharField(max_length=10, choices=Condicion.choices, default=Condicion.CRUDO)
    ruta = models.CharField(max_length=15, choices=Ruta.choices, default=Ruta.NINGUNA)
    cantidad_inicial_kg = models.DecimalField(**KG)
    fecha_elaboracion = models.DateField()
    fecha_vencimiento = models.DateField()
    receta = models.ForeignKey("catalogos.Receta", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    linea_recepcion = models.OneToOneField(
        "recepcion.LineaRecepcion", on_delete=models.PROTECT, null=True, blank=True, related_name="lote"
    )

    class Meta:
        indexes = [models.Index(fields=["estado_calidad", "fecha_vencimiento"])]
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_inicial_kg__gt=0), name="lote_cantidad_positiva"),
            models.CheckConstraint(
                condition=~Q(tipo="materia_prima") | Q(linea_recepcion__isnull=False),
                name="lote_mp_viene_de_recepcion",
            ),
        ]

    def __str__(self):
        return self.codigo

    @property
    def usable(self):
        return self.estado_calidad in ESTADOS_USABLES


class LoteOrigen(CapturaBase):
    """De qué lotes, y cuántos kilos de cada uno, salió un lote nuevo."""

    lote_destino = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="origenes")
    lote_origen = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="destinos")
    cantidad_kg = models.DecimalField(**KG)

    class Meta:
        verbose_name = "origen de lote"
        verbose_name_plural = "orígenes de lote"
        constraints = [
            models.UniqueConstraint(fields=["lote_destino", "lote_origen"], name="lote_origen_unico"),
            models.CheckConstraint(condition=~Q(lote_destino=F("lote_origen")), name="lote_origen_no_circular"),
            models.CheckConstraint(condition=Q(cantidad_kg__gt=0), name="lote_origen_cantidad_positiva"),
        ]


class Movimiento(CapturaBase):
    """Entrada, salida, ajuste, devolución, traslado, merma o consumo de un lote."""

    class Tipo(models.TextChoices):
        ENTRADA = "entrada"
        SALIDA = "salida"
        CONSUMO = "consumo", "Consumo en producción"
        MERMA = "merma"
        DEVOLUCION = "devolucion", "Devolución"
        TRASLADO = "traslado"
        AJUSTE = "ajuste"

    class RefTipo(models.TextChoices):
        PESAJE = "pesaje"
        CONTROL = "control"
        REMISION = "remision"
        CONTEO = "conteo"
        MANUAL = "manual"

    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    cantidad_kg = models.DecimalField(**KG)
    ubicacion_origen = models.ForeignKey(
        "catalogos.Ubicacion", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    ubicacion_destino = models.ForeignKey(
        "catalogos.Ubicacion", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    canastilla = models.ForeignKey(
        "canastillas.Canastilla", on_delete=models.PROTECT, null=True, blank=True, related_name="movimientos_lote",
        help_text="Canastilla en la que se movió el producto, si aplica",
    )
    motivo = models.CharField(max_length=255, blank=True)
    ref_tipo = models.CharField(max_length=10, choices=RefTipo.choices, blank=True)
    ref_id = models.UUIDField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["lote", "hora_dispositivo"])]
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_kg__gt=0), name="movimiento_cantidad_positiva"),
            models.CheckConstraint(
                condition=Q(ubicacion_origen__isnull=False) | Q(ubicacion_destino__isnull=False),
                name="movimiento_tiene_ubicacion",
            ),
            models.CheckConstraint(
                condition=~Q(tipo="ajuste") | ~Q(motivo=""),
                name="movimiento_ajuste_con_motivo",
            ),
        ]


class SaldoLote(models.Model):
    """[V] Kilos disponibles por lote y ubicación. Vista creada en la migración 0002."""

    id = models.CharField(max_length=80, primary_key=True)
    lote = models.ForeignKey(Lote, on_delete=models.DO_NOTHING, related_name="saldos", db_constraint=False)
    ubicacion = models.ForeignKey(
        "catalogos.Ubicacion", on_delete=models.DO_NOTHING, related_name="+", db_constraint=False
    )
    saldo_kg = models.DecimalField(**KG)

    class Meta:
        managed = False
        db_table = "inventario_saldolote"
        verbose_name = "saldo de lote"


class Paquete(CapturaBase):
    """Paquete empacado al vacío, pesado en la báscula de empaque y etiquetado. Se escanea en despacho."""

    class OrigenPeso(models.TextChoices):
        BASCULA = "bascula"
        MANUAL = "manual"


    class Estado(models.TextChoices):
        EN_STOCK = "en_stock"
        DESPACHADO = "despachado"
        DEVUELTO = "devuelto"
        DESCARTADO = "descartado"
        VENCIDO = "vencido"

    codigo = models.CharField(max_length=40, unique=True)
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="paquetes")
    peso_kg = models.DecimalField(**KG)
    unidades = models.PositiveSmallIntegerField(default=1, help_text="Unidades de venta en el paquete (p. ej. 1 pescado entero)")
    bascula = models.ForeignKey(
        "recepcion.Bascula", on_delete=models.PROTECT, null=True, blank=True, related_name="paquetes",
        help_text="Báscula de la zona de pesaje y etiquetado (vacío si el peso se digitó)",
    )
    origen_peso = models.CharField(max_length=10, choices=OrigenPeso.choices, default=OrigenPeso.BASCULA)
    estable = models.BooleanField(default=False)
    autorizado_por = models.ForeignKey(
        "core.Usuario", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Quien autoriza digitar el peso a mano",
    )
    motivo_manual = models.CharField(max_length=255, blank=True)
    fecha_empaque = models.DateTimeField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.EN_STOCK)
    ubicacion = models.ForeignKey(
        "catalogos.Ubicacion", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(peso_kg__gt=0), name="paquete_peso_positivo"),
            models.CheckConstraint(condition=Q(unidades__gt=0), name="paquete_unidades_positivas"),
            models.CheckConstraint(
                condition=Q(origen_peso="manual") | (Q(bascula__isnull=False) & Q(estable=True)),
                name="paquete_bascula_estable",
            ),
            models.CheckConstraint(
                condition=Q(origen_peso="bascula") | (Q(autorizado_por__isnull=False) & ~Q(motivo_manual="")),
                name="paquete_peso_manual_autorizado",
            ),
        ]
