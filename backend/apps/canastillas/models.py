from django.conf import settings
from django.db import models
from django.db.models import F, Q

from core.models import CapturaBase, CatalogoBase

KG = dict(max_digits=10, decimal_places=3)


class EstadoCanastilla(models.TextChoices):
    DISPONIBLE = "disponible", "Disponible (limpia y vacía)"
    OCUPADA = "ocupada", "Ocupada en planta"
    DESPACHADA = "despachada", "Despachada (en ruta)"
    EN_SEDE = "en_sede", "En sede"
    EN_RETORNO = "en_retorno", "En retorno"
    POR_LAVAR = "por_lavar", "Por lavar"
    RETENIDA = "retenida", "Retenida por daño"
    BAJA = "baja", "De baja"


class Canastilla(CatalogoBase):
    """Activo retornable con número único y QR durable."""

    class Uso(models.TextChoices):
        CRUDO = "crudo", "Crudos (azul)"
        LISTO = "listo", "Listos para consumo (blanco)"

    codigo = models.CharField(max_length=20, unique=True, help_text="PM-C-0001; es el contenido del QR")
    tipo = models.ForeignKey(
        "catalogos.Contenedor", on_delete=models.PROTECT, related_name="canastillas",
        help_text="Referencia y tara (p. ej. 60 × 40 × 15 cm para porciones, 60 × 40 × 25 cm para despacho)",
    )
    uso = models.CharField(max_length=10, choices=Uso.choices)
    estado = models.CharField(max_length=12, choices=EstadoCanastilla.choices, default=EstadoCanastilla.DISPONIBLE)
    ubicacion = models.ForeignKey(
        "catalogos.Ubicacion", on_delete=models.PROTECT, null=True, blank=True, related_name="canastillas"
    )
    sede = models.ForeignKey(
        "catalogos.Sede", on_delete=models.PROTECT, null=True, blank=True, related_name="canastillas"
    )
    fecha_alta = models.DateField()
    ultimo_movimiento_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~Q(estado="en_sede") | Q(sede__isnull=False), name="canastilla_en_sede_con_sede"),
        ]

    def __str__(self):
        return self.codigo

    @property
    def libre(self):
        return not self.contenidos.filter(retirado_en__isnull=True, anulado=False).exists()


class ContenidoCanastilla(CapturaBase):
    """Lo que tiene una canastilla: un lote (materia prima, cocido, en proceso) o paquetes al vacío."""

    canastilla = models.ForeignKey(Canastilla, on_delete=models.PROTECT, related_name="contenidos")
    lote = models.ForeignKey("inventario.Lote", on_delete=models.PROTECT, related_name="contenidos_canastilla")
    paquete = models.ForeignKey(
        "inventario.Paquete", on_delete=models.PROTECT, null=True, blank=True, related_name="contenidos_canastilla"
    )
    cantidad_kg = models.DecimalField(
        **KG, null=True, blank=True,
        help_text="Kilos del lote en la canastilla. Vacío si entró en un arrume pesado junto",
    )
    pesaje_recepcion = models.ForeignKey(
        "recepcion.Pesaje", on_delete=models.PROTECT, null=True, blank=True, related_name="canastillas",
        help_text="Pesada de recepción (arrume) en la que entró esta canastilla",
    )
    cargado_en = models.DateTimeField()
    retirado_en = models.DateTimeField(null=True, blank=True)
    retirado_por = models.ForeignKey(
        "MovimientoCanastilla", on_delete=models.PROTECT, null=True, blank=True, related_name="contenidos_retirados"
    )

    class Meta:
        verbose_name = "contenido de canastilla"
        verbose_name_plural = "contenidos de canastilla"
        indexes = [models.Index(fields=["canastilla", "retirado_en"])]
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_kg__isnull=True) | Q(cantidad_kg__gt=0), name="contenido_kg_positivo"),
            models.UniqueConstraint(
                fields=["paquete"], condition=Q(retirado_en__isnull=True, anulado=False, paquete__isnull=False),
                name="paquete_en_una_sola_canastilla",
            ),
        ]


class PesajeCanastilla(CapturaBase):
    """Pesada individual de una canastilla en la báscula de recepción (pantalla 1) al salir o volver al CF1.

    - ``salida``: sale la canastilla completa hacia cocción o marinado.
    - ``parcial``: se saca una parte a otra canastilla con QR; se pesa solo la que sale y la de
      origen vuelve al CF1 sin pesarse.
    - ``reingreso``: producto que vuelve al CF1 (p. ej. lo que cocina no usó).
    El neto (bruto menos la tara de la canastilla) es el ``Movimiento`` del lote.
    """

    class Tipo(models.TextChoices):
        SALIDA = "salida", "Salida completa del CF1"
        PARCIAL = "parcial", "Salida parcial del CF1"
        REINGRESO = "reingreso", "Reingreso al CF1"

    class Destino(models.TextChoices):
        COCCION = "coccion", "Cocción"
        MARINADO = "marinado"

    class Origen(models.TextChoices):
        BASCULA = "bascula"
        MANUAL = "manual"

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    lote = models.ForeignKey("inventario.Lote", on_delete=models.PROTECT, related_name="pesajes_canastilla")
    canastilla = models.ForeignKey(
        Canastilla, on_delete=models.PROTECT, related_name="pesajes", help_text="Canastilla que se pone en la báscula"
    )
    canastilla_origen = models.ForeignKey(
        Canastilla, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="En una salida parcial, la canastilla de la que se sacó el producto",
    )
    destino = models.CharField(max_length=10, choices=Destino.choices, blank=True)
    bascula = models.ForeignKey(
        "recepcion.Bascula", on_delete=models.PROTECT, null=True, blank=True, related_name="pesajes_canastilla"
    )
    bruto_kg = models.DecimalField(**KG)
    tara_kg = models.DecimalField(**KG, help_text="Tara de la canastilla, del catálogo de contenedores")
    neto_kg = models.DecimalField(**KG)
    origen = models.CharField(max_length=10, choices=Origen.choices, default=Origen.BASCULA)
    estable = models.BooleanField(default=False)
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    motivo_manual = models.CharField(max_length=255, blank=True)
    movimiento = models.OneToOneField(
        "inventario.Movimiento", on_delete=models.PROTECT, null=True, blank=True, related_name="pesaje_canastilla",
        help_text="Salida o devolución del lote con este neto",
    )

    class Meta:
        verbose_name = "pesaje de canastilla"
        verbose_name_plural = "pesajes de canastilla"
        constraints = [
            models.CheckConstraint(condition=Q(neto_kg__gt=0), name="pesaje_canastilla_neto_positivo"),
            models.CheckConstraint(condition=Q(neto_kg=F("bruto_kg") - F("tara_kg")), name="pesaje_canastilla_neto_cuadra"),
            models.CheckConstraint(
                condition=Q(origen="manual") | (Q(estable=True) & Q(bascula__isnull=False)),
                name="pesaje_canastilla_bascula_estable",
            ),
            models.CheckConstraint(
                condition=Q(origen="bascula") | (Q(autorizado_por__isnull=False) & ~Q(motivo_manual="")),
                name="pesaje_canastilla_manual_autorizado",
            ),
            models.CheckConstraint(
                condition=Q(tipo="reingreso", destino="") | (~Q(tipo="reingreso") & ~Q(destino="")),
                name="pesaje_canastilla_destino_segun_tipo",
            ),
            models.CheckConstraint(
                condition=(Q(tipo="parcial") & Q(canastilla_origen__isnull=False) & ~Q(canastilla_origen=F("canastilla")))
                | (~Q(tipo="parcial") & Q(canastilla_origen__isnull=True)),
                name="pesaje_canastilla_parcial_con_origen",
            ),
        ]


def saldo_al_agotar(lote, ubicacion):
    """Saldo que queda de un lote en una ubicación cuando ya no tiene canastillas allí.

    Devuelve None mientras quede alguna canastilla activa del lote en esa ubicación o si el
    saldo es cero. Positivo = merma de almacenamiento; negativo = salió más de lo que entró
    (ajuste con aviso a la ingeniera).
    """
    from inventario.models import SaldoLote

    quedan = ContenidoCanastilla.objects.filter(
        lote=lote, retirado_en__isnull=True, anulado=False, canastilla__ubicacion=ubicacion
    ).exists()
    if quedan:
        return None
    fila = SaldoLote.objects.filter(lote=lote, ubicacion=ubicacion).first()
    if fila is None or fila.saldo_kg == 0:
        return None
    return fila.saldo_kg


class MovimientoCanastilla(CapturaBase):
    """Cambio de estado, ubicación o custodia de una canastilla, registrado al escanear su QR."""

    class Tipo(models.TextChoices):
        ALTA = "alta"
        CARGA = "carga", "Carga de producto"
        DESCARGA = "descarga", "Descarga o consumo del contenido"
        TRASLADO = "traslado", "Traslado interno (CF1, ultracongelador, sala, CF2)"
        SALIDA = "salida", "Salida en una remisión"
        RECEPCION_SEDE = "recepcion_sede", "Recepción en sede"
        DEVOLUCION = "devolucion", "Entregada al conductor para retorno"
        LLEGADA_PLANTA = "llegada_planta", "Llegada a planta (zona sucia)"
        LAVADO = "lavado"
        LIBERACION = "liberacion", "Inspeccionada y disponible"
        RETENCION = "retencion", "Retenida por daño"
        BAJA = "baja"

    class Condicion(models.TextChoices):
        INTEGRA = "integra", "Íntegra"
        TAPA_DANADA = "tapa_danada", "Tapa dañada"
        ROTA = "rota"
        SUCIA = "sucia"
        QR_DANADO = "qr_danado", "QR dañado"

    canastilla = models.ForeignKey(Canastilla, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    estado_anterior = models.CharField(max_length=12, choices=EstadoCanastilla.choices)
    estado_nuevo = models.CharField(max_length=12, choices=EstadoCanastilla.choices)
    ubicacion_destino = models.ForeignKey(
        "catalogos.Ubicacion", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    sede = models.ForeignKey("catalogos.Sede", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    remision = models.ForeignKey(
        "despacho.Remision", on_delete=models.PROTECT, null=True, blank=True, related_name="movimientos_canastilla"
    )
    entrega = models.CharField(max_length=80, blank=True, help_text="Quien entrega (p. ej. el conductor)")
    recibe = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Usuario que recibe (receptor de sede o planta)",
    )
    condicion = models.CharField(max_length=12, choices=Condicion.choices, default=Condicion.INTEGRA)
    retorno_previsto = models.DateTimeField(null=True, blank=True)
    unidades_esperadas = models.PositiveIntegerField(
        null=True, blank=True, help_text="Unidades que el sistema sabe que hay en la canastilla"
    )
    unidades_contadas = models.PositiveIntegerField(
        null=True, blank=True, help_text="Unidades que confirma el operario al despachar o recibir"
    )
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "movimiento de canastilla"
        verbose_name_plural = "movimientos de canastilla"
        indexes = [models.Index(fields=["canastilla", "hora_dispositivo"])]
        constraints = [
            models.CheckConstraint(condition=~Q(tipo="salida") | Q(remision__isnull=False), name="salida_canastilla_con_remision"),
            models.CheckConstraint(
                condition=~Q(tipo__in=["recepcion_sede", "devolucion"]) | Q(sede__isnull=False),
                name="canastilla_sede_en_recepcion_y_devolucion",
            ),
            models.CheckConstraint(
                condition=~Q(tipo__in=["retencion", "baja"]) | ~Q(observacion=""),
                name="retencion_y_baja_con_motivo",
            ),
            models.CheckConstraint(
                condition=Q(unidades_contadas__isnull=True) | Q(unidades_esperadas__isnull=True)
                | Q(unidades_contadas=F("unidades_esperadas")) | ~Q(observacion=""),
                name="conteo_distinto_con_motivo",
            ),
            models.CheckConstraint(
                condition=~Q(tipo="salida") | Q(unidades_contadas__isnull=False),
                name="salida_canastilla_con_conteo",
            ),
        ]
