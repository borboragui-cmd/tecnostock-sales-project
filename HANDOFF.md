# HANDOFF — Sales Project (TecnoStock S.A.)

> Documento de traspaso técnico. Escrito para que otra IA (o desarrollador)
> entienda el proyecto completo sin releer todo el código fuente ni consumir
> tokens en PDFs/capturas. Última actualización: 2026-07-13.

---

## 1. Qué es esto

Sistema de facturación/ERP para una empresa ficticia ("TecnoStock S.A."),
hecho en **Django 6.0.6**, orientado al mercado ecuatoriano (validación de
cédula/RUC, IVA 15%, zona horaria Guayaquil). Proyecto de
aprendizaje/portafolio, no producción real: `DEBUG=True`, `SECRET_KEY`
hardcodeada, SQLite, sin variables de entorno.

Ubicación real del código Django: **`sales_project/sales_project/`** (hay
dos carpetas anidadas con el mismo nombre). Para correr el servidor:
```bash
cd sales_project/sales_project
python manage.py runserver
```
El repo raíz (`sales_project/`) y la carpeta interna (`sales_project/sales_project/`)
tienen cada uno su propio `README.md` y `requirements.txt` — no confundirlos.

## 2. Stack

| Capa | Tecnología |
|---|---|
| Backend | Django 6.0.6 (Python 3.13) |
| DB | SQLite3 (`dbA1.sqlite3`) — NO está en git |
| Frontend | Bootstrap 5.3.0 vía CDN + Django Templates, estilo propio en `billing/base.html` |
| Auth | `django.contrib.auth` (login/signup propios) |
| PDF | ReportLab |
| Excel | openpyxl |
| Fechas | `python-dateutil` (`relativedelta` para vencimientos mensuales) |
| Debug | `django-debug-toolbar`, `django-extensions` (declarados en `INSTALLED_APPS` pero el middleware de debug_toolbar falta — warning inofensivo en cada arranque) |
| Locale | `es-ec`, `America/Guayaquil` |

## 3. Apps Django y su rol

- **`billing`** — app principal: Brand, ProductGroup, Supplier, Product,
  Customer, CustomerProfile, **Invoice** (con crédito, sección 5), InvoiceDetail.
  CRUD completo + dashboard + búsqueda global + exportación PDF/Excel de productos.
- **`purchasing`** — compras a proveedores. Reutiliza `Supplier` y `Product`
  de `billing`. **Purchase** (con crédito, sección 6) + PurchaseDetail,
  formset maestro-detalle, PDF/Excel, reporte de costo promedio.
- **`creditos_ventas`** — ventas a crédito con plan de pagos sobre `Invoice`.
  Ver sección 5 completa.
- **`creditos_compras`** — espejo de `creditos_ventas` pero sobre `Purchase`
  (compras a proveedores a crédito). Ver sección 6 completa.
- **`shared`** — utilidades cross-app: `shared/validators.py` (cédula/RUC
  ecuatoriano), `shared/decorators.py` (`audit_action`; `staff_required`
  sigue definido pero **ya no se usa en ninguna vista**, ver sección 7.3),
  `shared/mixins.py` (`StaffRequiredMixin`, `ExportMixin` genérico PDF/Excel).
- **`config`** — settings/urls/wsgi/asgi del proyecto.

Diagrama de relaciones y tablas de campos de `billing`/`purchasing`: ver
`sales_project/README.md` (detallado, pero puede estar desactualizado en el
número de migraciones — confía más en el código y en este HANDOFF).

## 4. Trampas de estructura

1. **Doble anidación** de carpetas `sales_project/` (raíz y proyecto Django).
2. **Dos `requirements.txt`** (raíz e interno), parcialmente desincronizados:
   el de la raíz trae `Flask`/`Werkzeug`/`blinker`/`click`/`Jinja2` que no
   pintan nada en un proyecto Django — parecen arrastrados de otro tutorial.
   Ambos ya incluyen `python-dateutil==2.9.0.post0`.
3. **Entorno virtual** en `sales_project/ent_sales/` — ignorado por git,
   pero el `python` que realmente se usa para correr comandos es el
   **sistema** (`C:\Users\Luiax\AppData\Local\Programs\Python\Python313\python.exe`),
   no el del venv. Confirmarlo con `python -c "import sys; print(sys.executable)"`
   antes de instalar paquetes.
4. **Formsets con prefijos no obvios** — útil para quien tenga que probar
   por HTTP en vez de por navegador:
   - `InvoiceDetailFormSet` / `PurchaseDetailFormSet`: prefijo `details-N-*`
     (`details-0-product`, `details-0-quantity`, `details-0-unit_price` /
     `details-0-unit_cost`, + `details-TOTAL_FORMS/INITIAL_FORMS/MIN_NUM_FORMS/MAX_NUM_FORMS`).
   - Filas "extra" completamente vacías de un formset SON válidas y se
     saltan solas — pero si les mandás management form con `TOTAL_FORMS`
     mayor al número de filas que realmente llenás, Django las valida como
     obligatorias igual si no vienen 100% vacías/ausentes. Más simple para
     pruebas por HTTP: mandar `TOTAL_FORMS=1` con una sola fila llena.
   - El formset de pago (`PagoCuotaForm`/`PagoCuotaCompraForm` vía
     `formset_factory`, no `inlineformset_factory`) usa prefijo `form-N-*`
     (`form-0-cuota_id`, `form-0-pagar`, `form-0-valor`, `form-0-observacion`).
     Sigue teniendo un campo `fecha` en el HTML (heredado de antes), pero
     **ya no se lee en la vista** — la fecha de pago siempre es hoy (ver 7.1).
5. **`ALLOWED_HOSTS = []`** en settings — si alguien usa `django.test.Client`
   por fuera de un `TestCase` (script suelto con `django.setup()`), hay que
   envolver con `django.test.utils.override_settings(ALLOWED_HOSTS=['testserver'])`
   o falla con `DisallowedHost`. Dentro de `TestCase`/`manage.py test` con
   `self.client` normalmente no hace falta, pero en este proyecto se agregó
   el override explícito igual en los tests que usan `Client()` manual,
   por consistencia.

## 5. Módulo de Ventas a Crédito (`creditos_ventas`)

Sobre `billing.Invoice`. Implementado y probado end-to-end.

### 5.1 Modelo de datos

**`billing.Invoice`** (ampliado):
- `numero` — `CharField` único, `FAC-000001`, autogenerado en `save()`
  (doble-save: primero para obtener `pk`, luego `save(update_fields=['numero'])`).
- `tipo_pago` (`CONTADO`/`CREDITO`, default `CONTADO`), `saldo`, `estado`
  (`PENDIENTE`/`PAGADA`, default `PENDIENTE`).

**`creditos_ventas.CuotaVenta`**: FK `factura`→`Invoice` (`PROTECT`,
`related_name='cuotas'`), `numero`, `fecha_vencimiento`, `valor`, `saldo`,
`estado`. Constraints `unique_cuota_numero_por_factura` y
`cuotaventa_saldo_valido` (`0<=saldo<=valor`, usa `condition=` no `check=`
— Django 6 renombró el kwarg). Properties: `esta_pagada`, `esta_vencida`
(`estado=='PENDIENTE' and fecha_vencimiento<hoy`), y 3 métodos nuevos (no
son `@property`, reciben `fecha=None` opcional — ver 7.2):
`interes_mora_actual()`, `descuento_pronto_pago_actual()`, `monto_para_liquidar_hoy()`.

**`creditos_ventas.PagoCuotaVenta`**: FK `cuota`→`CuotaVenta` (`PROTECT`,
`related_name='pagos'`), `fecha`, `valor` (`MinValueValidator(0.01)`),
`observacion`, y **`interes_mora`**/**`descuento_pronto_pago`** (nuevos,
default 0 — cuánto de ESE pago específico fue interés/descuento vs. capital).

Migraciones: `billing` hasta `0008` (0006 campos nuevos nullable, 0007
`RunPython` backfill de facturas viejas → `CONTADO`/`PAGADA`, 0008
`AlterField numero` a `NOT NULL`). `creditos_ventas` tiene `0001_initial`
+ `0002` (agrega `interes_mora`/`descuento_pronto_pago` a `PagoCuotaVenta`).

### 5.2 Lógica de negocio (`creditos_ventas/services.py`)

- `procesar_tipo_pago(factura, tipo_pago, num_cuotas=None)` — CONTADO →
  `saldo=0`/`PAGADA` de inmediato. CREDITO → `saldo=total`/`PENDIENTE`,
  llama a `generar_cuotas`.
- `generar_cuotas(factura, num_cuotas)` — divide `total` en partes iguales,
  **la última cuota absorbe el residuo de redondeo**. Vencimientos
  mensuales (`relativedelta(months=i)`) desde `factura.invoice_date.date()`.
  Rechaza `num_cuotas<1` y duplicados.
- **`registrar_pago(cuota_id, valor, observacion='')`** — reescrito
  completo en esta sesión, ver sección 7.1 (mora/descuento/pago mínimo).
  Ya **no recibe `fecha`** — siempre `timezone.localdate()`.
- `registrar_pagos_multiples(pagos_data)` — todo-o-nada
  (`@transaction.atomic`), itera `registrar_pago` (ya sin `fecha` en los dicts).

### 5.3 Vistas (`creditos_ventas/views.py`)

- `CuotaVentaPendientesListView` (CBV, `LoginRequiredMixin`+`ExportMixin`+`ListView`)
  con `get()` override para `?export=pdf`/`?export=excel` (necesario:
  `ExportMixin` no lo hace solo).
- `CuotaVentaListView` — auditoría completa.
- `registrar_pagos(request, factura_id)` — FBV, formset de pagos. **Solo
  `@login_required`** (el `@staff_required` se quitó, ver 7.3). Guarda
  `request.session['ultimo_lote_pagos']` y redirige a `comprobante_lote`.
- `imprimir_plan_pagos`, `comprobante_lote`, `comprobante_lote_pdf`,
  `HistorialPagosListView` — sin cambios de lógica desde que se crearon.

### 5.4 PDFs (`creditos_ventas/pdf_utils.py`)

- `generar_pdf_plan_pagos(factura)` — cabecera + tabla de cuotas, `VENCIDA`
  si `esta_vencida`.
- `generar_pdf_comprobante_lote(pagos)` — **actualizado esta sesión**:
  sello "PAGO APROBADO" + timestamp de generación arriba; por cada pago con
  `interes_mora`/`descuento_pronto_pago` ≠ 0, fila adicional (spaneada,
  fondo ámbar) `Capital: $X — Interés de mora: $Y` o `Capital: $X —
  Descuento pronto pago: $Y` (capital = `valor - interes_mora + descuento_pronto_pago`).
  El total final sigue siendo `sum(valor)`, no solo capital.

### 5.5 Dashboard e integración en `billing`

Sin cambios desde la sesión anterior: 2 tarjetas KPI (Cartera Pendiente,
Cuotas Vencidas) en su propia fila de `home.html`; `InvoiceForm` con
`tipo_pago`+`num_cuotas`; `invoice_create`/`invoice_delete` integrados
(descuento de stock intacto, `ProtectedError` capturado); bloque condicional
crédito/contado en `invoice_detail.html`.

### 5.6 URLs (`/creditos/`)
```
/creditos/cuotas/                          → cuota_list
/creditos/cuotas/pendientes/               → cuotas_pendientes (export PDF/Excel)
/creditos/facturas/<id>/pagar/             → registrar_pagos (solo login)
/creditos/facturas/<id>/plan-pagos/pdf/    → plan_pagos_pdf
/creditos/pagos/historial/                 → historial_pagos
/creditos/pagos/comprobante/               → comprobante_lote
/creditos/pagos/comprobante/pdf/           → comprobante_lote_pdf
```

## 6. Módulo de Compras a Crédito (`creditos_compras`) — espejo de `creditos_ventas`

Construido esta sesión, sobre `purchasing.Purchase`. Mismo patrón 1:1 que
`creditos_ventas`, con las adaptaciones de nombres (`compra` en vez de
`factura`, `Supplier` en vez de `Customer`) y las diferencias reales que
ya existían entre `billing`/`purchasing` (ver 6.4).

### 6.1 Modelo de datos

**`purchasing.Purchase`** (ampliado): `numero` (`ORD-000001`, mismo patrón
doble-save que `Invoice.numero` — **coexiste con `document_number`**, que
es el número que pone el proveedor y NO se toca), `tipo_pago`, `saldo`,
`estado`. Migraciones `purchasing` hasta `0005` (0002 campos nuevos, 0003
backfill `ORD-`/`CONTADO`/`PAGADA` en compras viejas, 0004 `AlterField NOT
NULL`, 0005 es un efecto colateral — ver 6.5).

**`creditos_compras.CuotaCompra`**: FK `compra`→`Purchase` (`PROTECT`,
`related_name='cuotas'`), mismos campos/constraints/properties que
`CuotaVenta` (`uq_cuotacompra_compra_numero`, `ck_cuotacompra_saldo_rango`
con `condition=`, `esta_pagada`, `esta_vencida`,
`interes_mora_actual`/`descuento_pronto_pago_actual`/`monto_para_liquidar_hoy`).

**`creditos_compras.PagoCuotaCompra`**: igual que `PagoCuotaVenta`
(`interes_mora`, `descuento_pronto_pago` incluidos).

Migraciones: `creditos_compras` tiene `0001_initial` + `0002` (agrega
`interes_mora`/`descuento_pronto_pago`).

### 6.2 Lógica de negocio y vistas

`creditos_compras/services.py` y `creditos_compras/views.py` son un calco
funcional de los de `creditos_ventas` (mismas firmas, mismo comportamiento,
`compra`/`Purchase` en vez de `factura`/`Invoice`). Una diferencia de
diseño **deliberada y ya existente antes de esta sesión**: el criterio para
marcar el padre como `PAGADA` es distinto entre los dos módulos:
- `creditos_ventas`: `factura.estado='PAGADA'` cuando `factura.saldo<=0`.
- `creditos_compras`: `compra.estado='PAGADA'` cuando **todas** sus cuotas
  están en `PAGADA` (`not compra.cuotas.exclude(estado='PAGADA').exists()`).

Ambos criterios deberían coincidir en la práctica, pero no son el mismo
código — si alguien "unifica" esto sin querer, tenerlo en cuenta.

`registrar_pagos` en `creditos_compras/views.py` también quedó **solo con
`@login_required`** (staff_required removido, igual que en ventas).

Clave de sesión para el comprobante de lote: `ultimo_lote_pagos_compras`
(deliberadamente distinta de `ultimo_lote_pagos` de ventas, para que pagar
una venta y una compra en la misma sesión de navegador no se pisen).

### 6.3 PDFs (`creditos_compras/pdf_utils.py`)

Mismo sello "PAGO APROBADO" + desglose capital/interés/descuento que
`creditos_ventas/pdf_utils.py`. `generar_pdf_plan_pagos(compra)` usa
`compra.numero` (`ORD-...`) como identificador principal — `document_number`
solo aparece como dato informativo secundario ("N° Factura Proveedor").

### 6.4 Diferencias reales entre `purchasing`/`billing` que hay que respetar

- `Purchase` no tenía (antes de esta sesión) ningún campo `numero` interno,
  solo `document_number` (dato externo, del proveedor). Se agregó `numero`
  siguiendo el mismo patrón que `Invoice`, sin tocar `document_number`.
- `purchase_create` **incrementa** stock al crear y `purchase_delete` lo
  **revierte** al eliminar — lo opuesto a facturación (`invoice_create`
  decrementa). El módulo de crédito de compras no toca esta lógica de
  stock para nada, solo el plan de pagos. Confirmado con test manual: el
  stock solo se movió por la creación/eliminación de compras, nunca por
  nada del módulo de crédito.
- `purchase_delete` ahora captura `ProtectedError` (antes no lo hacía, a
  diferencia de `invoice_delete` que sí) — necesario porque `CuotaCompra`
  usa `PROTECT` hacia `Purchase`.
- `PurchaseForm` agregó `tipo_pago`+`num_cuotas`, conservando la validación
  de duplicado `supplier+document_number` que ya existía (no se pisó).

### 6.5 Efecto colateral de migraciones (ya resuelto, documentado para no repetirlo)

`purchasing` tenía una migración pendiente de antes (`Meta.options` de
`PurchaseDetail` — `ordering`/`verbose_name` nunca migrados desde el
`0001_initial`). Al generar `creditos_compras.0001_initial` (FK `compra`→
`Purchase`), Django tomó el estado más reciente de `purchasing` para
construir la dependencia, y de rebote generó y aplicó
`purchasing/0005_alter_purchasedetail_options.py`. Es inofensivo (solo
metadata de ORM/admin, sin cambio de schema) y quedó aplicado a propósito
(confirmado con el usuario) — si ves `0005` en `purchasing/migrations/`,
no es un error.

### 6.6 URLs (`/creditos-compras/`)
```
/creditos-compras/cuotas/                       → cuota_list
/creditos-compras/cuotas/pendientes/            → cuotas_pendientes (export PDF/Excel)
/creditos-compras/compras/<id>/pagar/           → registrar_pagos (solo login)
/creditos-compras/compras/<id>/plan-pagos/pdf/  → plan_pagos_pdf
/creditos-compras/pagos/historial/              → historial_pagos
/creditos-compras/pagos/comprobante/            → comprobante_lote
/creditos-compras/pagos/comprobante/pdf/        → comprobante_lote_pdf
```

### 6.7 Dashboard

2 tarjetas nuevas en su propia fila de `home.html` (además de las 2 de
ventas, que están en OTRA fila propia — son 3 filas de KPIs en total ahora):
**Cuentas por Pagar** (`Purchase.filter(tipo_pago='CREDITO', estado='PENDIENTE').aggregate(Sum('saldo'))`)
y **Cuotas de Compra Vencidas** (conteo `CuotaCompra` con
`fecha_vencimiento__lt=hoy`, link a `creditos_compras:cuotas_pendientes`).

## 7. Cambios de lógica de negocio de esta sesión (mora, descuento, pago mínimo, permisos)

Esto reemplazó el `registrar_pago` original (que solo validaba
`0 < valor <= saldo` y una fecha explícita) por un sistema de liquidación
con interés por mora / descuento por pronto pago. **Aplica idéntico en
ambos módulos** (`creditos_ventas` y `creditos_compras`).

### 7.1 `registrar_pago(cuota_id, valor, observacion='')` — nueva firma

- **La fecha de pago ya NO es parámetro** — siempre `timezone.localdate()`
  (hoy), sin excepción.
- Rechaza si la factura/compra ya está `PAGADA`.
- Calcula `monto_liquidacion = cuota.monto_para_liquidar_hoy()`,
  `interes = cuota.interes_mora_actual()`, `descuento = cuota.descuento_pronto_pago_actual()`.
- **Dos modalidades**:
  - **Liquidación total** (`valor == monto_liquidacion` exacto): cancela la
    cuota, `saldo=0`, `estado=PAGADA`, guarda `interes_mora`/`descuento_pronto_pago`
    reales en el `PagoCuota*` creado.
  - **Pago parcial** (cualquier otro valor válido): 1:1 sobre `saldo`, SIN
    interés ni descuento (quedan en 0 en el `PagoCuota*`). Exige un mínimo:
    `min(settings.PAGO_MINIMO_CUOTA, cuota.saldo)` — o sea, si lo que falta
    es menor al mínimo nominal, se acepta pagar exactamente ese resto.
- **Bug real que se encontró y corrigió sobre el pseudocódigo original
  dado por el usuario**: el pago parcial no estaba topado contra
  `cuota.saldo`, solo contra `monto_liquidacion`. Con mora,
  `monto_liquidacion > saldo` (por el interés), así que un pago "parcial"
  de `saldo + $1` pasaba el chequeo superior pero dejaba `cuota.saldo`
  **negativo**, violando la constraint `saldo_rango`. Se agregó un tope
  explícito: un pago parcial no puede superar `cuota.saldo`; superarlo
  solo es válido como liquidación total exacta.
- El saldo de la factura/compra padre se decrementa por el **capital**
  (`cuota.saldo` antes de liquidar en el caso total, o `valor` en el caso
  parcial) — NO por `valor` bruto en el caso de liquidación total, porque
  `valor` ahí incluye interés (que no es capital) o excluye descuento (que
  sí reduce capital igual). Esta es una decisión de diseño tomada sin
  especificación explícita del usuario — si el saldo agregado de la
  factura/compra no cuadra como se espera, revisar esto primero.

### 7.2 Fórmulas de mora/descuento (`CuotaVenta`/`CuotaCompra`, métodos no-property)

Ambos usan `settings.TASA_MORA_DESCUENTO_MENSUAL` (ver 7.4), prorrateando
linealmente por días con mes=30 días:
- `interes_mora_actual(fecha=None)`: `saldo * TASA * (dias_mora/30)`,
  `dias_mora = fecha - fecha_vencimiento`, solo si vencida. `quantize(0.01, ROUND_HALF_UP)`.
- `descuento_pronto_pago_actual(fecha=None)`: `valor * TASA * (dias_anticipo/30)`,
  `dias_anticipo = fecha_vencimiento - fecha`, solo si `fecha < fecha_vencimiento`.
  Ojo: la base es `valor` (nominal), no `saldo`.
- `monto_para_liquidar_hoy(fecha=None)`: `saldo + interes - descuento`, nunca negativo.

**Consecuencia importante y no del todo intuitiva**: si una cuota aún NO
vence, `monto_para_liquidar_hoy() < saldo` automáticamente (por el
descuento). Esto significa que **ya no hay forma de pagar el saldo íntegro
sin tomar el descuento** cuando la cuota no está vencida — cualquier
intento de pagar más que `monto_liquidacion` se rechaza, en vez de
simplemente ignorar el descuento ofrecido. Es el comportamiento tal como
lo pidió el usuario (`if valor > monto_liquidacion: raise ValidationError`),
pero se le avisó explícitamente que esto "fuerza" el descuento — no se
cambió sin confirmación.

Estos métodos generalizan `esta_vencida` (que siempre usa `timezone.now()`
internamente) para aceptar una `fecha` hipotética explícita — con
`fecha=None` el resultado es idéntico a usar `esta_vencida`.

### 7.3 Permisos — `staff_required` removido de `registrar_pagos`

En ambos módulos, `registrar_pagos` pasó de `@login_required
+ @staff_required(...)` a **solo `@login_required`**. Razón (dada por el
usuario): pagar no destruye información y ya está blindado por las
validaciones de `services.py`. El decorador `staff_required` en
`shared/decorators.py` **sigue existiendo** (no se borró, solo dejó de
usarse) — los imports huérfanos se limpiaron de ambos `views.py`. Los 4
`DeleteView` con `StaffRequiredMixin` (`ProductGroupDeleteView`,
`SupplierDeleteView`, `ProductDeleteView`, `CustomerDeleteView`) **no se
tocaron**, siguen siendo staff-only. `invoice_delete`/`purchase_delete`
nunca requirieron staff (eso ya era así desde antes).

### 7.4 Constantes de negocio (`config/settings.py`)

```python
from decimal import Decimal
TASA_MORA_DESCUENTO_MENSUAL = Decimal('0.02')  # 2% mensual, mora y descuento
PAGO_MINIMO_CUOTA = Decimal('5.00')  # mínimo fijo por pago parcial, en dólares
```
Única fuente de verdad — `services.py` de ambos módulos las importa vía
`from django.conf import settings`, nunca hardcodeadas. El proyecto no
tiene settings separado por módulos (todo vive en el único `config/settings.py`).

## 8. Tests

`billing/tests.py` y `purchasing/tests.py` siguen vacíos (boilerplate,
hallazgo de auditoría de sesiones anteriores, no tocado).

`creditos_ventas/tests.py` y `creditos_compras/tests.py` — **19 tests cada
uno, 38 en total, todos verdes**:
```
python manage.py test creditos_ventas creditos_compras
Ran 38 tests in ~1.2s — OK
```
Cobertura por módulo (idéntica estructura en ambos): `procesar_tipo_pago`
CONTADO, `generar_cuotas` (residuo exacto, rechazo de `num_cuotas` inválido,
rechazo de duplicado), `registrar_pago` (valor no positivo, valor >
liquidación, factura/compra ya pagada, pago mínimo, tope de parcial en
mora, fecha siempre hoy, última cuota marca padre PAGADA), fórmulas exactas
de interés (15 días de mora) y descuento (20 días de anticipo),
pago parcial de cuota vencida sin interés, pago parcial igual al resto
bajo el mínimo, `registrar_pagos_multiples` todo-o-nada, `ProtectedError`
en cascada (cuota con pagos, factura/compra con cuotas), y usuario
no-staff pagando exitosamente vía `Client()` + `override_settings(ALLOWED_HOSTS=['testserver'])`.

**Dos bugs reales encontrados escribiendo estos tests** (documentados
también en el código):
1. El fixture helper (`_crear_factura`/`_crear_compra`) no inicializaba
   `saldo`/`estado` como lo haría `procesar_tipo_pago` real (quedaban en
   su default `0`/`PENDIENTE`), lo que hacía que el primer pago parcial
   dejara el saldo del padre negativo y lo marcara `PAGADA` prematuramente.
   Solo se manifestó como fallo visible en `creditos_ventas` (criterio
   `saldo<=0`); en `creditos_compras` no se notó porque su criterio es
   "todas las cuotas PAGADA" (ver 6.2). Corregido en ambos helpers.
2. Varios tests asumían que pagar `cuota.saldo` siempre liquida — falso
   si la cuota no está vencida (ver 7.2, el descuento reduce
   `monto_para_liquidar_hoy()` por debajo de `saldo`). Se cambió a usar
   `cuota.monto_para_liquidar_hoy()` donde corresponde liquidación total.

## 9. Estado de git

Todo lo de las secciones 5, 6, 7 y 8 fue commiteado y pusheado a
`github.com/borboragui-cmd/tecnostock-sales-project` (rama `main`) en esta
sesión. `dbA1.sqlite3`/`dbA1.sqlite3.backup` siguen excluidos vía
`.gitignore` (ver historial de sesiones anteriores — el repo fue
reescrito una vez para sacar la DB del historial).

## 10. Hallazgos de auditoría aún vigentes (de sesiones anteriores, sin resolver)

- `debug_toolbar` en `INSTALLED_APPS` sin su middleware → warning cosmético
  en cada arranque.
- `billing/tests.py` y `purchasing/tests.py` vacíos.
- Dos `requirements.txt` desincronizados (sección 4.2).
- `ProductListView.get_queryset()` usa `except:` desnudo en varios filtros numéricos.
- La asimetría de criterio "padre PAGADA" entre `creditos_ventas`
  (`saldo<=0`) y `creditos_compras` (todas las cuotas `PAGADA`) — sección 6.2.
  Ambos deberían coincidir en la práctica pero no está garantizado por
  construcción; si algún día divergen, sería difícil de detectar.
- El campo `fecha` sigue presente en `PagoCuotaForm`/`PagoCuotaCompraForm`
  y en los templates de `registrar_pagos.html`, pero ya no se lee en la
  vista (la fecha siempre es hoy). Es UI inerte, no se tocó porque no fue
  pedido explícitamente — candidato a limpieza si se retoma el frontend.

## 11. Preferencias de quien pidió este trabajo

- Prefiere trabajar en español, pide "detallitas" — respuestas completas, no resumidas de más.
- Cuando da instrucciones muy detalladas y numeradas (incluso pseudocódigo
  completo), las sigue al pie de la letra pero **espera que se detecten y
  corrijan bugs/omisiones en esas instrucciones** en vez de copiarlas
  ciegamente. Pasó varias veces: descuento de stock faltante en un
  `invoice_create` reescrito, `get()` faltante para que `ExportMixin`
  funcionara, `CheckConstraint(check=...)` en vez de `condition=`, y el
  tope de pago parcial faltante contra `cuota.saldo` en mora.
- Antes de operaciones destructivas de git (reescribir historial, force
  push) pide confirmación explícita paso a paso.
- Para features grandes espera que se pruebe de verdad (no solo
  `manage.py check`) antes de dar por cerrado — `django.test.Client` +
  `override_settings(ALLOWED_HOSTS=['testserver'])`, o mejor aún,
  `TestCase` con tests permanentes en vez de scripts desechables, es el
  patrón ya establecido en este proyecto.
- Cuando algo queda ambiguo en una especificación (ej. fórmula exacta de
  mora, o qué monto decrementar del padre), prefiere que se tome una
  decisión razonada Y se le avise explícitamente, en vez de preguntar por
  cada detalle menor — pero si la decisión es grande/reversible con
  costo (ej. qué migrar, qué commitear), prefiere que se le pregunte antes.
