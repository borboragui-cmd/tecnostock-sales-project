# TecnoStock S.A — Reutilización de modelos entre `purchasing` y `billing`

## Contexto

La app `billing` define el catálogo central de la plataforma: `Supplier` (proveedores)
y `Product` (productos con stock). La app `purchasing` **no duplica esas tablas**;
las importa directamente para registrar órdenes de compra.

```python
# purchasing/models.py
from billing.models import Supplier, Product
```

---

## Modelo `Supplier` — de `billing` a `purchasing`

`Supplier` almacena razón social, contacto, email, teléfono y dirección.
`purchasing` lo consume mediante una clave foránea en `Purchase`:

```python
class Purchase(models.Model):
    supplier  = models.ForeignKey(Supplier, on_delete=models.PROTECT,
                                  related_name='purchases')
    date      = models.DateTimeField(auto_now_add=True)
    total     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
```

`PROTECT` garantiza que no se pueda eliminar un proveedor que tenga órdenes de
compra registradas, preservando la trazabilidad histórica.

---

## Modelo `Product` — de `billing` a `purchasing`

`Product` centraliza nombre, precio de venta y **stock**. `PurchaseDetail` lo
referencia para registrar qué artículos entran y a qué costo unitario:

```python
class PurchaseDetail(models.Model):
    purchase  = models.ForeignKey(Purchase, on_delete=models.CASCADE,
                                  related_name='details')
    product   = models.ForeignKey(Product, on_delete=models.PROTECT,
                                  related_name='purchase_details')
    quantity  = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
```

Al confirmar una compra el stock se actualiza en el mismo registro de `billing`:

```python
Product.objects.filter(pk=detail.product.pk).update(
    stock=F('stock') + detail.quantity
)
```

Ventas (`InvoiceDetail`) y compras modifican así el mismo campo `Product.stock`.

---

## Resumen de beneficios

| Aspecto | Resultado |
|---|---|
| Sin duplicación | Un único catálogo de proveedores y productos para toda la app |
| Integridad referencial | `PROTECT` impide borrar registros con movimientos asociados |
| Stock centralizado | Compras y ventas actúan sobre el mismo campo `billing.Product.stock` |
| Migraciones limpias | `purchasing` no agrega tablas propias para entidades ya existentes |
