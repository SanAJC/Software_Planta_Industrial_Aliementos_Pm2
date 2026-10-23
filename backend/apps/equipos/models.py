"""Equipos, matriz de cambio de producto y limpieza.

Dos niveles de limpieza:
- N1, superficial: retiro de residuos entre usos con la misma especie.
- N2, profunda: cuando cambia la especie que pasa por el equipo.
El nivel exigido sale de MatrizCambio (categoría del último UsoEquipo frente a
la del producto nuevo); si la pareja no está, misma especie = N1 y distinta = N2.

Equipo.estado es una copia que la tablet descarga; la fuente de verdad son
UsoEquipo, RegistroLimpieza y CambioEstadoEquipo.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import CapturaBase, CatalogoBase


class Nivel(models.TextChoices):
    N1 = "N1", "N1 · superficial (retiro de residuos)"
    N2 = "N2", "N2 · profunda (cambio de especie)"


def nivel_exigido(categoria_anterior_id, categoria_nueva_id):
    """Nivel por defecto cuando la matriz no define la pareja."""
    if categoria_anterior_id is None or categoria_anterior_id == categoria_nueva_id:
        return Nivel.N1
    return Nivel.N2


class EstadoEquipo(models.TextChoices):
    LIBERADO = "liberado"
    EN_USO = "en_uso"
    USADO = "usado"
    EN_LIMPIEZA = "en_limpieza"
    POR_VERIFICAR = "por_verificar"
    FUERA_SERVICIO = "fuera_servicio", "Fuera de servicio"


class Equipo(CatalogoBase):
    """Marmita, horno, empacadora, mesa o tombler. Lleva una etiqueta QR fija con su código."""

    codigo = models.CharField(
        max_length=20, unique=True,
        help_text="Identificador corto, p. ej. MARM-1. Es el contenido del QR pegado en el equipo",
    )
    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=40)
    estacion = models.ForeignKey("core.Estacion", on_delete=models.PROTECT, related_name="equipos")
    estado = models.CharField(max_length=15, choices=EstadoEquipo.choices, default=EstadoEquipo.LIBERADO)
    ultima_categoria = models.ForeignKey(
        "catalogos.CategoriaSanitaria", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    ultimo_uso_fin = models.DateTimeField(null=True, blank=True)
    tiempo_max_uso_min = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.codigo} {self.nombre}"


class MatrizCambio(CatalogoBase):
    """Nivel de limpieza exigido al pasar de una categoría a otra."""

    categoria_desde = models.ForeignKey("catalogos.CategoriaSanitaria", on_delete=models.PROTECT, related_name="+")
    categoria_hacia = models.ForeignKey("catalogos.CategoriaSanitaria", on_delete=models.PROTECT, related_name="+")
    nivel = models.CharField(max_length=2, choices=Nivel.choices)
    version_matriz = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "matriz de cambio"
        verbose_name_plural = "matriz de cambio"
        constraints = [
            models.UniqueConstraint(
                fields=["categoria_desde", "categoria_hacia", "version_matriz"], name="matriz_cambio_unica"
            ),
        ]


class ProcedimientoLimpieza(CatalogoBase):
    """Procedimiento (POE) de un nivel de limpieza, versionado."""

    nivel = models.CharField(max_length=2, choices=Nivel.choices)
    nombre = models.CharField(max_length=80)
    version_procedimiento = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "procedimiento de limpieza"
        verbose_name_plural = "procedimientos de limpieza"
        constraints = [
            models.UniqueConstraint(fields=["nivel", "version_procedimiento"], name="procedimiento_version_unica"),
        ]


class PasoLimpieza(CatalogoBase):
    """Un paso del procedimiento, con su medición y rango si aplica."""

    class TipoResultado(models.TextChoices):
        NINGUNO = "ninguno"
        NUMERICO = "numerico"
        APROBADO_RECHAZADO = "aprobado_rechazado"

    procedimiento = models.ForeignKey(ProcedimientoLimpieza, on_delete=models.PROTECT, related_name="pasos")
    orden = models.PositiveSmallIntegerField()
    descripcion = models.CharField(max_length=255)
    requiere_medicion = models.BooleanField(default=False)
    medicion_nombre = models.CharField(max_length=60, blank=True)
    unidad = models.CharField(max_length=15, blank=True)
    rango_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    rango_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    tipo_resultado = models.CharField(max_length=20, choices=TipoResultado.choices, default=TipoResultado.NINGUNO)

    class Meta:
        verbose_name = "paso de limpieza"
        verbose_name_plural = "pasos de limpieza"
        ordering = ["procedimiento", "orden"]
        constraints = [models.UniqueConstraint(fields=["procedimiento", "orden"], name="paso_orden_unico")]


class RegistroLimpieza(CapturaBase):
    """Una limpieza: se abre escaneando el QR del equipo desde el celular de la encargada.

    El ejecutor es quien limpió; el verificador es la encargada (rol limpieza o ingeniera) que marca si
    cumple y libera el equipo. Puede ser la misma persona.
    """

    class Estado(models.TextChoices):
        EN_LIMPIEZA = "en_limpieza"
        POR_VERIFICAR = "por_verificar"
        APROBADA = "aprobada"
        RECHAZADA = "rechazada"

    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, related_name="limpiezas")
    procedimiento = models.ForeignKey(ProcedimientoLimpieza, on_delete=models.PROTECT, related_name="+")
    nivel = models.CharField(max_length=2, choices=Nivel.choices)
    inicio = models.DateTimeField()
    fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.EN_LIMPIEZA)
    ejecutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    verificador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    motivo_rechazo = models.CharField(max_length=255, blank=True)
    liberado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "registro de limpieza"
        verbose_name_plural = "registros de limpieza"
        constraints = [
            models.CheckConstraint(
                condition=~Q(estado="rechazada") | ~Q(motivo_rechazo=""),
                name="limpieza_rechazo_con_motivo",
            ),
        ]


class RegistroLimpiezaPaso(CapturaBase):
    """Lo que se hizo y midió en cada paso de una limpieza."""

    registro = models.ForeignKey(RegistroLimpieza, on_delete=models.PROTECT, related_name="pasos")
    paso = models.ForeignKey(PasoLimpieza, on_delete=models.PROTECT, related_name="+")
    cumplido = models.BooleanField(default=False)
    valor_medido = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    resultado_prueba = models.CharField(max_length=20, blank=True, help_text="ATP o alérgeno, si aplica")
    fuera_de_rango = models.BooleanField(default=False)

    class Meta:
        verbose_name = "paso ejecutado"
        verbose_name_plural = "pasos ejecutados"
        constraints = [models.UniqueConstraint(fields=["registro", "paso"], name="registro_paso_unico")]


class UsoEquipo(CapturaBase):
    """Uso de un equipo con una categoría; guarda qué limpieza lo liberó."""

    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, related_name="usos")
    categoria = models.ForeignKey("catalogos.CategoriaSanitaria", on_delete=models.PROTECT, related_name="+")
    lote = models.ForeignKey(
        "inventario.Lote", on_delete=models.PROTECT, null=True, blank=True, related_name="usos_equipo"
    )
    limpieza = models.ForeignKey(
        RegistroLimpieza, on_delete=models.PROTECT, null=True, blank=True, related_name="usos",
        help_text="Limpieza (N1 o N2) que liberó el equipo para este uso",
    )
    inicio = models.DateTimeField()
    fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "uso de equipo"
        verbose_name_plural = "usos de equipo"
        indexes = [models.Index(fields=["equipo", "inicio"])]


class CambioEstadoEquipo(CapturaBase):
    """Historial de estados del equipo, incluido fuera de servicio."""

    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, related_name="cambios_estado")
    estado_anterior = models.CharField(max_length=15, choices=EstadoEquipo.choices)
    estado_nuevo = models.CharField(max_length=15, choices=EstadoEquipo.choices)
    motivo = models.CharField(max_length=255, blank=True)
    ref_tipo = models.CharField(max_length=10, blank=True, help_text="uso | limpieza | manual")
    ref_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = "cambio de estado de equipo"
        verbose_name_plural = "cambios de estado de equipo"

