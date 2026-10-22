""" Catálogos: 
    sedes, proveedores, productos, alérgenos, recetas, 
    contenedores, ubicaciones y reglas."""
from django.db import models

from core.models import CatalogoBase

KG = dict(max_digits=10, decimal_places=3)
TEMP = dict(max_digits=5, decimal_places=1, null=True, blank=True)

class Sede(CatalogoBase):
    """Punto de venta que pide y recibe producto."""

    nombre = models.CharField(max_length=80, unique=True)
    ciudad = models.CharField(max_length=60)
    direccion = models.CharField(max_length=160, blank=True)

    def __str__(self):
        return self.nombre

class Proveedor(CatalogoBase):
    """Quien entrega materia prima en recepción."""

    nombre = models.CharField(max_length=120)
    nit = models.CharField(max_length=20, unique=True)
    contacto = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name_plural = "proveedores"

    def __str__(self):
        return self.nombre

class CategoriaSanitaria(CatalogoBase):
    """Especie o grupo sanitario del producto (pollo, res, pescado, crustáceos...).

    Define el nivel de limpieza: misma especie = N1; cambio de especie = N2.
    """

    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        verbose_name = "categoría sanitaria"
        verbose_name_plural = "categorías sanitarias"

    def __str__(self):
        return self.nombre

class Alergeno(CatalogoBase):
    """Ingrediente que causa hipersensibilidad y se declara siempre en la etiqueta (Res. 5109 de 2005).

    Lista base: cereales con gluten, crustáceos, huevo, pescado, maní, soya, leche y lácteos,
    nueces de árbol y sulfitos (10 mg/kg o más).
    """

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        verbose_name = "alérgeno"

    def __str__(self):
        return self.nombre


class Producto(CatalogoBase):
    """Materia prima, intermedio, terminado o insumo."""

    class Tipo(models.TextChoices):
        MATERIA_PRIMA = "materia_prima"
        INTERMEDIO = "intermedio"
        TERMINADO = "terminado"
        INSUMO = "insumo"
        KIT = "kit", "Receta de venta (se despacha como sus ingredientes, p. ej. cazuela)"

    class Unidad(models.TextChoices):
        KG = "kg"
        UND = "und"
        L = "l"

    class Ruta(models.TextChoices):
        COCIDO = "cocido"
        MARINADO = "marinado"
        NINGUNA = "ninguna"


    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    unidad = models.CharField(max_length=5, choices=Unidad.choices, default=Unidad.KG)
    ruta = models.CharField(max_length=15, choices=Ruta.choices, default=Ruta.NINGUNA)
    categoria_sanitaria = models.ForeignKey(
        CategoriaSanitaria, on_delete=models.PROTECT, related_name="productos"
    )
    vida_util_dias = models.PositiveIntegerField(null=True, blank=True)
    condicion_conservacion = models.CharField(max_length=120, blank=True)
    temp_conservacion_min_c = models.DecimalField(**TEMP)
    temp_conservacion_max_c = models.DecimalField(**TEMP)
    peso_porcion_kg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    alergenos = models.ManyToManyField(Alergeno, through="ProductoAlergeno", related_name="productos", blank=True)

    def __str__(self):
        return f"{self.codigo} {self.nombre}"


class ProductoAlergeno(CatalogoBase):
    """Alérgeno que contiene un producto. Sale en la etiqueta del paquete como "Contiene: ..."."""

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="alergenos_producto")
    alergeno = models.ForeignKey(Alergeno, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "alérgeno del producto"
        verbose_name_plural = "alérgenos del producto"
        constraints = [models.UniqueConstraint(fields=["producto", "alergeno"], name="producto_alergeno_unico")]


class Contenedor(CatalogoBase):
    """Tipo de canastilla, caja o bolsa con su tara medida (p. ej. canastilla 60 × 40 × 15 cm)."""

    nombre = models.CharField(max_length=60, unique=True)
    tara_kg = models.DecimalField(**KG)
    retornable = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "contenedores"
        constraints = [models.CheckConstraint(condition=models.Q(tara_kg__gte=0), name="contenedor_tara_no_negativa")]

    def __str__(self):
        return self.nombre

class Ubicacion(CatalogoBase):
    """Cuarto frío (CF1, CF2), ultracongelador, sala o vehículo donde está un lote o una canastilla."""

    class Tipo(models.TextChoices):
        CUARTO_FRIO_MATERIA_PRIMA = "cuarto_frio_materia_prima"
        CUARTO_FRIO_PRODUCTO_TERMINADO= "cuarto_frio_producto_terminado"
        ULTRACONGELADOR = "ultracongelador"
        ZONA = "zona", "Zona o sala (recepción, cocina, sala de proceso, lavado)"
        VEHICULO = "vehiculo"

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    temp_objetivo_c = models.DecimalField(**TEMP)

    class Meta:
        verbose_name = "ubicación"
        verbose_name_plural = "ubicaciones"

    def __str__(self):
        return self.codigo

class ReglaControl(CatalogoBase):
    """Combinación válida de tiempo y temperatura por producto y control.

    Un producto puede tener varias filas del mismo tipo; el control cumple si alguna se satisface.
    """

    class TipoControl(models.TextChoices):
        RECEPCION = "recepcion"
        COCCION = "coccion"
        MARINADO = "marinado"
        CONGELACION = "congelacion"
        SELLADO = "sellado"

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="reglas")
    tipo_control = models.CharField(max_length=15, choices=TipoControl.choices)
    temp_min_c = models.DecimalField(**TEMP)
    temp_max_c = models.DecimalField(**TEMP)
    tiempo_min_min = models.PositiveIntegerField(null=True, blank=True)
    tiempo_max_min = models.PositiveIntegerField(null=True, blank=True)
    exige_temp_centro = models.BooleanField(default=False)
    version_regla = models.PositiveIntegerField(default=1)
    vigente_desde = models.DateField()

    class Meta:
        verbose_name = "regla de control"
        verbose_name_plural = "reglas de control"
        indexes = [models.Index(fields=["producto", "tipo_control"])]

class Receta(CatalogoBase):
    """Ficha técnica versionada de un producto. El lote guarda la versión con que se hizo."""

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="recetas")
    version = models.PositiveIntegerField()
    rendimiento_esperado_pct = models.DecimalField(max_digits=5, decimal_places=2)
    vigente_desde = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["producto", "version"], name="receta_version_unica")]

    def __str__(self):
        return f"{self.producto} v{self.version}"

class ItemReceta(CatalogoBase):
    """Insumo y cantidad por unidad del producto (por kg si el producto se mide en kg, por unidad si es und).

    En un kit (p. ej. cazuela) da los kilos de cada ingrediente que salen por cada cazuela despachada.
    """

    receta = models.ForeignKey(Receta, on_delete=models.PROTECT, related_name="items")
    insumo = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="+")
    cantidad_por_unidad = models.DecimalField(max_digits=10, decimal_places=4)
    merma_esperada_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        verbose_name = "ítem de receta"
        constraints = [models.UniqueConstraint(fields=["receta", "insumo"], name="item_receta_unico")]


class CausaMerma(CatalogoBase):
    """Motivo de pérdida de peso o producto en una etapa."""

    nombre = models.CharField(max_length=80)
    etapa = models.CharField(max_length=20)

    class Meta:
        verbose_name = "causa de merma"
        verbose_name_plural = "causas de merma"

    def __str__(self):
        return self.nombre


class Parametro(CatalogoBase):
    """Valor configurable sin tocar código (tolerancias, tiempos)."""

    class Tipo(models.TextChoices):
        DECIMAL = "decimal"
        ENTERO = "entero"
        TEXTO = "texto"
        BOOLEANO = "booleano"

    clave = models.CharField(max_length=60, unique=True)
    valor = models.CharField(max_length=255)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.DECIMAL)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "parámetro"

    def __str__(self):
        return self.clave