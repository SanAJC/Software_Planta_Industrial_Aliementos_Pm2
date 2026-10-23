from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import CapturaBase

KG = dict(max_digits=10, decimal_places=3)
TEMP = dict(max_digits=5, decimal_places=1, null=True, blank=True)


class PedidoSede(CapturaBase):
    """Lo que una sede pide para una fecha. Lo atiende despacho con una remisión."""

    class Estado(models.TextChoices):
        BORRADOR = "borrador"
        CONFIRMADO = "confirmado"
        EN_DESPACHO = "en_despacho", "En despacho"
        ATENDIDO = "atendido"
        CANCELADO = "cancelado"

    codigo = models.CharField(max_length=20, unique=True)
    sede = models.ForeignKey("catalogos.Sede", on_delete=models.PROTECT, related_name="pedidos")
    fecha_entrega = models.DateField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "pedido de sede"
        verbose_name_plural = "pedidos de sede"


class LineaPedido(CapturaBase):
    """Producto y cantidad de un pedido."""

    pedido = models.ForeignKey(PedidoSede, on_delete=models.PROTECT, related_name="lineas")
    producto = models.ForeignKey("catalogos.Producto", on_delete=models.PROTECT, related_name="+")
    cantidad = models.DecimalField(**KG, help_text="Unidades pedidas (o kilos si el producto se vende por kg)")
    unidad = models.CharField(max_length=5, default="und")

    class Meta:
        verbose_name = "línea de pedido"
        constraints = [models.CheckConstraint(condition=Q(cantidad__gt=0), name="linea_pedido_cantidad_positiva")]


class Remision(CapturaBase):
    """Envío a una sede. Se cierra solo con la confirmación de la sede."""

    class Estado(models.TextChoices):
        BORRADOR = "borrador"
        DESPACHADA = "despachada"
        EN_TRANSITO = "en_transito", "En tránsito"
        RECIBIDA = "recibida"
        CERRADA = "cerrada"

    codigo = models.CharField(max_length=20, unique=True)
    sede = models.ForeignKey("catalogos.Sede", on_delete=models.PROTECT, related_name="remisiones")
    pedido = models.ForeignKey(
        PedidoSede, on_delete=models.PROTECT, null=True, blank=True, related_name="remisiones",
        help_text="Pedido que atiende (vacío si se despacha sin pedido)",
    )
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)
    fecha_despacho = models.DateTimeField(null=True, blank=True)
    temperatura_c = models.DecimalField(**TEMP)
    conductor = models.CharField(max_length=80, blank=True)
    placa_vehiculo = models.CharField(max_length=10, blank=True)
    observaciones = models.TextField(blank=True)
    paquetes = models.ManyToManyField("inventario.Paquete", through="RemisionPaquete", related_name="remisiones")

    class Meta:
        verbose_name = "remisión"
        verbose_name_plural = "remisiones"


class LineaRemision(CapturaBase):
    """Producto y kilos enviados en una remisión."""

    remision = models.ForeignKey(Remision, on_delete=models.PROTECT, related_name="lineas")
    producto = models.ForeignKey("catalogos.Producto", on_delete=models.PROTECT, related_name="+")
    linea_pedido = models.ForeignKey(
        LineaPedido, on_delete=models.PROTECT, null=True, blank=True, related_name="lineas_remision"
    )
    cantidad = models.DecimalField(**KG, help_text="Unidades despachadas (cazuelas, pescados...)")
    unidad = models.CharField(max_length=5, default="und")
    cantidad_kg = models.DecimalField(**KG, null=True, blank=True, help_text="Kilos reales que salieron (suma de paquetes)")
    receta = models.ForeignKey(
        "catalogos.Receta", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Versión de receta usada para explotar un kit",
    )

    class Meta:
        verbose_name = "línea de remisión"
        verbose_name_plural = "líneas de remisión"
        constraints = [models.CheckConstraint(condition=Q(cantidad__gt=0), name="linea_remision_cantidad_positiva")]


class ComponenteRemision(CapturaBase):
    """Ingrediente que sale por una línea de kit: kilos teóricos según la receta y kilos reales despachados."""

    linea_remision = models.ForeignKey(LineaRemision, on_delete=models.PROTECT, related_name="componentes")
    insumo = models.ForeignKey("catalogos.Producto", on_delete=models.PROTECT, related_name="+")
    kg_teoricos = models.DecimalField(**KG, help_text="cantidad de la línea × cantidad_por_unidad del ítem de receta")
    kg_despachados = models.DecimalField(**KG, default=0)

    class Meta:
        verbose_name = "componente de remisión"
        verbose_name_plural = "componentes de remisión"
        constraints = [
            models.UniqueConstraint(fields=["linea_remision", "insumo"], name="componente_remision_unico"),
            models.CheckConstraint(condition=Q(kg_teoricos__gt=0), name="componente_kg_teoricos_positivos"),
        ]


class RemisionPaquete(CapturaBase):
    """Paquete que sale en una remisión. Entra al escanear la canastilla que lo contiene."""

    remision = models.ForeignKey(Remision, on_delete=models.PROTECT, related_name="escaneos")
    paquete = models.ForeignKey("inventario.Paquete", on_delete=models.PROTECT, related_name="escaneos")
    linea_remision = models.ForeignKey(
        LineaRemision, on_delete=models.PROTECT, null=True, blank=True, related_name="paquetes_linea",
        help_text="Línea que atiende (producto simple o ingrediente de un kit)",
    )
    canastilla = models.ForeignKey(
        "canastillas.Canastilla", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Canastilla escaneada que traía el paquete",
    )
    escaneado_en = models.DateTimeField()

    class Meta:
        verbose_name = "paquete de remisión"
        verbose_name_plural = "paquetes de remisión"
        constraints = [models.UniqueConstraint(fields=["remision", "paquete"], name="remision_paquete_unico")]


class RecepcionSede(CapturaBase):
    """Confirmación de la sede de lo que recibió."""

    remision = models.OneToOneField(Remision, on_delete=models.PROTECT, related_name="recepcion_sede")
    recibido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha = models.DateTimeField()
    temperatura_c = models.DecimalField(**TEMP)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "recepción en sede"
        verbose_name_plural = "recepciones en sede"


class LineaRecepcionSede(CapturaBase):
    """Kilos recibidos por línea y diferencia con lo enviado."""

    recepcion_sede = models.ForeignKey(RecepcionSede, on_delete=models.PROTECT, related_name="lineas")
    linea_remision = models.ForeignKey(LineaRemision, on_delete=models.PROTECT, related_name="recepciones")
    cantidad_recibida_kg = models.DecimalField(**KG)
    diferencia_kg = models.DecimalField(**KG, default=0)
    motivo = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "línea recibida en sede"
        verbose_name_plural = "líneas recibidas en sede"
        constraints = [
            models.CheckConstraint(
                condition=Q(diferencia_kg=0) | ~Q(motivo=""), name="diferencia_sede_con_motivo"
            ),
        ]


class Devolucion(CapturaBase):
    """Producto que vuelve a la planta (de una sede o de una salida parcial)."""

    lote = models.ForeignKey("inventario.Lote", on_delete=models.PROTECT, related_name="devoluciones")
    paquete = models.ForeignKey(
        "inventario.Paquete", on_delete=models.PROTECT, null=True, blank=True, related_name="devoluciones"
    )
    remision = models.ForeignKey(Remision, on_delete=models.PROTECT, null=True, blank=True, related_name="devoluciones")
    cantidad_kg = models.DecimalField(**KG)
    motivo = models.CharField(max_length=255)
    movimiento = models.OneToOneField(
        "inventario.Movimiento", on_delete=models.PROTECT, null=True, blank=True, related_name="devolucion_registro"
    )

    class Meta:
        verbose_name = "devolución"
        verbose_name_plural = "devoluciones"
