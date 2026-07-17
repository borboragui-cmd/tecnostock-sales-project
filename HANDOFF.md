# HANDOFF — Sales Project (TecnoStock S.A.)

> Documento de traspaso técnico. Escrito para que otra IA (o desarrollador)
> entienda el proyecto completo sin releer todo el código fuente ni consumir
> tokens en PDFs/capturas. Última actualización: 2026-07-16.

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
| Auth | `django.contrib.auth` (login vía `django.contrib.auth.urls`, registro propio en `security` — ver sección 12) |
| Roles/permisos | `django.contrib.auth` nativo (`User`/`Group`/`Permission`) vía app `security` — ver sección 12 |
| PDF | ReportLab |
| Excel | openpyxl |
| Fechas | `python-dateutil` (`relativedelta` para vencimientos mensuales) |
| Debug | `django-debug-toolbar`, `django-extensions` (declarados en `INSTALLED_APPS` pero el middleware de debug_toolbar falta — warning inofensivo en cada arranque) |
| Locale | `es-ec`, `America/Guayaquil` |

## 3. Apps Django y su rol

- **`billing`** — app principal: Brand, ProductGroup, Supplier, Product,
  Customer, CustomerProfile, **Invoice** (con crédito, sección 5), InvoiceDetail.
  CRUD completo + dashboard + búsqueda global + exportación PDF/Excel de productos.
  Protegido por rol (`Vendedor`/`Analista de Compras`/`Administrador`) desde
  esta sesión — ver sección 12.5.
- **`purchasing`** — compras a proveedores. Reutiliza `Supplier` y `Product`
  de `billing`. **Purchase** (con crédito, sección 6) + PurchaseDetail,
  formset maestro-detalle, PDF/Excel, reporte de costo promedio. 100% FBV
  (no tiene ninguna CBV), protegido por rol con `@group_required` — sección 12.5.
- **`creditos_ventas`** — ventas a crédito con plan de pagos sobre `Invoice`.
  Ver sección 5 completa.
- **`creditos_compras`** — espejo de `creditos_ventas` pero sobre `Purchase`
  (compras a proveedores a crédito). Ver sección 6 completa.
- **`security`** — **app nueva de esta sesión**: gestión de usuarios, roles
  (`Group`) y permisos usando los modelos nativos de Django. Reemplaza
  por completo el registro que antes vivía en `billing`. Ver sección 12
  completa — es la sección más grande de este documento.
- **`shared`** — utilidades cross-app: `shared/validators.py` (cédula/RUC
  ecuatoriano), `shared/decorators.py` (`audit_action`, `group_required`
  **nuevo**, `staff_required` sigue definido pero **ya no se usa en ninguna
  vista**, ver sección 7.3), `shared/mixins.py` (`StaffRequiredMixin`,
  `ExportMixin` genérico PDF/Excel, `GroupRequiredMixin` **nuevo**, ver 12.2).
  **No es una app Django registrada** (no tiene `apps.py`, no está en
  `INSTALLED_APPS`), solo un paquete Python de utilidades.
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
   antes de instalar paquetes. (También existe un `sales_project/venv/`
   adicional — no confundir los dos, ninguno es el que se usa realmente.)
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
   por consistencia. Patrón usado también extensivamente en `security` — ver 12.7.
6. **Windows/NTFS case-insensitive por defecto** — durante esta sesión hubo
   confusión real entre `billing/Templates/` (mayúscula, `startapp` original)
   y `billing/templates/` (minúscula). En este sistema son la MISMA carpeta
   física (confirmado con `os.stat` — mismo tamaño/mtime en ambas rutas), pero
   herramientas distintas (`ls` de Git Bash vs. API de Windows vía Python) a
   veces resuelven/reportan el path con casing distinto. Si algo "no se
   actualiza" al editar una plantilla, **antes de sospechar de caché de
   Django**, confirmar con `python -c "..."` + `get_template().origin.name`
   cuál es la ruta real que está leyendo el loader.

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
- **`registrar_pago(cuota_id, valor, observacion='')`** — sistema completo
  de liquidación con mora/descuento/pago mínimo, ver sección 7.1. **No
  recibe `fecha`** — siempre `timezone.localdate()`. **NO se le agregó
  `GroupRequiredMixin`/`@group_required` en la sesión de RBAC (sección 12)
  — sigue siendo la única vista de crédito accesible con cualquier rol,
  decisión explícita del usuario, ver 12.5.**
- `registrar_pagos_multiples(pagos_data)` — todo-o-nada
  (`@transaction.atomic`), itera `registrar_pago` (ya sin `fecha` en los dicts).

### 5.3 Vistas (`creditos_ventas/views.py`)

- `CuotaVentaPendientesListView` (CBV, `LoginRequiredMixin`+`GroupRequiredMixin`+
  `ExportMixin`+`ListView`) con `get()` override para `?export=pdf`/`?export=excel`.
  `group_required=['Vendedor','Administrador']` desde sección 12.5.
- `CuotaVentaListView` — auditoría completa. **Hasta la sesión de RBAC (12.5)
  no tenía NI `LoginRequiredMixin`** — cualquiera, sin loguearse, podía verla.
  Ahora protegida igual que arriba.
- `registrar_pagos(request, factura_id)` — FBV, formset de pagos. **Solo
  `@login_required`**, sin `@group_required` (decisión explícita, ver 7.3 y 12.5).
  Guarda `request.session['ultimo_lote_pagos']` y redirige a `comprobante_lote`.
- `imprimir_plan_pagos`, `comprobante_lote`, `comprobante_lote_pdf`,
  `HistorialPagosListView` — mismo `group_required=['Vendedor','Administrador']`
  agregado en 12.5 (`HistorialPagosListView` tampoco tenía `LoginRequiredMixin`
  antes de esta sesión).

### 5.4 PDFs (`creditos_ventas/pdf_utils.py`)

- `generar_pdf_plan_pagos(factura)` — cabecera + tabla de cuotas, `VENCIDA`
  si `esta_vencida`.
- `generar_pdf_comprobante_lote(pagos)` — sello "PAGO APROBADO" + timestamp
  de generación arriba; por cada pago con `interes_mora`/`descuento_pronto_pago`
  ≠ 0, fila adicional (spaneada, fondo ámbar) `Capital: $X — Interés de mora: $Y`
  o `Capital: $X — Descuento pronto pago: $Y` (capital =
  `valor - interes_mora + descuento_pronto_pago`). El total final sigue
  siendo `sum(valor)`, no solo capital.

### 5.5 Dashboard e integración en `billing`

2 tarjetas KPI (Cartera Pendiente, Cuotas Vencidas) en su propia fila de
`home.html`; `InvoiceForm` con `tipo_pago`+`num_cuotas`; `invoice_create`/
`invoice_delete` integrados (descuento de stock intacto, `ProtectedError`
capturado); bloque condicional crédito/contado en `invoice_detail.html`.
**`home.html` fue reescrito en la sesión de RBAC (12.6) para extender
`billing/base.html` — los KPIs y su lógica de contexto NO cambiaron, solo
la estructura del template.**

### 5.6 URLs (`/creditos/`)
```
/creditos/cuotas/                          → cuota_list
/creditos/cuotas/pendientes/               → cuotas_pendientes (export PDF/Excel)
/creditos/facturas/<id>/pagar/             → registrar_pagos (solo login, sin rol)
/creditos/facturas/<id>/plan-pagos/pdf/    → plan_pagos_pdf
/creditos/pagos/historial/                 → historial_pagos
/creditos/pagos/comprobante/               → comprobante_lote
/creditos/pagos/comprobante/pdf/           → comprobante_lote_pdf
```

## 6. Módulo de Compras a Crédito (`creditos_compras`) — espejo de `creditos_ventas`

Sobre `purchasing.Purchase`. Mismo patrón 1:1 que `creditos_ventas`, con las
adaptaciones de nombres (`compra` en vez de `factura`, `Supplier` en vez de
`Customer`) y las diferencias reales que ya existían entre `billing`/`purchasing`
(ver 6.4). **Todo lo de la sección 5 sobre RBAC aplica igual acá, pero con
`group_required=['Analista de Compras','Administrador']` en vez de
`['Vendedor','Administrador']`** — ver 12.5.

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
diseño **deliberada**: el criterio para marcar el padre como `PAGADA` es
distinto entre los dos módulos:
- `creditos_ventas`: `factura.estado='PAGADA'` cuando `factura.saldo<=0`.
- `creditos_compras`: `compra.estado='PAGADA'` cuando **todas** sus cuotas
  están en `PAGADA` (`not compra.cuotas.exclude(estado='PAGADA').exists()`).

Ambos criterios deberían coincidir en la práctica, pero no son el mismo
código — si alguien "unifica" esto sin querer, tenerlo en cuenta.

`registrar_pagos` en `creditos_compras/views.py` también quedó **solo con
`@login_required`**, sin `@group_required` (mismo criterio que `creditos_ventas`).

Clave de sesión para el comprobante de lote: `ultimo_lote_pagos_compras`
(deliberadamente distinta de `ultimo_lote_pagos` de ventas, para que pagar
una venta y una compra en la misma sesión de navegador no se pisen).

### 6.3 PDFs (`creditos_compras/pdf_utils.py`)

Mismo sello "PAGO APROBADO" + desglose capital/interés/descuento que
`creditos_ventas/pdf_utils.py`. `generar_pdf_plan_pagos(compra)` usa
`compra.numero` (`ORD-...`) como identificador principal — `document_number`
solo aparece como dato informativo secundario ("N° Factura Proveedor").

### 6.4 Diferencias reales entre `purchasing`/`billing` que hay que respetar

- `Purchase` no tenía originalmente ningún campo `numero` interno, solo
  `document_number` (dato externo, del proveedor). Se agregó `numero`
  siguiendo el mismo patrón que `Invoice`, sin tocar `document_number`.
- `purchase_create` **incrementa** stock al crear y `purchase_delete` lo
  **revierte** al eliminar — lo opuesto a facturación (`invoice_create`
  decrementa). El módulo de crédito de compras no toca esta lógica de
  stock para nada, solo el plan de pagos.
- `purchase_delete` captura `ProtectedError` (a diferencia de `invoice_delete`
  que también lo hace) — necesario porque `CuotaCompra` usa `PROTECT` hacia
  `Purchase`.
- `PurchaseForm` agregó `tipo_pago`+`num_cuotas`, conservando la validación
  de duplicado `supplier+document_number` que ya existía.
- **`purchasing/views.py` es 100% FBV** — no hay ninguna CBV en todo el
  archivo (a diferencia de `billing`, que mezcla FBV y CBV). Importante para
  la sección 12.5: todas sus 8 vistas se protegieron con el decorador
  `@group_required`, no con `GroupRequiredMixin`.

### 6.5 Efecto colateral de migraciones (ya resuelto, documentado para no repetirlo)

`purchasing` tenía una migración pendiente de antes (`Meta.options` de
`PurchaseDetail` — `ordering`/`verbose_name` nunca migrados desde el
`0001_initial`). Al generar `creditos_compras.0001_initial` (FK `compra`→
`Purchase`), Django tomó el estado más reciente de `purchasing` para
construir la dependencia, y de rebote generó y aplicó
`purchasing/0005_alter_purchasedetail_options.py`. Es inofensivo (solo
metadata de ORM/admin, sin cambio de schema) y quedó aplicado a propósito
— si ves `0005` en `purchasing/migrations/`, no es un error.

### 6.6 URLs (`/creditos-compras/`)
```
/creditos-compras/cuotas/                       → cuota_list
/creditos-compras/cuotas/pendientes/            → cuotas_pendientes (export PDF/Excel)
/creditos-compras/compras/<id>/pagar/           → registrar_pagos (solo login, sin rol)
/creditos-compras/compras/<id>/plan-pagos/pdf/  → plan_pagos_pdf
/creditos-compras/pagos/historial/              → historial_pagos
/creditos-compras/pagos/comprobante/            → comprobante_lote
/creditos-compras/pagos/comprobante/pdf/        → comprobante_lote_pdf
```

### 6.7 Dashboard

2 tarjetas en `home.html` (además de las 2 de ventas): **Cuentas por Pagar**
(`Purchase.filter(tipo_pago='CREDITO', estado='PENDIENTE').aggregate(Sum('saldo'))`)
y **Cuotas de Compra Vencidas** (conteo `CuotaCompra` con
`fecha_vencimiento__lt=hoy`, link a `creditos_compras:cuotas_pendientes`).

## 7. Cambios de lógica de negocio de la sesión de crédito (mora, descuento, pago mínimo, permisos)

Reemplazó el `registrar_pago` original (que solo validaba `0 < valor <= saldo`
y una fecha explícita) por un sistema de liquidación con interés por mora /
descuento por pronto pago. **Aplica idéntico en ambos módulos**
(`creditos_ventas` y `creditos_compras`).

### 7.1 `registrar_pago(cuota_id, valor, observacion='')` — firma actual

- **La fecha de pago NO es parámetro** — siempre `timezone.localdate()` (hoy).
- Rechaza si la factura/compra ya está `PAGADA`.
- Calcula `monto_liquidacion = cuota.monto_para_liquidar_hoy()`,
  `interes = cuota.interes_mora_actual()`, `descuento = cuota.descuento_pronto_pago_actual()`.
- **Dos modalidades**:
  - **Liquidación total** (`valor == monto_liquidacion` exacto): cancela la
    cuota, `saldo=0`, `estado=PAGADA`, guarda `interes_mora`/`descuento_pronto_pago`
    reales en el `PagoCuota*` creado.
  - **Pago parcial** (cualquier otro valor válido): 1:1 sobre `saldo`, SIN
    interés ni descuento. Exige un mínimo: `min(settings.PAGO_MINIMO_CUOTA, cuota.saldo)`.
- **Bug real corregido**: el pago parcial no estaba topado contra
  `cuota.saldo`, solo contra `monto_liquidacion`. Con mora,
  `monto_liquidacion > saldo` (por el interés), así que un pago "parcial"
  de `saldo + $1` pasaba el chequeo superior pero dejaba `cuota.saldo`
  **negativo**, violando la constraint `saldo_rango`. Se agregó un tope
  explícito: un pago parcial no puede superar `cuota.saldo`.
- El saldo de la factura/compra padre se decrementa por el **capital**
  (`cuota.saldo` antes de liquidar en el caso total, o `valor` en el caso
  parcial) — NO por `valor` bruto en liquidación total.

### 7.2 Fórmulas de mora/descuento (`CuotaVenta`/`CuotaCompra`, métodos no-property)

Ambos usan `settings.TASA_MORA_DESCUENTO_MENSUAL` (ver 7.4), prorrateando
linealmente por días con mes=30 días:
- `interes_mora_actual(fecha=None)`: `saldo * TASA * (dias_mora/30)`,
  solo si vencida. `quantize(0.01, ROUND_HALF_UP)`.
- `descuento_pronto_pago_actual(fecha=None)`: `valor * TASA * (dias_anticipo/30)`,
  solo si `fecha < fecha_vencimiento`. La base es `valor` (nominal), no `saldo`.
- `monto_para_liquidar_hoy(fecha=None)`: `saldo + interes - descuento`, nunca negativo.

**Consecuencia**: si una cuota aún NO vence, `monto_para_liquidar_hoy() < saldo`
automáticamente (por el descuento) — no hay forma de pagar el saldo íntegro
sin tomar el descuento cuando la cuota no está vencida. Comportamiento
pedido explícitamente por el usuario.

### 7.3 Permisos de `registrar_pagos` — `staff_required` removido

En ambos módulos, `registrar_pagos` pasó de `@login_required
+ @staff_required(...)` a **solo `@login_required`**. Razón: pagar no
destruye información y ya está blindado por las validaciones de
`services.py`. El decorador `staff_required` **sigue existiendo** en
`shared/decorators.py` pero no se usa en ninguna vista. **En la sesión de
RBAC (12.5) se decidió explícitamente NO agregarle `@group_required`
tampoco** — sigue siendo accesible por cualquier rol logueado, a propósito.

### 7.4 Constantes de negocio (`config/settings.py`)

```python
from decimal import Decimal
TASA_MORA_DESCUENTO_MENSUAL = Decimal('0.02')  # 2% mensual, mora y descuento
PAGO_MINIMO_CUOTA = Decimal('5.00')  # mínimo fijo por pago parcial, en dólares
```
Única fuente de verdad — `services.py` de ambos módulos las importa vía
`from django.conf import settings`.

## 8. Tests

`billing/tests.py` y `purchasing/tests.py` siguen vacíos (boilerplate, hallazgo
de auditoría de sesiones anteriores, no tocado).

`creditos_ventas/tests.py` y `creditos_compras/tests.py` — **19 tests cada
uno, 38 en total**. `security/tests.py` — **12 tests nuevos** (sección 12.7).
**Total: 50 tests, todos verdes**:
```
python manage.py test billing purchasing creditos_ventas creditos_compras security
Ran 50 tests in ~12s — OK
```

Cobertura de `creditos_ventas`/`creditos_compras` (idéntica estructura en
ambos): `procesar_tipo_pago` CONTADO, `generar_cuotas` (residuo exacto,
rechazo de `num_cuotas` inválido, rechazo de duplicado), `registrar_pago`
(valor no positivo, valor > liquidación, factura/compra ya pagada, pago
mínimo, tope de parcial en mora, fecha siempre hoy, última cuota marca
padre PAGADA), fórmulas exactas de interés (15 días de mora) y descuento
(20 días de anticipo), pago parcial de cuota vencida sin interés, pago
parcial igual al resto bajo el mínimo, `registrar_pagos_multiples`
todo-o-nada, `ProtectedError` en cascada, y usuario no-staff pagando
exitosamente vía `Client()` + `override_settings(ALLOWED_HOSTS=['testserver'])`.

Cobertura de `security` (sección 12.7): setup_roles crea los 3 roles y es
idempotente, registro con/sin rol, `GroupRequiredMixin` bloquea/permite
según rol (incluido bypass de superusuario sin `Group`), filtro `has_group`
probado como función pura (rol propio, rol ajeno, superuser, `AnonymousUser`).

**Dos bugs reales encontrados escribiendo los tests de crédito** (documentados
también en el código):
1. El fixture helper (`_crear_factura`/`_crear_compra`) no inicializaba
   `saldo`/`estado` como lo haría `procesar_tipo_pago` real, lo que hacía
   que el primer pago parcial dejara el saldo del padre negativo. Corregido
   en ambos helpers.
2. Varios tests asumían que pagar `cuota.saldo` siempre liquida — falso si
   la cuota no está vencida (el descuento reduce `monto_para_liquidar_hoy()`
   por debajo de `saldo`). Corregido.

## 9. Estado de git

Lo de las secciones 5, 6, 7 y 8 (módulos de crédito) fue commiteado y
pusheado a `github.com/borboragui-cmd/tecnostock-sales-project` (rama
`main`) en una sesión anterior — commit `2557d8a`.

**Todo lo de la sección 12 (app `security` completa + RBAC + fixes de
seguridad) está hecho en el working tree pero AÚN NO COMMITEADO** al
momento de escribir este HANDOFF. `git status` muestra modificados:
`billing/{Templates/billing/base.html,Templates/billing/home.html,forms.py,urls.py,views.py}`,
`config/{settings.py,urls.py}`, `creditos_compras/views.py`,
`creditos_ventas/views.py`, `purchasing/views.py`, `shared/{decorators.py,mixins.py}`,
`templates/registration/login.html`; eliminado: `templates/registration/signup.html`;
sin trackear: `security/` (app completa nueva) y `DIAGNOSTICO_SEGURIDAD.md`
(en la raíz del repo, no dentro de `sales_project/`).

`dbA1.sqlite3`/`dbA1.sqlite3.backup` siguen excluidos vía `.gitignore` (el
repo fue reescrito una vez para sacar la DB del historial, en sesión anterior).

**Nadie ha commiteado la sección 12 todavía** — si retomás esto, confirmar
con el usuario antes de commitear (siguiendo su preferencia de sección 13,
pedir confirmación explícita para operaciones de git).

## 10. Hallazgos de auditoría aún vigentes (sin resolver)

- `debug_toolbar` en `INSTALLED_APPS` sin su middleware → warning cosmético
  en cada arranque.
- `billing/tests.py` y `purchasing/tests.py` vacíos.
- Dos `requirements.txt` desincronizados (sección 4.2).
- `ProductListView.get_queryset()` usa `except:` desnudo en varios filtros numéricos.
- La asimetría de criterio "padre PAGADA" entre `creditos_ventas`
  (`saldo<=0`) y `creditos_compras` (todas las cuotas `PAGADA`) — sección 6.2.
- El campo `fecha` sigue presente en `PagoCuotaForm`/`PagoCuotaCompraForm`
  y en los templates de `registrar_pagos.html`, pero ya no se lee en la





  vista. UI inerte, candidato a limpieza si se retoma el frontend.
- `registrar_pagos` (ambos módulos de crédito) sigue accesible por
  cualquier rol logueado — decisión explícita, no un descuido, ver 7.3/12.5.
- **`PermissionCreateView`/`UpdateView`/`DeleteView` no existen a propósito**
  (sección 12.4) — el Administrador solo puede LEER permisos desde la UI,
  no crear permisos custom. Si se necesita en el futuro, hay que crear esas
  3 vistas + urls + templates desde cero.
- El sidebar de `base.html` no tiene enlaces a `creditos_ventas`/
  `creditos_compras` (cuotas pendientes, historial de pagos) — esos módulos
  solo se acceden desde las tarjetas del dashboard, no desde el menú lateral.
  No se tocó en esta sesión, sigue igual que antes.

## 11. Preferencias de quien pidió este trabajo

- Prefiere trabajar en español, pide "detallitas" — respuestas completas, no
  resumidas de más.
- Cuando da instrucciones muy detalladas y numeradas (incluso pseudocódigo
  completo), las sigue al pie de la letra pero **espera que se detecten y
  corrijan bugs/omisiones en esas instrucciones** en vez de copiarlas
  ciegamente. Pasó varias veces: descuento de stock faltante en un
  `invoice_create` reescrito, `get()` faltante para `ExportMixin`,
  `CheckConstraint(check=...)` en vez de `condition=`, tope de pago parcial
  faltante contra `cuota.saldo` en mora, y en esta sesión: el mapeo de
  permisos del PDF de la guía solo cubría `billing`/`purchasing` y hubo que
  extenderlo a `creditos_ventas`/`creditos_compras` (sección 12.3).
- **Pide "PASO 0 — auditoría" antes de cualquier cambio grande**: mostrar el
  contenido COMPLETO de los archivos relevantes primero, identificar qué
  existe hoy, y a veces literalmente frenar ahí y esperar confirmación
  ("dale") antes de aplicar nada. No asumir nombres de clases/mixins/URLs
  sin haberlos visto en el código real.
- Antes de operaciones destructivas de git (reescribir historial, force
  push) pide confirmación explícita paso a paso. **Esto también aplicó a
  cambios de código sensibles**: pidió verificar en runtime (no solo
  razonar sobre el código) si los huecos de auto-eliminación/auto-degradación
  de Administrador eran explotables (sección 12.8) antes de decidir el fix.
- Para features grandes espera que se pruebe de verdad (no solo
  `manage.py check`) antes de dar por cerrado — `django.test.Client` +
  `override_settings(ALLOWED_HOSTS=['testserver'])`, o mejor aún,
  `TestCase` con tests permanentes, es el patrón ya establecido.
- Pide explícitamente la salida CRUDA de comandos (no resúmenes) cuando
  quiere verificar algo — ver sección 12.7, pidió el output literal de
  `manage.py test` dos veces.
- Cuando algo queda ambiguo en una especificación, prefiere que se tome una
  decisión razonada Y se le avise explícitamente — pero si la decisión es
  grande/reversible con costo (ej. qué migrar, qué commitear, qué grupo de
  permisos asignar a qué vista), prefiere que se le pregunte antes.

---

## 12. App de Seguridad (`security`) — Roles y Permisos (RBAC) — sesión actual

Construida desde cero en esta sesión. Usa **exclusivamente** los modelos
nativos de `django.contrib.auth` (`User`, `Group`, `Permission`) — no hay
ningún modelo propio en `security/models.py` (queda como lo generó
`startapp`, sin clases), por lo tanto **no hay migraciones de `security`**.

### 12.1 Los 3 roles

| Rol (`Group.name`) | Qué ve/hace |
|---|---|
| `Administrador` | Todo el sistema + menú Seguridad (Usuarios/Roles/Permisos). Todos los permisos (`Permission.objects.all()`). |
| `Vendedor` | Clientes, Facturas + módulo `creditos_ventas` (cuotas, historial, planes de pago — NO `registrar_pagos`, que es libre para cualquier rol). |
| `Analista de Compras` | Marcas, Grupos, Proveedores, Productos, Compras + módulo `creditos_compras`. |

El **superusuario** (`is_superuser=True`, vía `createsuperuser` o el admin
de Django) **siempre pasa todos los chequeos de rol, incluso sin tener
ningún `Group` asignado** — verificado explícitamente con tests y en runtime
(secciones 12.2 y 12.7).

### 12.2 `GroupRequiredMixin` (`shared/mixins.py`) y `group_required` (`shared/decorators.py`)

Par de utilidades hermanas — mixin para CBV, decorador para FBV, mismo
comportamiento exacto:

```python
class GroupRequiredMixin:
    group_required = []
    group_redirect_url = '/'
    group_error_message = 'No tienes permiso para acceder a esta opción.'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        if request.user.groups.filter(name__in=self.group_required).exists():
            return super().dispatch(request, *args, **kwargs)
        messages.error(request, self.group_error_message)
        return redirect(self.group_redirect_url)
```

`group_required(group_names, redirect_url='/', error_message=...)` en
`shared/decorators.py` es el equivalente para FBV (mismo bypass de
superusuario), usado como `@group_required([...])`, **siempre por debajo**
de `@login_required` en el stack de decoradores (Python ejecuta el decorador
de más arriba primero, así que `@login_required` arriba garantiza que el
login se valida antes que el rol).

**Orden de mixins en las CBV con `StaffRequiredMixin`** (4 vistas de
`billing`: `ProductGroupDeleteView`, `SupplierDeleteView`, `ProductDeleteView`,
`CustomerDeleteView`):
```python
class ProductDeleteView(LoginRequiredMixin, GroupRequiredMixin, StaffRequiredMixin, DeleteView):
```
`GroupRequiredMixin` va **después** de `LoginRequiredMixin` y **antes** de
`StaffRequiredMixin`: login → rol → staff → vista. Se confirmó que
`ExportMixin` (usado en `ProductListView`, `CuotaVentaPendientesListView`,
`CuotaCompraPendientesListView`) **no define `dispatch()`** — no participa
en la cadena de resolución, así que su posición relativa no afecta el
comportamiento, pero se mantuvo consistente: `LoginRequiredMixin,
GroupRequiredMixin, ExportMixin, ListView`.

### 12.3 Filtro de template `has_group` (`security/templatetags/security_tags.py`)

```python
@register.filter(name='has_group')
def has_group(user, group_name):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=group_name).exists()
```
Uso en templates: `{% load security_tags %}` + `{% if user|has_group:'Vendedor' %}`.
Cargado como primera línea de `billing/base.html` (antes de `<!DOCTYPE html>`).
Probado directamente como función pura en los tests (sección 12.7), sin
necesidad de renderizar HTML.

### 12.4 `security/forms.py`, `views.py`, `urls.py`

**Forms** (`security/forms.py`):
- `UserRegisterForm(UserCreationForm)` — registro público. Reutiliza
  `validate_only_letters` de `shared/validators.py` (mismo criterio que el
  `SignUpForm` que reemplazó, ver 12.6). Campo `role` (`ModelChoiceField`)
  **excluye explícitamente `'Administrador'`** desde el fix de la sección
  12.8 — `Group.objects.exclude(name='Administrador')`, NO `.all()`.
- `UserUpdateForm(ModelForm)` — usado solo por `UserUpdateView`, protegida
  por `AdminOnlyMixin`. Su campo `groups` SÍ usa `Group.objects.all()` sin
  filtrar (correcto: solo un Administrador ya autenticado llega ahí).
- `GroupForm(ModelForm)` — crear/editar rol con checkboxes de permisos.
- **No existe `PermissionForm`** — decisión explícita, ver 12.1 y sección 10.

**Views** (`security/views.py`) — `AdminOnlyMixin(LoginRequiredMixin,
GroupRequiredMixin)` con `group_required=['Administrador']` como base de
todo el CRUD de administración:
- `RegisterView` (pública, sin `AdminOnlyMixin`) — reemplaza `billing.SignUpView`.
- `UserListView`, `UserUpdateView` (con protección anti-auto-degradación,
  12.8), `UserDeleteView` (con protección anti-auto-eliminación, 12.8).
- `GroupListView`, `GroupCreateView`, `GroupUpdateView`, `GroupDeleteView`
  (con protección contra borrar el Group `'Administrador'`, 12.8).
- `PermissionListView` — **solo lectura**, sin Create/Update/Delete.

**URLs** (`/security/`, `app_name='security'`):
```
/security/register/                → security:register (pública)
/security/users/                   → security:user_list
/security/users/<pk>/edit/         → security:user_update
/security/users/<pk>/delete/       → security:user_delete
/security/roles/                   → security:group_list
/security/roles/create/            → security:group_create
/security/roles/<pk>/edit/         → security:group_update
/security/roles/<pk>/delete/       → security:group_delete
/security/permissions/             → security:permission_list
```
Montada en `config/urls.py` entre `accounts/` (login/logout nativos de
Django) y `billing.urls`.

**Templates** (`security/templates/security/`): `register.html`,
`user_list.html`, `user_form.html`, `group_list.html`, `group_form.html`,
`permission_list.html`, `confirm_delete.html` (genérico, sirve para User
y Group por igual — `DeleteView` siempre manda `object` en el contexto).

### 12.5 Vistas reales protegidas por rol (`billing`, `purchasing`, `creditos_ventas`, `creditos_compras`)

Mapeo aplicado con `GroupRequiredMixin` (CBV) o `@group_required` (FBV):

- **`CATALOGO_COMPRAS = ['Analista de Compras', 'Administrador']`** →
  Brand/ProductGroup/Supplier/Product (todas las CBV/FBV de `billing`,
  incluido `ProductDetailView`), TODA `purchasing` (8 FBV — `purchasing/views.py`
  es 100% FBV, no tiene ninguna CBV), y en `creditos_compras`:
  `CuotaCompraPendientesListView`, `CuotaCompraListView`, `HistorialPagosListView`,
  `imprimir_plan_pagos`, `comprobante_lote`, `comprobante_lote_pdf`.
- **`VENTAS = ['Vendedor', 'Administrador']`** → Customer, Invoice (todas
  las CBV/FBV de `billing`), y en `creditos_ventas`:
  `CuotaVentaPendientesListView`, `CuotaVentaListView`, `HistorialPagosListView`,
  `imprimir_plan_pagos`, `comprobante_lote`, `comprobante_lote_pdf`.
- **Sin cambios (cualquier rol logueado)**: `home` (dashboard, KPIs de
  ambas áreas), `global_search` (cross-área), `registrar_pagos` en ambos
  módulos de crédito (decisión explícita, ver 7.3).

**Hallazgo real de la auditoría previa al cambio**: `CuotaVentaListView`,
`HistorialPagosListView` (y sus espejos en `creditos_compras`) **no tenían
NI `LoginRequiredMixin`** antes de esta sesión — cualquiera, sin loguearse,
podía ver el listado completo de cuotas y el historial de pagos. Se
corrigió como parte de agregarles `GroupRequiredMixin` (que ya valida
`is_authenticated` internamente).

Verificado en runtime (no solo `manage.py check`) con `Client()` +
`force_login()` cruzando roles: usuario Vendedor bloqueado en rutas de
Catálogo/Compras y viceversa, Administrador y superusuario con acceso total.

### 12.6 Bug encontrado y corregido: `home.html` no extendía `base.html`

Antes de esta sesión, `billing/templates/billing/home.html` era un archivo
HTML **standalone completo** (con su propio `<!DOCTYPE html>`, su propio
`<aside class="sidebar">` duplicado y sin segmentar por rol, y su propio
sistema de mensajes `.messages-wrap`/`.msg-*` con auto-dismiss JS). Al
implementar el sidebar segmentado por rol en `base.html`, **el cambio no se
reflejaba en `/` (home)** porque ese template nunca leía `base.html` —
tenía una copia vieja pegada del sidebar. Como `/` es `LOGIN_REDIRECT_URL`,
era la primera pantalla que veía cualquier usuario tras loguearse.

**Diagnóstico real**: se confirmó que era el ÚNICO archivo de toda la app
con este problema (barrido completo del repo buscando templates que
empezaran con `<!DOCTYPE html>` en vez de `{% extends %}`), y que en
cualquier otra página (`/customers/`, etc.) el sidebar SÍ se segmentaba
correctamente por rol — el bug estaba aislado a `home.html`.

**Fix**: se agregaron dos hooks nuevos a `base.html` — `{% block extra_css %}`
(antes de `</head>`) y `{% block extra_js %}` (antes de `</body>`) — y se
reescribió `home.html` para `{% extends 'billing/base.html' %}`, moviendo
el CSS específico del dashboard (KPIs, gráfico de barras CSS puro, tabla de
reporte de compras) a `extra_css`, y todo el contenido a `{% block content %}`.
**No se tocó ningún número, cálculo ni variable de contexto** — verificado
comparando los valores renderizados antes/después con datos reales de la
BD. Se descartó el CSS/JS duplicado del sidebar y de mensajes (ya cubiertos
por `base.html`); el script de auto-dismiss de `.messages-wrap` se eliminó
por completo (huérfano, ese contenedor ya no existe).

**Bug relacionado, mismo hallazgo**: `messages.error()` generaba la clase
CSS `alert-error` (tag por defecto de Django para nivel `ERROR`), que **no
es una clase válida de Bootstrap** (Bootstrap usa `alert-danger`) — el
mensaje se veía sin color rojo. Se agregó a `config/settings.py`:
```python
from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {message_constants.ERROR: 'danger'}
```

### 12.7 Tests (`security/tests.py`) — 12 tests

Sigue el mismo patrón que `creditos_ventas`/`creditos_compras`: `TestCase`,
`Client()` + `override_settings(ALLOWED_HOSTS=['testserver'])` como context
manager, nombres de test en español, comentarios numerados breves.

- `SecurityRolesSetupTests` (2): `setup_roles` crea los 3 roles exactos y
  es idempotente (correrlo 2 veces no duplica `Group` ni cambia conteo de
  permisos).
- `RegisterViewTests` (2): registro con rol válido asigna el `Group`
  correcto; registro sin rol no crea el `User` (mensaje de error en
  **español** — `'Este campo es obligatorio.'`, por `LANGUAGE_CODE='es-ec'`,
  no en inglés).
- `GroupRequiredMixinTests` (4): Vendedor bloqueado en `/security/users/`,
  Analista de Compras bloqueado en `/security/roles/` (ambos con mensaje de
  error verificado vía `r.context['messages']`), Administrador no-superuser
  sí entra, **superusuario sin ningún `Group` asignado también entra**
  (bypass real probado, no solo asumido).
- `HasGroupTemplateTagTests` (4): filtro `has_group` como función pura —
  rol propio `True`, rol ajeno `False`, superuser sin grupos `True`,
  `AnonymousUser` siempre `False`.

**Decisión de diseño**: el `setUp` de los tests llama a
`call_command('setup_roles')` (envuelto en un helper `_setup_roles()` que
solo silencia el stdout) **en vez de reimplementar el mapa de permisos
dentro del test**. Razón: si el mapa de `setup_roles.py` cambia en el
futuro, un test con lógica duplicada seguiría "pasando" contra su propia
copia desactualizada — probar el comando real es la única forma de que el
test detecte una regresión real.

**Comando `setup_roles`** (`security/management/commands/setup_roles.py`):
idempotente (`get_or_create` + `.set()`), mapa `ROLES` extendido más allá
del PDF de la guía original (que solo cubría `billing`/`purchasing`) para
incluir también `creditos_ventas`/`creditos_compras`:
- `Administrador`: `Permission.objects.all()` → **80 permisos**.
- `Vendedor`: 17 codenames exactos (billing: Customer×3, CustomerProfile×3,
  Invoice×3, InvoiceDetail×3, Product view-only×1; creditos_ventas:
  CuotaVenta view+change×2, PagoCuotaVenta view+add×2) → **17 permisos**
  asignados, confirmado que no hay codenames mal escritos (el conteo
  esperado coincide exacto con el asignado).
- `Analista de Compras`: 27 codenames (billing: Brand/ProductGroup/Supplier/
  Product×4 c/u; purchasing: Purchase×4, PurchaseDetail×3;
  creditos_compras: CuotaCompra×2, PagoCuotaCompra×2) → **27 permisos**.

### 12.8 Hallazgos de seguridad encontrados y corregidos en auditoría posterior

Cuatro huecos reales encontrados auditando la app `security` ya construida
(no en el diseño original del PDF de la guía):

**1. Escalación de privilegios en el registro público** — `UserRegisterForm.role`
usaba `Group.objects.all()` sin filtrar: cualquier persona no autenticada
podía auto-registrarse eligiendo `'Administrador'` en `/security/register/`,
sin aprobación de nadie. **Fix**: `Group.objects.exclude(name='Administrador')`
(sección 12.4). Los Administradores ahora solo se crean por otro
Administrador ya existente (vía `UserUpdateForm`, protegida por
`AdminOnlyMixin`) o por `createsuperuser`.

**2. Auto-eliminación y auto-degradación de Administradores** — **verificado
en runtime, no solo razonado**, dentro de una transacción con rollback
explícito (para no dejar rastro en la BD real) que un Administrador podía:
   - (a) Eliminarse a sí mismo desde `/security/users/<su propio pk>/delete/`
     — confirmado: `status 302`, el usuario dejaba de existir.
   - (b) Quitarse su propio rol `Administrador` vía `UserUpdateForm` dejando
     el conteo de Administradores activos en 0 — confirmado: `status 302`,
     `admin_test.groups` quedaba en `[]`.

   **Fix (a)**: `UserDeleteView.post()` override — rechaza si
   `self.get_object().pk == request.user.pk`, mensaje de error, redirect.
   Se implementó sobreescribiendo `post()` (no `dispatch()`) para que el
   chequeo corra **después** de que `AdminOnlyMixin` ya validó login+rol —
   así un usuario sin rol Administrador que manipule la URL recibe el
   mensaje de permiso correcto, no el de auto-eliminación.

   **Fix (b)**: `UserUpdateView.form_valid()` override — si el usuario
   editado es el propio `request.user` Y el nuevo conjunto de `groups` ya
   no incluye `'Administrador'` Y es el único Administrador activo
   (`User.objects.filter(groups__name='Administrador', is_active=True).count() == 1`),
   rechaza con `messages.error()` y `self.form_invalid(form)` (no guarda).

**3. El `Group` `'Administrador'` se podía eliminar completo** —
`GroupDeleteView` no protegía contra borrar su propio grupo base, lo que
rompería `group_required=['Administrador']` en todo el sistema (mitigado
parcialmente porque el superusuario real siempre tiene bypass, pero
cualquier Administrador "normal" perdería su rol de la noche a la mañana).
**Fix**: `GroupDeleteView.post()` override — rechaza si
`self.get_object().name == 'Administrador'`.

**4. Validación de contraseñas** — se auditó `AUTH_PASSWORD_VALIDATORS` en
`config/settings.py`: **ya existía**, completo, con los 4 validadores
estándar de Django (`UserAttributeSimilarityValidator`,
`MinimumLengthValidator`, `CommonPasswordValidator`, `NumericPasswordValidator`).
No fue necesario agregar nada.

Los 4 fixes se verificaron en runtime contra la BD real (no solo
`manage.py check`/tests): intento de auto-eliminación rechazado con mensaje,
intento de auto-degradación rechazado con mensaje, intento de eliminar el
Group `'Administrador'` rechazado con mensaje, select de rol en
`/security/register/` confirmado sin la opción `'Administrador'`.

### 12.9 Eliminación del registro viejo en `billing`

Como parte de crear `security`, se eliminó por completo el sistema de
registro que antes vivía en `billing`:
- `billing/views.py`: eliminada `SignUpView`, removido el import huérfano
  `from django.contrib.auth import login` (no se usaba en ningún otro lado).
- `billing/forms.py`: eliminada `SignUpForm`, removidos los imports huérfanos
  `UserCreationForm`, `User`, `validate_only_letters` (este último NO se usa
  en ningún otro form de `billing/forms.py` — el `Customer` con
  `validate_only_letters` está aplicado a nivel de **modelo**
  (`billing/models.py`), no de form).
- `billing/urls.py`: eliminada la ruta `signup/`.
- `templates/registration/signup.html`: eliminado.
- `templates/registration/login.html` y `billing/Templates/billing/base.html`:
  actualizados de `{% url 'billing:signup' %}` a `{% url 'security:register' %}`.
- Confirmado con grep global: **cero referencias restantes** a `billing:signup`
  en todo el proyecto.

---

## 13. Auditoría de todo el proyecto + configuración de correo (sesión actual, 2026-07-16)

### 13.1 Auditoría completa — estado verificado en código real (no solo lo escrito en este HANDOFF)

Se corrió la suite completa, `manage.py check`/`--deploy`, `makemigrations
--check --dry-run`, y se releyó línea por línea el código de `billing`,
`purchasing`, `shared` y `security` para confirmar (o refutar) lo
documentado en la sección 12.

**Confirmado, coincide con lo documentado**:
- `git status` idéntico al descrito en la sección 9 — nada se movió solo
  entre sesiones.
- Sin migraciones pendientes.
- Los 4 fixes de seguridad de la sección 12.8 (rol `Administrador` excluido
  del registro público, auto-eliminación bloqueada, auto-degradación del
  único Admin bloqueada, borrado del `Group` `Administrador` bloqueado,
  validadores de contraseña completos) — **verificados presentes y
  correctos en el código actual**, no solo en los tests.
- `manage.py check --deploy` — 8 warnings, todos esperables para un
  proyecto de portafolio (`DEBUG=True`, `SECRET_KEY` insegura, sin
  HTTPS/HSTS/cookies seguras, `ALLOWED_HOSTS=[]`). No requieren acción
  salvo despliegue real.

**Discrepancias encontradas contra este HANDOFF (corregidas acá)**:
- **Conteo de tests**: la sección 8 decía "50 tests, todos verdes". El
  conteo real actual es **55 tests, todos verdes**
  (`python manage.py test billing purchasing creditos_ventas
  creditos_compras security` → `Ran 55 tests ... OK`). No hay tests
  rotos, solo el número había quedado desactualizado.
- **🔴 Hallazgo importante — RBAC de solo lectura, contradice la sección
  12.5**: la sección 12.5 afirmaba que "todas las CBV/FBV" de `billing`
  y `purchasing` (incluida `ProductDetailView`) estaban protegidas por
  `GroupRequiredMixin`/`@group_required`. **Verificado en código: es
  falso.** Las vistas de **solo lectura** (`ProductGroupListView`,
  `SupplierListView`, `ProductListView`, `ProductDetailView`,
  `CustomerListView`, `brand_list`, `invoice_list`, `invoice_detail`,
  `purchase_list`, `purchase_detail`, `purchase_pdf`/`excel`,
  `purchase_report`) tienen **solo `LoginRequiredMixin`/`@login_required`**,
  sin `group_required` — cualquier rol logueado puede leerlas. Solo las
  vistas de **mutación** (Create/Update/Delete) están realmente
  restringidas por rol. Mismo patrón en `security`: `UserListView`,
  `GroupListView`, `PermissionListView` son de lectura abierta a
  cualquier autenticado, no solo a `Administrador` (la restricción real
  es que no aparecen en el sidebar de ese rol, pero la URL directa no
  está bloqueada).
  **Estado de la decisión**: presentado al usuario el 2026-07-16, **pospuesta
  explícitamente** ("aún no decidir, seguir con otra cosa") — no se tocó
  código de RBAC. Sigue pendiente decidir si esto es un diseño intencional
  (lectura abierta / escritura restringida) que solo requiere corregir la
  sección 12.5 del HANDOFF, o si es un hueco real que falta cerrar
  agregando `group_required` también a las vistas de lectura. **Si se
  retoma este proyecto, preguntar esto primero antes de tocar RBAC.**

### 13.2 Configuración de envío de correo real (Gmail SMTP) — EN PROGRESO, NO VERIFICADO

Motivación: preparar infraestructura de correo antes de construir
cualquier feature que la use (ej. notificaciones de vencimiento de
cuotas). Requisito explícito del usuario: la contraseña de aplicación de
Gmail **nunca hardcodeada en `settings.py`** — el repo es público en
GitHub y ya hubo un incidente previo de credenciales filtradas.

**Hecho**:
- `python-decouple==3.8` — **ya estaba instalado** en el intérprete real
  del proyecto (`C:\Users\Luiax\AppData\Local\Programs\Python\Python313\python.exe`)
  antes de esta sesión, pero no figuraba en ningún `requirements.txt`.
  Agregado a **ambos** `requirements.txt` (raíz e interno) como
  `python-decouple==3.8`.
- `.gitignore` (raíz, único que existe en el repo) **ya cubría `.env`**
  desde antes — no hizo falta agregarlo.
- Creado `sales_project/sales_project/.env` (junto a `manage.py`, fuera
  de git) con placeholders:
  ```
  EMAIL_HOST_USER=tu_correo@gmail.com
  EMAIL_HOST_PASSWORD=tu_contraseña_de_aplicacion_de_16_caracteres
  ```
  Confirmado con `git status` que `.env` no aparece como archivo para
  commitear.
- `config/settings.py`: agregado `from decouple import config` (junto a
  los demás imports), y una sección nueva **separada** de la de reglas de
  negocio de crédito (sección 7.4) — decisión deliberada, son conceptos
  sin relación:
  ```python
  # Correo (Gmail SMTP) — credenciales fuera del código, ver .env (no versionado)
  EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
  EMAIL_HOST = 'smtp.gmail.com'
  EMAIL_PORT = 587
  EMAIL_USE_TLS = True
  EMAIL_HOST_USER = config('EMAIL_HOST_USER')
  EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
  DEFAULT_FROM_EMAIL = f'TecnoStock S.A. <{EMAIL_HOST_USER}>'
  ```
- `manage.py check` pasa OK con esta config (solo el warning cosmético de
  siempre de `debug_toolbar`).

**Bug real detectado en las instrucciones originales del usuario, señalado
antes de ejecutar**: el plan asumía que `config('EMAIL_HOST_USER')` iba a
"fallar" mientras el `.env` tuviera el placeholder sin completar, y que
eso sería la señal para saber que faltaba llenarlo. **Falso** —
`python-decouple` no distingue un placeholder de un valor real, solo
lanza error si la clave falta por completo del `.env`. Con el placeholder
puesto, `config()` lo carga como texto literal sin quejarse.

**Estado real, verificado con `python manage.py shell -c "..."` corriendo
`send_mail(...)` con `fail_silently=False`** (dos veces, antes y después
de que el usuario dijera "listo"): en **ambas ocasiones** se obtuvo
`UnicodeEncodeError: 'ascii' codec can't encode character '\xf1' in
position 32` — la `ñ` de la palabra "contraseñ**a**" del placeholder
`tu_contraseña_de_aplicacion_de_16_caracteres`. Se confirmó leyendo el
`.env` directamente: **el archivo sigue con el placeholder original, sin
completar**, pese a que el usuario indicó "listo". El usuario decidió
explícitamente (2026-07-16) documentar este estado tal cual — configurado
pero **NO verificado** — y completar el `.env` más tarde, en vez de
bloquear la actualización del HANDOFF a que el correo funcione.

**Si se retoma esto**: no asumir que el envío de correo funciona por el
solo hecho de que `manage.py check` pasa. Confirmar primero que
`sales_project/sales_project/.env` tiene un `EMAIL_HOST_USER`/
`EMAIL_HOST_PASSWORD` reales (sin `ñ` de placeholder, sin espacios en la
contraseña de aplicación), y recién ahí volver a correr el `send_mail` de
prueba. Errores esperables si aun así falla: cuenta sin 2FA activado
(la contraseña de aplicación no funciona sin 2FA), contraseña de
aplicación mal copiada (con espacios), o uso accidental de la contraseña
normal de la cuenta en vez de la de aplicación. **No se ha construido
ninguna vista/modelo/feature sobre esta infraestructura de correo
todavía** — instrucción explícita del usuario de no avanzar hasta
verificar el envío real.

**Actualización de esta misma sesión**: se intentó completar el `.env`
dos veces más con datos reales del usuario y ambas veces resultaron ser
credenciales inválidas para Gmail SMTP:
1. `luiaxel-22@hotmail.com` + `09636262702203` — cuenta de **Hotmail**, no
   Gmail (incompatible con `EMAIL_HOST='smtp.gmail.com'`), y el
   "password" son 14 dígitos, no una contraseña de aplicación (que son 16
   letras minúsculas). No se escribió al `.env`.
2. `borboragui@gmail.com` + `09636262702203` (mismo número otra vez) — se
   confirmó con el usuario que **la cuenta no tiene verificación en 2
   pasos activada**, por lo que Google no permite generar contraseñas de
   aplicación reales todavía. Tampoco se escribió al `.env`.

El usuario activó 2FA y confirmó que `myaccount.google.com/apppasswords`
ya le muestra el formulario para generar una contraseña de aplicación
real, pero al momento de escribir esto **todavía no la generó/pasó** —
quedó pausado ahí para retomar el punto 5.2 del roadmap (unicidad de
email, sección 14). **No tocar el `.env` ni asumir que el correo
funciona** hasta que el usuario entregue una contraseña de 16 letras
minúsculas generada de verdad en esa página.

---

## 14. Unicidad de email en `User` — Fase 3, punto 5.2 (sesión actual, 2026-07-16)

Motivación: la base real (`dbA1.sqlite3`) tiene usuarios duplicados por
email — nunca hubo restricción de unicidad. Se aborda en 2 pasos
separados a pedido explícito del usuario: primero blindar el formulario
(reversible, no toca la BD), después decidir qué hacer con los duplicados
ya existentes, y recién con eso resuelto, migrar `unique=True` a nivel de
modelo.

### 14.1 Paso 1 — Validación a nivel de formulario (COMPLETO)

`security/forms.py`, `UserRegisterForm`: agregado `clean_email()` que
rechaza el registro si ya existe un `User` con ese email
(`User.objects.filter(email__iexact=email).exists()` — case-insensitive,
`"Juan@gmail.com"` y `"juan@gmail.com"` cuentan como el mismo). Mensaje:
`'Ya existe una cuenta registrada con este correo electrónico.'`.
**Nota**: esta validación solo corre en `UserRegisterForm` (registro
público) — `UserUpdateForm` (edición por Administrador) no la tiene, así
que un Administrador todavía puede guardar un email duplicado editando un
usuario existente desde `/security/users/<pk>/edit/`. No se tocó porque
no fue parte del pedido explícito, pero queda anotado para cuando se
migre a `unique=True` real (ahí sí sería un `IntegrityError` a nivel de
BD, no solo de formulario).

`security/tests.py`: 2 tests nuevos (suite pasó de 17 a **19 tests,
todos verdes**) — `test_registro_con_email_duplicado_es_rechazado`
(mismo email con distinto casing, rechazado) y
`test_registro_con_email_nuevo_es_aceptado` (email nunca usado, aceptado).

### 14.2 Paso 2 — Diagnóstico de duplicados existentes en `dbA1.sqlite3` (COMPLETO, sin modificar nada)

Corrido vía `manage.py shell`, solo lectura. **El HANDOFF anterior asumía
3 usuarios con `luiaxel-22@hotmail.com` — el número real confirmado es
4**, y además hay un **segundo grupo de duplicados** que no estaba
documentado:

| Email | Username | date_joined | is_active | is_staff | is_superuser | Grupo |
|---|---|---|---|---|---|---|
| `luiaxel-22@hotmail.com` | `luiggi` | 2026-06-27 17:09 | Sí | No | No | (sin grupo) |
| `luiaxel-22@hotmail.com` | `laguinob` | 2026-07-13 08:54 | Sí | No | No | (sin grupo) |
| `luiaxel-22@hotmail.com` | `axsus22` | 2026-07-16 23:32 | Sí | No | No | Vendedor |
| `luiaxel-22@hotmail.com` | `manuel` | 2026-07-16 23:42 | Sí | No | No | Analista de Compras |
| `adm@gmail.com` | `Adm` | 2026-06-15 03:42 | Sí | Sí | **Sí** | (sin grupo) |
| `adm@gmail.com` | `adm` | 2026-06-15 03:49 | Sí | Sí | **Sí** | (sin grupo) |

No hay usuarios con `email=''` (0 encontrados, no aportan al conteo de
duplicados).

**El grupo `adm@gmail.com` es el más delicado**: dos superusuarios
activos distintos (`Adm`/`adm`, difieren solo en mayúscula), ambos con
acceso total al sistema — no es un simple "usuario de prueba duplicado"
como el otro grupo, son dos cuentas root reales.

### 14.3 Decisión del dueño del proyecto — nadie se borra, se renombran los emails duplicados

Decisión explícita (2026-07-17): **no se elimina ninguna cuenta**. Se
conserva cada usuario tal cual (mismo `pk`, mismos datos vinculados por FK
— facturas, compras, cuotas, pagos — intactos), y a los duplicados
"perdedores" se les reemplaza el email por una variante con `+dupN`
(truco de Gmail/estándar de email, sigue siendo una dirección
técnicamente válida aunque no reciba correos reales).

**Investigación previa (grupo `adm@gmail.com`)**: se consultó
`last_login` de ambas cuentas — `Adm` (mayúscula, id=2) tenía
`last_login=None` (nunca se usó desde que se creó); `adm` (minúscula,
id=3, creado 7 minutos después) tenía `last_login=2026-06-23 14:51:41`.
No había ningún `LogEntry` de `django.contrib.admin` ni sesiones activas
para ninguna de las dos. Con esa evidencia se determinó que `adm`
(minúscula) es la cuenta real en uso, y el usuario lo confirmó.

**Renombres ejecutados** (`UPDATE` sobre el campo `email` únicamente,
ningún `pk` ni FK tocado):

| Username | Email viejo | Email nuevo |
|---|---|---|
| `Adm` (id=2) | `adm@gmail.com` | `adm+dup1@gmail.com` |
| `luiggi` | `luiaxel-22@hotmail.com` | `luiaxel-22+dup1@hotmail.com` |
| `laguinob` | `luiaxel-22@hotmail.com` | `luiaxel-22+dup2@hotmail.com` |
| `manuel` | `luiaxel-22@hotmail.com` | `luiaxel-22+dup3@hotmail.com` |

Conservan el email original sin cambios: `adm` (id=3) → `adm@gmail.com`,
`axsus22` (rol Vendedor) → `luiaxel-22@hotmail.com`. Verificado con query
que no queda ningún email duplicado en `User` tras el renombrado.

### 14.4 `unique=True` real — restricción de Django encontrada y resuelta

**Problema real, no anticipado en el pedido original**: el proyecto usa
`django.contrib.auth.User` directamente — no hay `AUTH_USER_MODEL`
custom, `security/models.py` está vacío. Esto significa que **no se puede
agregar `email = models.EmailField(unique=True)`** y generar una
migración normal: `User` pertenece a `django.contrib.auth` (código de
Django en `site-packages`), no a ninguna app de este proyecto, así que
`makemigrations` no detecta ningún cambio de estado sobre un modelo que
no le pertenece a ninguna app propia.

Dos caminos posibles, presentados al usuario:
1. Migrar a un modelo de usuario custom (`AUTH_USER_MODEL`) — **descartado**:
   reescribiría todas las FKs existentes hacia `auth.User` (facturas,
   compras, permisos, etc.), altísimo riesgo con datos reales ya
   cargados, normalmente exige recrear la base desde cero.
2. **Elegido**: índice `UNIQUE` real por SQL directo sobre la tabla
   `auth_user`, vía una migración de `security` con `RunSQL` (no toca el
   modelo `User` ni ninguna FK, reversible, bajo riesgo).

`security/migrations/0001_email_unique_index.py`:
```python
migrations.RunSQL(
    sql="CREATE UNIQUE INDEX security_uq_auth_user_email ON auth_user (email) WHERE email != '';",
    reverse_sql="DROP INDEX security_uq_auth_user_email;",
)
```
`dependencies = [('auth', '0012_alter_user_first_name_max_length')]`
(última migración real de `auth` en este Django 6.0.6, confirmada antes
de escribir la dependencia).

**Bug real encontrado y corregido en la propia migración, antes de
dejarla así**: la primera versión del índice era `UNIQUE` simple, sin
`WHERE`. SQLite trata `''` (string vacío) como un valor real para efectos
de un índice único — **no** lo exime como haría con `NULL`. Como el
patrón `User.objects.create_user(username=..., password=...)` sin pasar
`email` (usado extensamente en los tests del proyecto, ej.
`GroupRequiredMixinTests.setUp`, que crea 4 usuarios sin email en la
misma prueba) deja `email=''` por defecto, el índice simple rechazaba al
segundo usuario sin email de cada test como si fuera un duplicado real.
Esto rompió 9 tests de `security` en la primera corrida de la suite
completa. Se revirtió la migración (`migrate security zero`), se corrigió
el `RunSQL` a un **índice parcial** (`WHERE email != ''`), y se volvió a
aplicar. Verificado en runtime (`transaction.atomic()` + rollback, sin
dejar rastro en la BD): un email real duplicado sigue bloqueado con
`IntegrityError`, y ahora múltiples usuarios con `email=''` conviven sin
problema.

### 14.5 `UserUpdateForm` — misma validación que `UserRegisterForm`

Agregado `clean_email()` a `UserUpdateForm` (`security/forms.py`), igual
que en `UserRegisterForm` pero con `.exclude(pk=self.instance.pk)` para
que un usuario/Administrador pueda guardar el formulario sin que su
propio email actual se auto-rechace como "duplicado". Cierra el hueco que
había quedado anotado en la sección 14.1 (un Administrador podía asignarle
a un usuario el email de otro vía `/security/users/<pk>/edit/`).

### 14.6 Tests y estado final

`security/tests.py`: nueva clase `EmailUniquenessTests` (4 tests) —
índice `UNIQUE` bloquea duplicado real a nivel de BD
(`IntegrityError`, salteándose el formulario a propósito para probar la
capa de BD independiente), `UserUpdateForm` rechaza el email de otro
usuario, `UserUpdateForm` permite guardar el propio email sin cambios (el
`exclude` no se auto-rechaza), y lo mismo por HTTP real vía
`UserUpdateView` con un Administrador logueado.

**Suite completa, verificada con el comando exacto pedido**:
```
python manage.py test billing purchasing creditos_ventas creditos_compras security
Ran 61 tests in ~26s — OK
```
(57 tests previos + 4 nuevos de `EmailUniquenessTests`; el número subió
de 55 — sección 13.1 — a 57 porque ya incluía los 2 de `clean_email` en
`UserRegisterForm` del paso 1 de este mismo punto 5.2).

**Punto 5.2 (unicidad de email) — CERRADO.** Pendiente relacionado que
queda para otra sesión: el correo real por Gmail SMTP (sección 13.2)
sigue sin verificar, no se tocó en este punto a pedido explícito del
usuario ("el tema de correo real... queda en pausa por ahora, no depende
de este punto").

---

## 15. Pago simulado con PayPal — Fase 3, punto 5.3 (sesión actual, 2026-07-17)

Checkout de PayPal **100% visual/simulado** — no se conecta contra la API
real ni sandbox de PayPal. Aplica a ambos módulos de crédito
(`creditos_ventas`: cliente paga a la empresa; `creditos_compras`: la
empresa paga a un proveedor), mismo patrón de duplicación espejada que ya
usa el resto del proyecto.

### 15.1 Diseño (decidido antes de escribir código, ver hilo de la sesión)

El formset de cuotas de `registrar_pagos` (checkbox+valor por fila) **no
se tocó** — el pago manual sigue exactamente igual. Se agregó un
**segundo botón** "Pagar con PayPal" al lado de "Registrar pagos", que
usa las mismas filas marcadas pero en vez de guardar el pago de
inmediato, lo deja en sesión y arranca un checkout simulado de 3 pasos:
**staging → login falso → confirmación**. La confirmación llama al mismo
`services.registrar_pagos_multiples()` de siempre — **cero lógica de
mora/descuento/liquidación reimplementada**, PayPal es solo una fachada
sobre el mismo motor de pagos.

**Decisiones confirmadas explícitamente por el usuario antes de
implementar**:
- Default `metodo_pago='EFECTIVO'` para todo el histórico al migrar (no
  había ningún pago previo en la BD real al momento de migrar, así que
  esto no tuvo efecto práctico, pero quedó como default correcto).
- El pago vía PayPal admite **parcial o total**, exactamente las mismas
  reglas que ya tiene `registrar_pago` (tope por `saldo`, pago mínimo,
  etc.) — no se agregó ninguna restricción "solo liquidación total".

### 15.2 Modelos y migraciones

`PagoCuotaVenta`/`PagoCuotaCompra` (`creditos_ventas`/`creditos_compras`
`models.py`) — 2 campos nuevos en ambos, idénticos:
```python
metodo_pago = models.CharField(max_length=15, choices=METODO_PAGO_CHOICES, default='EFECTIVO')
paypal_transaction_id = models.CharField(max_length=40, blank=True)
```
`METODO_PAGO_CHOICES = [('EFECTIVO', 'Efectivo'), ('TRANSFERENCIA', 'Transferencia'), ('PAYPAL', 'PayPal')]`.
Migraciones: `creditos_ventas/migrations/0003_pagocuotaventa_metodo_pago_and_more.py`,
`creditos_compras/migrations/0003_pagocuotacompra_metodo_pago_and_more.py`
— `AddField` normal, sin ningún `RunPython`/`RunSQL` (a diferencia de la
migración de unicidad de email de la sección 14, acá sí es un modelo
propio del proyecto, no `auth.User`). No hay ningún modelo nuevo
(`PagoPaypalSimulado` descartado en el diseño) — el ID de transacción es
solo un campo más del `PagoCuota*` ya existente.

### 15.3 Vistas — 3 nuevas por módulo + helper de parsing compartido

`_parsear_formset_a_pagos_data(formset)` (nueva función a nivel de módulo
en `views.py` de cada app, **no compartida entre apps** — sigue el mismo
patrón de duplicación espejada que el resto del proyecto): recorre el
formset ya validado y arma `pagos_data`. La usan tanto `registrar_pagos`
(pago manual, refactorizado para llamarla en vez de tener el parsing
inline) como `pagar_con_paypal` (staging) — antes este parsing solo
existía inline dentro de `registrar_pagos` y se iba a duplicar.

**3 vistas nuevas por módulo** (`creditos_ventas/views.py` y
`creditos_compras/views.py`, todas `@login_required` sin `@group_required`
— mismo criterio que `registrar_pagos`, ver sección 7.3/12.5):

1. **`pagar_con_paypal(request, factura_id|compra_id)`** — solo POST.
   Reusa `_parsear_formset_a_pagos_data`, y si hay algo que pagar, guarda
   en `request.session['paypal_pago_pendiente']` (`'..._compras'` en el
   otro módulo, clave separada a propósito, mismo criterio que
   `ultimo_lote_pagos`/`ultimo_lote_pagos_compras`) un dict
   `{'factura_id'|'compra_id': ..., 'pagos_data': [...]}`. **`valor` se
   guarda como `str(Decimal)`, no como `Decimal`** — el serializador de
   sesión de Django es JSON por default y `Decimal` no es serializable
   ahí; se reconstruye con `Decimal(...)` al leer. Redirige a
   `paypal_login`.
2. **`paypal_login(request, factura_id|compra_id)`** — si no hay nada
   pendiente en sesión para esa factura/compra, redirige de vuelta con
   error (cubre entrar directo por URL sin pasar por el staging). GET
   renderiza el form falso (email/password, ninguno valida nada real);
   POST simplemente avanza a `paypal_confirmar`.
3. **`paypal_confirmar(request, factura_id|compra_id)`** — GET arma las
   filas para mostrar (cuota + valor) leyendo la sesión. POST: reconstruye
   `pagos_data` con `Decimal`, llama a
   `services.registrar_pagos_multiples(pagos_data)` **sin modificar
   services.py para nada**, genera
   `'PAYPAL-' + secrets.token_hex(4).upper()` (8 hex uppercase, ej.
   `PAYPAL-8F3A21C9`) y por cada `PagoCuota*` creado le hace
   `pago.metodo_pago='PAYPAL'; pago.paypal_transaction_id=transaction_id;
   pago.save(update_fields=[...])` — un `UPDATE` de metadata después del
   hecho, no una reimplementación de la liquidación. Guarda
   `ultimo_lote_pagos` igual que el flujo manual y redirige al mismo
   `comprobante_lote` de siempre.

**URLs nuevas** (idénticas en estructura a lo propuesto en el diseño):
```
/creditos/facturas/<id>/pagar/paypal/                → pagar_con_paypal (staging)
/creditos/facturas/<id>/pagar/paypal/login/           → paypal_login
/creditos/facturas/<id>/pagar/paypal/confirmar/       → paypal_confirmar
```
(espejo bajo `/creditos-compras/compras/<id>/pagar/paypal/...`)

### 15.4 Templates

`paypal_login.html` y `paypal_confirm.html` nuevos en ambos módulos
(`creditos_ventas/templates/creditos_ventas/` y su espejo en
`creditos_compras`) — extienden `billing/base.html` como el resto del
proyecto, wordmark "PayPal" simplificado en CSS (texto negrita/cursiva,
`Pay` en `#003087` + `Pal` en `#0070BA`, **no el logo oficial en SVG**),
botón de login en `#0070BA`, botón "Pagar ahora" en `#FFC439` con texto
`#003087`, y banner fijo `MODO SIMULACIÓN — no se procesa ningún pago
real` en ambas pantallas. En `paypal_confirm.html` el destinatario
mostrado es `TecnoStock S.A.` (hardcodeado) en `creditos_ventas`, y
`{{ compra.supplier.name }}` en `creditos_compras`.

`registrar_pagos.html` (ambos módulos): el botón "Registrar pagos"
original ahora tiene `name="accion" value="manual"` (no se usa
realmente en la vista, es solo para diferenciar el submit en el HTML) y
se agregó al lado el botón "Pagar con PayPal" con
`formaction="...:pagar_con_paypal"` — mismo `<form>`, mismos campos,
dos `formaction` distintos. El comportamiento del botón manual **no
cambió**.

`comprobante_lote.html` (ambos módulos): nueva columna "Método" — si
`pago.metodo_pago == 'PAYPAL'` muestra un badge azul `Pagado vía PayPal —
ID: <paypal_transaction_id>`, si no, `{{ pago.get_metodo_pago_display }}`
(`Efectivo`/`Transferencia`).

### 15.5 Tests

`CreditosVentasPaypalTests` (`creditos_ventas/tests.py`) y
`CreditosComprasPaypalTests` (`creditos_compras/tests.py`, espejo
1:1) — 4 tests cada uno, **8 nuevos en total**:
1. Flujo completo por HTTP real (staging → login → confirmar) con
   liquidación total: verifica cada redirect intermedio, que la cuota
   queda `PAGADA`, `metodo_pago='PAYPAL'`, `paypal_transaction_id` matchea
   `^PAYPAL-[0-9A-F]{8}$`, y que el comprobante final contiene "Pagado vía
   PayPal".
2. Pago parcial vía PayPal: confirma que respeta las mismas reglas 1:1
   sin interés/descuento que el pago manual (mismo comportamiento que los
   tests de `registrar_pago` en `CreditosVentasServicesTests`/
   `CreditosComprasServicesTests`, solo que disparado por el flujo
   PayPal).
3. El botón manual sigue guardando `metodo_pago='EFECTIVO'` por default
   — confirma que el flujo existente no se rompió con los campos nuevos.
4. Entrar directo a `/paypal/login/` sin pasar por el staging (sin nada
   pendiente en sesión) redirige con mensaje de error en vez de reventar.

**Bug real encontrado y corregido escribiendo los tests, mismo patrón que
ya documenta la sección 8**: el primer intento de
`test_pago_manual_sigue_quedando_en_efectivo` no fijaba
`cuota.fecha_vencimiento` a hoy, así que la cuota generada por
`generar_cuotas` vencía a futuro (1 mes después de la factura) — pagar
`cuota.saldo` completo entonces superaba `monto_para_liquidar_hoy()` (que
es menor por el descuento de pronto pago, comportamiento documentado en
sección 7.2) y `registrar_pago` lo rechazaba con `ValidationError`,
haciendo que nunca se creara el `PagoCuotaVenta` que el test esperaba
leer. Corregido fijando `fecha_vencimiento = timezone.localdate()` antes
de pagar, igual que ya hacían los demás tests del archivo.

**Suite completa, comando exacto pedido**:
```
python manage.py test billing purchasing creditos_ventas creditos_compras security
Ran 69 tests in ~29s — OK
```
(61 tests previos + 4 de `CreditosVentasPaypalTests` + 4 de
`CreditosComprasPaypalTests`). Sin migraciones pendientes
(`makemigrations --check --dry-run` → `No changes detected`).

**Punto 5.3 (PayPal simulado) — CERRADO.** No se tocó el tema de correo
real (sigue en pausa, sección 13.2), a pedido explícito del usuario.

---

## 16. Facturación electrónica SRI simulada — Fase 3, punto 5.5 (sesión actual, 2026-07-17)

**Aclaración de origen**: en esta sesión no existe (ni existió) una
sección "5.5" de este HANDOFF sobre SRI — la numeración "Fase 3, punto
X.Y" viene de un roadmap externo que maneja el usuario, no de este
documento. Se trabajó directo con la especificación técnica que el
usuario pasó en el mensaje (estructura real de la clave de acceso de 49
dígitos, ciclo de vida real del SRI), validada por él de antemano.

Simulación **100% offline** — no se conecta contra el SRI real ni
sandbox, no implementa firma electrónica XAdES-BES real (sin
criptografía de certificado). Aplica tanto a `billing.Invoice` (tipo 01,
Factura) como a `purchasing.Purchase` (tipo 03, Liquidación de compra).

### 16.1 Decisión de arquitectura: una sola app, un solo modelo

A diferencia de `creditos_ventas`/`creditos_compras` (que sí se duplican
porque tienen reglas de negocio realmente distintas), acá se creó
**una sola app nueva `facturacion_electronica`** con **un solo modelo**
`ComprobanteElectronico`, con dos FKs nulas (`factura`, `compra`) y un
`CheckConstraint` que exige exactamente una de las dos. Justificación:
la lógica de clave de acceso/módulo 11/estados SRI es idéntica sin
importar el origen — duplicarla en dos apps habría sido puro copy-paste.

`INSTALLED_APPS` (`config/settings.py`): agregada `'facturacion_electronica'`
después de `'security'`. URLs montadas en `/facturacion/`
(`config/urls.py`).

### 16.2 RUC ficticio de la empresa y probabilidades de simulación (`settings.py`)

```python
EMPRESA_RUC = '0992345675001'
SRI_SIMULACION_PROBABILIDADES = {
    'AUTORIZADO': 0.85,
    'RECHAZADO': 0.10,
    'DEVUELTO': 0.05,
}
```
`EMPRESA_RUC`: no existía ningún RUC de la empresa en el proyecto antes
de esta sesión (ni en `settings.py` ni en ningún modelo — el único
`dni`/RUC del proyecto es el de `Customer`, dato del cliente, no de
TecnoStock). Se generó uno ficticio de sociedad privada (tercer dígito
9, provincia 09/Guayaquil, coherente con `TIME_ZONE`), con dígito
verificador real calculado a mano y **verificado programáticamente**
contra el propio `shared.validators.validate_cedula_ec` antes de
usarlo (`validate_cedula_ec('0992345675001')` no lanza excepción).

### 16.3 Nueva función de módulo 11 — `shared/validators.py`

`calcular_digito_verificador_clave_acceso(digits_48)`, agregada junto a
`validate_cedula_ec` (mismo archivo, ambas son validación ecuatoriana
reusable) pero con un algoritmo **deliberadamente distinto**: pesos
cíclicos `2,3,4,5,6,7` (no una lista fija de 9 coeficientes como cédula),
recorridos de derecha a izquierda sobre 48 dígitos (48 es múltiplo
exacto de 6, el ciclo cierra limpio). Reglas especiales: resultado 10 →
verificador 1, resultado 11 → verificador 0.

**6 tests unitarios de la función sola** (`CalcularDigitoVerificadorClaveAccesoTests`
en `facturacion_electronica/tests.py` — ver 16.7 sobre por qué viven ahí
y no en `shared`), con casos calculados a mano **antes** de escribir la
función y confirmados después contra la implementación (no solo
"lo que la función devuelve es lo correcto por definición"):
dígito único en la posición más a la derecha, 48 unos, 48 ceros (caso
especial resultado=11→0), un dígito en posición intermedia del ciclo
(confirma que el offset del ciclo es el correcto, no solo el caso
trivial), longitud inválida, caracteres no numéricos.

### 16.4 Modelo `ComprobanteElectronico` (`facturacion_electronica/models.py`)

Los 9 campos de la clave de acceso guardados por separado (trazabilidad/debug)
+ la clave ya concatenada (`clave_acceso`, `unique=True`, 49 caracteres):
`fecha_emision`, `tipo_comprobante` (`01`/`03`), `ruc_emisor`,
`tipo_ambiente` (**siempre `'1'`**, pruebas), `establecimiento` (`'001'`),
`punto_emision` (`'001'`), `secuencial` (9 dígitos, nunca se reutiliza —
ver 16.5), `codigo_numerico` (8 dígitos aleatorios), `tipo_emision`
(**siempre `'1'`**, normal), `digito_verificador`.

`estado` (`BORRADOR`/`FIRMADO`/`ENVIADO`/`EN_PROCESAMIENTO`/`AUTORIZADO`/
`RECHAZADO`/`DEVUELTO`) — **corrección de diseño que hizo el usuario
sobre una versión anterior mal planteada**: "Firmar" y "Enviar" son
acciones locales del emisor, no estados que reporte el SRI; el SRI real
(esquema offline vigente desde 2022) solo reporta
`En procesamiento → Autorizado/Rechazado/Devuelto`. El modelo de estados
final refleja ambas cosas en una sola cadena.

`xml_firmado` (`TextField`) y `firma_hash` (`CharField`) — **simulación
explícita, no firma XAdES-BES real**, documentado también en el
docstring del modelo y en el comentario dentro del XML simulado
(`<!-- Firma simulada — NO es XAdES-BES real... -->`).

`Meta.constraints`: `CheckConstraint(condition=...)` (Django 6.0.6,
`condition=` es el kwarg correcto — se confirmó la versión de Django
antes de generar la migración, `check=` habría sido necesario solo en
Django <5.1). Migración `facturacion_electronica/migrations/0001_initial.py`,
`AddField`/`CreateModel` normal.

### 16.5 `facturacion_electronica/services.py`

Mismo patrón que `creditos_ventas/services.py` — lógica fuera de las
vistas:
- `generar_clave_acceso(...)` — arma los 9 campos + llama a
  `calcular_digito_verificador_clave_acceso`. Valida que los primeros 48
  caracteres midan exactamente 48 antes de calcular el verificador.
- `_siguiente_secuencial(establecimiento, punto_emision, tipo_comprobante)`
  — `max(secuencial existente para esa combinación) + 1` con
  `select_for_update()` dentro de la transacción de `crear_comprobante`
  (evita que dos altas simultáneas choquen). **El secuencial nunca se
  reutiliza**: aunque el comprobante anterior con ese secuencial termine
  `RECHAZADO`/`DEVUELTO`, el siguiente siempre es
  `max_histórico + 1` — verificado con test dedicado (16.7, test 8).
- `crear_comprobante(factura=None, compra=None)` — exactamente uno de
  los dos; rechaza si ya existe un comprobante **activo** (no
  `RECHAZADO`/`DEVUELTO`) para ese origen — así si el primero fue
  rechazado, se puede generar uno nuevo para la misma factura/compra sin
  tocar el rechazado (que queda como registro histórico).
- `firmar(comprobante)` — `BORRADOR→FIRMADO`. Genera un XML simplificado
  (no el esquema XSD completo del SRI) + `firma_hash` = `sha256(xml +
  timestamp)`.
- `enviar(comprobante)` — `FIRMADO→ENVIADO→EN_PROCESAMIENTO`, ambas
  transiciones en el mismo llamado (no hay nada async real que esperar).
- `consultar_respuesta_sri(comprobante, forzar=None, usuario=None)` —
  sin `forzar`: sortea con `random.choices(weights=...)` sobre
  `settings.SRI_SIMULACION_PROBABILIDADES`. Con `forzar`: exige que
  `usuario` sea `Administrador` o superusuario (mismo criterio de bypass
  que `GroupRequiredMixin`), si no `ValidationError`. Si el resultado
  (sorteado o forzado) es `RECHAZADO`/`DEVUELTO`, llena `motivo_rechazo`
  con un mensaje al azar de `MOTIVOS_RECHAZO`/`MOTIVOS_DEVOLUCION`
  (catálogo de mensajes reales conocidos del esquema SRI, ej. *"Clave de
  acceso ya registrada"*, *"Firma electrónica inválida"*, *"XML no
  cumple esquema XSD del SRI"* — decisión explícita del usuario sobre
  usar catálogo real en vez de un mensaje genérico único).

### 16.6 Vistas, URLs y templates

`facturacion_electronica/views.py` — todas `@login_required` sin
restricción de rol adicional (mismo criterio que el resto de vistas de
acción del proyecto que no tienen reglas de negocio específicas por
rol): `generar_comprobante_factura`, `generar_comprobante_compra`,
`comprobante_detail` (calcula `puede_forzar` en la vista para pasarlo al
template), `firmar_comprobante`, `enviar_comprobante`,
`consultar_comprobante` (lee `forzar` de `request.POST`, `None` si no
viene), `ComprobanteListView` (auditoría, `LoginRequiredMixin`+`ListView`).

URLs bajo `/facturacion/` (`facturacion_electronica/urls.py`, montada en
`config/urls.py`):
```
/facturacion/facturas/<id>/generar/       → generar_factura
/facturacion/compras/<id>/generar/        → generar_compra
/facturacion/comprobantes/                → comprobante_list
/facturacion/comprobantes/<pk>/           → comprobante_detail
/facturacion/comprobantes/<pk>/firmar/    → firmar
/facturacion/comprobantes/<pk>/enviar/    → enviar
/facturacion/comprobantes/<pk>/consultar/ → consultar
```

Templates (`facturacion_electronica/templates/facturacion_electronica/`):
- `comprobante_detail.html` — stepper visual de 4 pasos (Borrador →
  Firmado → Enviado → estado final), banner fijo "MODO SIMULACIÓN", botón
  de acción según el estado actual, 3 botones "Forzar Autorizado/Rechazado/
  Devuelto" visibles **solo** si `puede_forzar` (calculado en la vista,
  mismo criterio de `services.consultar_respuesta_sri`), y una sección
  `<details>` colapsable "Detalle técnico" con los 9 campos + clave
  completa + XML simulado.
- `comprobante_list.html` — listado de auditoría, mismo patrón
  `.list-table` que `historial_pagos.html`/`user_list.html` (tokens CSS
  de `billing/base.html`: `--surface`, `--border-strong`, tipografía
  Manrope/Inter), con paginación igual al resto del proyecto.

**Botón de entrada** agregado a `invoice_detail.html` y
`purchase_detail.html` (ambos ya revisados antes de tocarlos — sin
sorpresas, mismo patrón `content-card`/`page-actions` que el resto del
proyecto): tarjeta "Comprobante Electrónico" que muestra el botón
"Generar comprobante electrónico" si `invoice.comprobantes.first` (o
`purchase.comprobantes.first`) es `None`, o el estado actual + link "Ver
comprobante" si ya existe uno. **Nota de implementación**: se usa
`.first`, no `.last` — como `Meta.ordering = ['-fecha_creacion']` en
`ComprobanteElectronico`, `.first` es el más reciente y `.last` sería el
más antiguo (se detectó y corrigió antes de dar el template por
terminado, no llegó a commitearse el bug).

### 16.7 Tests — 19 nuevos en `facturacion_electronica/tests.py`

Los tests de la función de módulo 11 (`CalcularDigitoVerificadorClaveAccesoTests`,
6 tests) viven en `facturacion_electronica/tests.py` y no en un
`shared/tests.py` — **`shared` no es una app Django registrada** (sin
`apps.py`, no está en `INSTALLED_APPS`, ver sección 3), así que
`manage.py test shared` no funciona; `facturacion_electronica` es la
única app que consume esa función, así que sus tests viven ahí.

`ComprobanteElectronicoServiciosTests` (10 tests): creación de
comprobante para factura (tipo `01`) y compra (tipo `03`), dos
comprobantes nunca comparten clave de acceso, rechaza segundo
comprobante activo para el mismo origen, flujo completo hasta
`AUTORIZADO` forzado (con `xml_firmado`/`firma_hash`/timestamps
verificados en cada paso), flujo hasta `RECHAZADO` con motivo del
catálogo real, transiciones fuera de orden rechazadas (firmar dos veces,
enviar sin firmar), **secuencial nunca se reutiliza tras un rechazo**
(crea un segundo comprobante para la misma factura después de rechazar
el primero, confirma `secuencial_2 == secuencial_1 + 1`), `forzar=`
bloqueado para no-Administrador y para `usuario=None`.

`ComprobanteElectronicoVistasTests` (3 tests): flujo completo por HTTP
real (generar→firmar→enviar→consultar forzado) con un Administrador
logueado, el botón "Generar comprobante electrónico" aparece en
`invoice_detail.html` cuando no hay comprobante, la vista `consultar`
bloquea `forzar=` para un usuario sin rol Administrador (mensaje de
error visible, estado no cambia).

**Suite completa, comando exacto pedido**:
```
python manage.py test billing purchasing creditos_ventas creditos_compras security facturacion_electronica
Ran 88 tests in ~41s — OK
```
(69 tests previos + 19 nuevos: 6 de módulo 11 + 10 de servicios + 3 de
vistas). Sin migraciones pendientes (`makemigrations --check --dry-run`
→ `No changes detected`).

**Punto 5.5 (facturación electrónica SRI simulada) — CERRADO.** No se
tocó el tema de correo real (sigue en pausa, sección 13.2), a pedido
explícito del usuario. No hubo ninguna sorpresa estructural en
`invoice_detail.html`/`purchase_detail.html` que ameritara detenerse a
consultar — ambos siguen el mismo patrón ya documentado del resto del
proyecto.

---

## 17. Cédula en el registro de usuario — requerimiento agregado (sesión actual, 2026-07-17)

**No es parte de los 5 puntos originales del roadmap de Fase 3** — pedido
nuevo del usuario, agregado después de cerrar el punto 5.5. Objetivo:
campo de cédula en `UserRegisterForm`, con unicidad real y validación de
formato con módulo 10 ecuatoriano.

### 17.1 Investigación previa (antes de asumir nada)

- **No existía ningún modelo de perfil en `security`** — `security/models.py`
  estaba vacío (`# Create your models here.`), tal como el HANDOFF ya
  documentaba que probablemente pasaba.
- `shared/validators.py` ya tenía `validate_cedula_ec` lista para reusar
  (la misma función del punto 5.5, que valida cédula de 10 dígitos con
  módulo 10 para persona natural, o RUC de 13 con módulo 11 según el
  tercer dígito).
- **12 usuarios reales existentes en la BD, ninguno con cédula** —
  pero como el diseño es una tabla nueva y separada (`UserProfile`,
  `OneToOneField` opcional a `User`), esto **no generó ningún problema
  de datos históricos**: los 12 usuarios existentes simplemente no
  tienen fila de perfil (la relación es opcional por naturaleza), no
  hizo falta backfill ni dejar el campo `cedula` nullable en el modelo.
  A diferencia del caso de unicidad de email (sección 14), acá no hubo
  que decidir qué hacer con datos preexistentes.

**Restricción respetada**: igual que en el punto 5.2, **no se migró a
un `AUTH_USER_MODEL` custom** — `UserProfile` es una tabla nueva con
`OneToOneField(settings.AUTH_USER_MODEL)`, no un campo agregado a
`auth.User`.

**Decisión del usuario sobre la ambigüedad señalada**: cédula
**obligatoria para todos los roles** en el registro (Vendedor, Analista
de Compras, Administrador) — sin lógica condicional por rol.

### 17.2 Modelo `UserProfile` (`security/models.py`)

```python
class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    cedula = models.CharField(max_length=10, unique=True, validators=[validate_cedula_ec])
```
`max_length=10` filtra de entrada cualquier RUC de 13 dígitos a nivel de
formulario/BD (el `MaxLengthValidator` de Django corre antes que
`validate_cedula_ec`) — así que en la práctica solo pasan cédulas de
persona natural (10 dígitos, módulo 10), aunque `validate_cedula_ec`
en sí mismo también acepte RUCs de 13. Migración
`security/migrations/0002_initial.py` (la app `security` no tenía
ninguna migración previa — no hay modelos hasta este punto, ver sección
12 introducción).

### 17.3 Formularios (`security/forms.py`)

**`UserRegisterForm`**: `cedula = forms.CharField(max_length=10, validators=[validate_cedula_ec])`
(formato, igual que `email` usa `EmailField` para su formato) +
`clean_cedula()` para unicidad (`UserProfile.objects.filter(cedula=cedula).exists()`,
mismo patrón que `clean_email`). `save()` extendido: además de
`user.groups.add(...)`, ahora también `UserProfile.objects.create(user=user, cedula=...)`.

**`UserUpdateForm`**: mismo patrón, con `clean_cedula()` excluyendo al
propio usuario (`.exclude(user=self.instance)`, equivalente al
`.exclude(pk=self.instance.pk)` de email). `__init__` precarga
`self.fields['cedula'].initial` leyendo `self.instance.profile` si
existe (`getattr(self.instance, 'profile', None)` — el `RelatedObjectDoesNotExist`
de Django hereda de `AttributeError`, así que `getattr` con default
funciona limpio para usuarios de los 12 preexistentes que no tienen
perfil). `save()` extendido con `UserProfile.objects.update_or_create(...)`
para crear el perfil la primera vez que un Administrador edita a un
usuario preexistente sin perfil, o actualizarlo si ya existía.

### 17.4 Templates — no hizo falta tocarlos

`register.html` (`{% for field in form %}`) y `user_form.html`
(`{{ form.as_p }}`) **ya iteran los campos del formulario de forma
genérica** — el campo `cedula` aparece automáticamente en el orden en
que se declaró en el form, sin ningún cambio de template. Se verificó
esto antes de tocar nada, en vez de asumir que hacía falta editar HTML.

### 17.5 Tests

**Bug real en tests preexistentes, encontrado y corregido antes de que
rompieran silenciosamente**: al agregar `cedula` como campo requerido en
`UserRegisterForm`, los tests ya existentes de `RegisterViewTests` y
`EmailUniquenessTests` que hacían `POST` a `/security/register/` (2
tests) o instanciaban `UserUpdateForm` esperando `is_valid()==True` (1
test) dejaron de pasar porque no mandaban `cedula` en los datos. Se
parchearon los 4 puntos del archivo que posteaban al registro/edición
agregando cédulas ficticias válidas (`1000000008`, `1000000016`, etc.,
generadas y confirmadas contra `validate_cedula_ec` antes de usarlas, no
inventadas a mano).

`CedulaUsuarioTests` (4 tests nuevos): formato inválido rechazado
(dígito verificador no coincide), cédula duplicada rechazada, cédula
válida y única aceptada (crea `User` + `UserProfile`, confirma
`user.profile.cedula`), `UserUpdateForm` no se autorrechaza al guardar
sin cambiar la cédula propia.

**Suite completa, comando exacto pedido**:
```
python manage.py test billing purchasing creditos_ventas creditos_compras security facturacion_electronica
Ran 92 tests in ~42s — OK
```
(88 tests previos + 4 nuevos de `CedulaUsuarioTests`; los 4 tests
preexistentes parcheados siguen contando en el total de `security`, no
se agregaron de más). Sin migraciones pendientes.

**Requerimiento de cédula — CERRADO.** No se tocó el tema de correo real
(sigue en pausa, sección 13.2).

---

## 18. Auditoría completa del proyecto + 2 fixes (sesión actual, 2026-07-17)

Auditoría honesta pedida por el usuario antes de seguir con features
nuevos: correr toda la suite, contrastar cada "completo/cerrado" del
HANDOFF contra el código real (no confiar en el documento), migraciones,
`check --deploy`, integridad de datos reales, y una revisión cruzada
puntual de los últimos 4 puntos grandes (email, PayPal, SRI, cédula).

**Nota sobre numeración**: el usuario citó secciones "5.5", "3.3" y
"2.3" en los pedidos de esta y la sesión anterior que **no existen en
este HANDOFF** (nunca hubo una sección 5.5 sobre SRI, ni 3.3 ni 2.3
sobre stock/RBAC). Los reclamos técnicos detrás de esos números sí se
verificaron y son reales (ver 18.4) — la numeración viene de un roadmap
externo que el usuario maneja aparte, no de este documento. Vale la pena
tenerlo presente si se retoma: **no asumir que un número de sección
citado existe acá sin buscarlo primero**.

### 18.1 Resultado de la auditoría (íntegro, sin cambios de código en ese momento)

- Suite completa: **92/92 tests verdes** (`-v 2`, sin ningún skip/
  amarillo), ~43s, nada anómalo.
- **Hallazgo no documentado antes**: `purchasing/tests.py` **no existe
  como archivo** (no es solo "vacío" como decía la sección 8) —
  `billing`/`purchasing` aportan 0 tests de los 92.
- Migraciones: sin pendientes, todas aplicadas.
- `check --deploy`: 8 warnings, todos esperables para un proyecto
  académico con `DEBUG=True` — sin cambios.
- Integridad de datos: sin emails ni cédulas duplicadas.
- Índice `UNIQUE` de email: confirmado **en disco** vía
  `sqlite_master`, no solo migración marcada como aplicada.
- PayPal manual: confirmado con el test HTTP real existente, sin
  regresión.
- SRI: generación de comprobante para Invoice (tipo `01`) y Purchase
  (tipo `03`) verificada manualmente por shell, ambos sin error, con
  rollback limpio.

**Los 2 hallazgos reales que salieron de la auditoría y se corrigieron
en esta misma sesión** (detalle en 18.2 y 18.3):
1. `UserUpdateForm.cedula` bloqueaba la edición de los 12 usuarios
   preexistentes sin `UserProfile`.
2. Datos de prueba reales mezclados en `dbA1.sqlite3` (usuario y
   comprobante creados manualmente por el usuario probando la app en el
   navegador, con el `runserver` corriendo en segundo plano desde hace
   varias sesiones).

### 18.2 Fix — `UserUpdateForm.cedula` ahora es opcional

**Causa raíz**: al implementar el punto 17, `cedula` se declaró como
`forms.CharField(...)` sin `required=False` en `UserUpdateForm`. Django
hace `CharField` obligatorio por default, así que cualquier edición de
un usuario sin `UserProfile` (los 12 preexistentes) fallaba la
validación exigiendo una cédula, aunque el Administrador solo quisiera
tocar `is_active` o el email.

**Reproducido con un test ANTES de aplicar el fix** (pedido explícito
del usuario, para confirmar que el test realmente detecta el bug):
`test_user_update_form_permite_editar_usuario_sin_perfil_sin_cedula` —
edita a un usuario sin perfil, sin mandar `cedula`, esperando
`is_valid()==True`. Corrido antes del fix: **`FAIL`**,
`cedula: Este campo es obligatorio.`. Corrido después: **`ok`**.

**Fix** (`security/forms.py`, `UserUpdateForm`):
```python
cedula = forms.CharField(
    max_length=10, label='Cédula', required=False, validators=[validate_cedula_ec],
    widget=forms.TextInput(attrs={'class': 'form-control'}),
    help_text='Opcional si el usuario todavía no tiene cédula registrada.',
)
```
`clean_cedula()`: si el valor viene vacío, retorna sin validar formato
ni unicidad (early return). `save()`: si `cedula` viene vacío, **no
toca `UserProfile` para nada** — no crea uno con cédula en blanco ni
pisa uno existente. Si sí viene un valor, se comporta exactamente igual
que antes (formato + unicidad + `update_or_create`).

**Decisión confirmada explícitamente por el usuario**: `UserRegisterForm.cedula`
**sigue obligatoria** para cuentas nuevas — solo se relajó
`UserUpdateForm` (edición). Criterio: es un dato que se puede pedir
desde el inicio del alta sin fricción real; la edición tiene que
convivir con datos históricos que nunca lo tuvieron. Sin cambios en
`UserRegisterForm`.

**Test de regresión** (pedido explícito): `test_user_update_form_sigue_validando_unicidad_si_se_da_cedula`
— confirma que si SÍ se manda una cédula que ya usa otro usuario, se
sigue rechazando igual que antes; el fix no debilitó la unicidad, solo
la hizo condicional a que el valor no esté vacío.

`security/tests.py`: **2 tests nuevos** en `CedulaUsuarioTests` (pasó de
27 a 29 tests en `security`).

### 18.3 Limpieza de datos de prueba en `dbA1.sqlite3` (BD real, no la de tests)

**Verificado antes de borrar nada** (instrucción explícita del usuario:
detenerse si algo quedaba vinculado): ningún modelo del proyecto tiene
FK hacia `User` salvo `UserProfile` (`on_delete=CASCADE`, se borra solo
al borrar el usuario) — no hay `Invoice`/`Purchase`/`PagoCuota*` con
referencia a "creado por", así que borrar al usuario no dejaba nada
huérfano. Único rastro adicional: una sesión activa de ese usuario en
`django_session` (no es una relación de datos, pero se limpió igual por
prolijidad).

**Borrado** (vía `manage.py shell`, con verificación de `pk`+`username`
exacta antes de cada `delete()`):
- Sesión activa del usuario `Axsus2203` (`django_session`).
- `ComprobanteElectronico` pk=1 (`BORRADOR`, sobre la Factura
  `FAC-000024`) — se verificó el estado y la factura asociada antes de
  borrar.
- Usuario `Axsus2203` (pk=13) — su `UserProfile` se borró en cascada
  automáticamente.

**Verificado después**: 12 usuarios (los originales, ninguno de más), 0
`UserProfile`, 0 `ComprobanteElectronico`, y `FAC-000024` **sigue
existiendo intacta** (solo se borró el comprobante hijo, no la factura).

**Origen de estos datos, para que quede registrado**: no eran basura de
pruebas automatizadas (esas corren en una BD de test aislada en
memoria, nunca tocan `dbA1.sqlite3`) — el `runserver` quedó corriendo en
segundo plano desde hace varias sesiones, y los timestamps (usuario
registrado 2026-07-17 06:11, comprobante creado 05:56) muestran que fue
el usuario probando la app manualmente en el navegador. Si se sigue
usando el `runserver` de fondo para probar cosas a mano, esto puede
volver a pasar — no es un bug del sistema, es simplemente que la BD de
desarrollo también acumula uso real.

### 18.4 Deuda técnica confirmada — auditada, decisión consciente de NO tocar todavía

Los siguientes 4 puntos se verificaron como reales en esta auditoría,
pero el usuario decidió **no corregirlos en esta sesión** — quedan
anotados para que quede como decisión consciente, no como algo que se
pasó por alto:

1. **Cero tests de RBAC en `billing`/`purchasing`/`creditos_ventas`/
   `creditos_compras`**: confirmado con grep — ninguna mención de
   `group_required`/`GroupRequiredMixin`/nombres de rol en
   `creditos_ventas/tests.py` ni `creditos_compras/tests.py`; `billing`
   y `purchasing` no tienen tests en absoluto. Las restricciones de rol
   de la sección 12.5 (`CATALOGO_COMPRAS`/`VENTAS`) nunca se probaron
   con un test automatizado, solo a mano en su momento.
2. **`purchasing/tests.py` no existe como archivo** (no es solo un
   boilerplate vacío como sugería la sección 8) — cosmético/documentación,
   no bloqueante.
3. **Umbrales de stock hardcodeados**: confirmado en
   `billing/Templates/billing/product_list.html` líneas 179/181 —
   `{% if item.stock <= 5 %}` / `{% elif item.stock <= 15 %}`, números
   mágicos en el template en vez de una constante en `settings.py`
   (mismo patrón que `TASA_MORA_DESCUENTO_MENSUAL`/`PAGO_MINIMO_CUOTA`).
4. **Hueco de RBAC de lectura abierta** (sección 13.1): sigue exactamente
   igual — decisión ya pospuesta a propósito en su momento, no cambió
   nada desde entonces.

### 18.5 Suite final

```
python manage.py test billing purchasing creditos_ventas creditos_compras security facturacion_electronica
Ran 94 tests in ~43s — OK
```
(92 tests previos + 2 nuevos del fix de `UserUpdateForm.cedula`). Sin
migraciones pendientes.

**Auditoría — CERRADA, ambos hallazgos corregidos.** Deuda técnica de
18.4 queda pendiente por decisión consciente, no por omisión. No se
tocó el tema de correo real (sigue en pausa, sección 13.2).

---

## 19. Inmutabilidad de Invoice/Purchase ya PAGADA — hallazgo crítico de la auditoría contra el caso de estudio original (sesión actual, 2026-07-17)

Cierra el hallazgo 🔴 más grave de la auditoría contra la especificación
original de la cátedra (turno anterior de esta misma sesión): **no había
ninguna validación que impidiera modificar el contenido financiero de
una `Invoice`/`Purchase` ya `PAGADA`**, ni por ORM directo ni por Django
Admin (`InvoiceAdmin`/`PurchaseAdmin` las exponían completas y
editables).

### 19.1 Investigación previa (antes de tocar código)

- **Nombres de campo confirmados en el modelo real** (el enunciado
  original decía "iva"/"cliente"/"proveedor", que no son los nombres
  reales): `Invoice` → `numero`, `customer` (no "cliente"), `subtotal`,
  `tax` (no "iva"), `total`, `tipo_pago`. `Purchase` → `numero`,
  `supplier` (no "proveedor"), `subtotal`, `tax`, `total`, `tipo_pago`.
- **Cómo llama `services.py` a `.save()` hoy** (confirmado con grep
  antes de decidir dónde poner el chequeo): `creditos_ventas/services.py`
  y `creditos_compras/services.py` usan `save(update_fields=[...])`
  parcial en varios puntos, y **`F('saldo') - valor` sobre `cuota.saldo`
  y `factura.saldo`/`compra.saldo`** — pero `saldo` **no está** en la
  lista de campos a congelar (el usuario no lo pidió, y de hecho
  `registrar_pago` ya rechaza cualquier pago sobre una factura/compra
  con `estado=='PAGADA'` desde antes, así que `saldo` nunca cambia
  después de PAGADA bajo el flujo normal). Ninguno de los 6 campos
  inmutables (`numero`/`customer_id`/`subtotal`/`tax`/`total`/`tipo_pago`
  para `Invoice`, ídem con `supplier_id` para `Purchase`) se toca nunca
  con `F()` en `services.py` — seguro comparar valores Python directos
  sin preocuparse por expresiones sin resolver.
- Confirmado que el `save()` de ambos modelos **no llama a
  `full_clean()`** — por eso el chequeo se puso directo en `save()`, no
  en `clean()` (que `services.py` nunca invoca).

### 19.2 Diseño de la solución

**Condición exacta pedida por el usuario, implementada literal**: si el
registro **ya existía en BD** (`self.pk` truthy) y su `estado` en BD
**antes de este save** era `'PAGADA'`, y alguno de los campos de
`CAMPOS_INMUTABLES_SI_PAGADA` difiere entre el valor en memoria (`self`)
y el valor que hay en BD, se rechaza con `ValidationError` (mismo tipo
de excepción que usa todo `services.py`, no se inventó una excepción
custom nueva). La transición `PENDIENTE→PAGADA` no se ve afectada porque
en **ese mismo save** el `estado` leído de BD todavía es `PENDIENTE` —
el chequeo lee el estado **anterior**, nunca el que se le está por
asignar ahora.

`billing/models.py`, `Invoice`:
```python
CAMPOS_INMUTABLES_SI_PAGADA = ['numero', 'customer_id', 'subtotal', 'tax', 'total', 'tipo_pago']

def save(self, *args, **kwargs):
    if self.pk:
        anterior = Invoice.objects.filter(pk=self.pk).values(
            'estado', *self.CAMPOS_INMUTABLES_SI_PAGADA
        ).first()
        if anterior and anterior['estado'] == 'PAGADA':
            for campo in self.CAMPOS_INMUTABLES_SI_PAGADA:
                if getattr(self, campo) != anterior[campo]:
                    raise ValidationError('No se puede modificar una factura ya pagada.')
    is_new = self.pk is None
    super().save(*args, **kwargs)
    if is_new and not self.numero:
        self.numero = f'FAC-{self.pk:06d}'
        super().save(update_fields=['numero'])
```
`purchasing/models.py`, `Purchase`: idéntico, con `supplier_id` en vez
de `customer_id` y mensaje "...una compra ya pagada.".

**Segunda capa — `get_readonly_fields()` en ambos `ModelAdmin`**
(`billing/admin.py`/`purchasing/admin.py`): si `obj.estado == 'PAGADA'`,
**todos** los campos del modelo (no solo los 6 inmutables) quedan
readonly — deliberadamente más estricto que el `save()` del modelo, para
que el admin funcione como pantalla de consulta pura sobre una
factura/compra cerrada, no de edición parcial. **Nota: las líneas de
detalle (`InvoiceDetailInline`/`PurchaseDetailInline`) no se tocaron** —
el pedido fue específicamente sobre `InvoiceAdmin`/`PurchaseAdmin`, no
sobre los inlines; sigue siendo técnicamente posible agregar/quitar
líneas de detalle de una factura pagada vía el admin. Si se retoma esto,
vale la pena cerrar también ese hueco.

### 19.3 Tests — reproducción del bug primero, mismo patrón que el hallazgo de cédula (sección 18.2)

`billing/tests.py` **estaba vacío** (boilerplate) — se escribió desde
cero. `purchasing/tests.py` **no existía como archivo** (confirmado en
la auditoría, sección 18.4 punto 2) — se creó por primera vez en esta
sesión.

`InvoiceInmutablePagadaTests`/`PurchaseInmutablePagadaTests` (6 tests
cada uno, espejados):
1. `test_no_se_puede_modificar_total_de_...` — **corrido ANTES del fix,
   falló en rojo** (`AssertionError: ValidationError not raised`,
   confirmado literal), corrido después del fix, verde.
2. Resto de campos inmutables (`subtotal`, `tax`, `tipo_pago`,
   `customer`/`supplier`, `numero`) — cada uno probado por separado.
3. Una factura/compra `PENDIENTE` se sigue editando sin ningún problema.
4. Transición `PENDIENTE→PAGADA` vía `CONTADO` sigue sin excepción.
5. Transición `PENDIENTE→PAGADA` vía pago completo de cuotas (`CREDITO`)
   sigue sin excepción.
6. Test del admin real, vía `Client().post()` al `change view` — confirma
   que los campos no aparecen como `<input name="...">` en el HTML (son
   readonly) y que un `POST` con valores distintos no modifica nada en
   BD.

**Suite completa, comando exacto pedido**:
```
python manage.py test billing purchasing creditos_ventas creditos_compras security facturacion_electronica
Ran 106 tests in ~47s — OK
```
(94 tests previos + 6 de `InvoiceInmutablePagadaTests` + 6 de
`PurchaseInmutablePagadaTests`). Sin migraciones nuevas (el fix es solo
`save()`/`ModelAdmin`, no cambia el schema).

**Efecto colateral positivo, no buscado a propósito pero real**: esta
sesión también resuelve parcialmente dos puntos de deuda técnica de la
sección 18.4 — `billing`/`purchasing` ahora **sí tienen tests reales**
(antes: 0 en ambos). Sigue pendiente la deuda de tests de RBAC
específicos (`group_required`/roles) en esas mismas apps — lo que se
agregó acá es sobre inmutabilidad, no sobre permisos.

**Hallazgo crítico de la auditoría — CERRADO.** Sesión terminada acá,
según lo pedido. No se tocó el tema de correo real (sigue en pausa,
sección 13.2).

---

## 20. Bugs reportados de `registrar_pagos` (formset) + fecha de pago inmutable en UI (sesión actual, 2026-07-17)

### 20.1 Investigación de los 2 bugs reportados — NO reproducidos

El dueño del proyecto reportó, probando manualmente en el navegador con
`FAC-000024` (3 cuotas de $440.83, saldo $1322.49): (1) marcar el
checkbox de una sola cuota y enviar "Registrar pagos" terminaba pagando
las 3, y (2) "Pagar con PayPal" rechazaba el formset con "Revisa los
datos del formulario". Sospecha a verificar: `_parsear_formset_a_pagos_data`
no estaría filtrando por el checkbox `pagar`.

**Investigado a fondo, con reproducción real (no solo lectura de
código), en varios escenarios**:
- Con el checkbox de una sola cuota marcado y el **valor exacto de
  liquidación** ($431.72 — la cuota real de `FAC-000024` no está
  vencida, aplica descuento por pronto pago, ver sección 7.2) en esa
  fila, dejando las otras 2 filas sin marcar (con su valor pre-llenado
  de $440.83 intacto, tal como lo enviaría un navegador real): **se
  pagó solo 1 cuota**, las otras 2 quedaron `PENDIENTE` con saldo
  intacto, y redirigió correctamente a `comprobante_lote`.
- Mismo escenario contra `pagar_con_paypal`: avanzó sin error a
  `paypal_login`.
- Cero checkboxes marcados: mensaje correcto "No seleccionaste ninguna
  cuota para pagar." en ambos flujos, no el mensaje de error reportado.

**Conclusión, confirmada con el usuario antes de seguir**: la sospecha
de causa raíz **no se confirma** — `_parsear_formset_a_pagos_data`
filtra correctamente por `pagar` en todos los escenarios probados. Ni
BUG 1 ni BUG 2 se lograron reproducir tal como se describieron. Se
decidió explícitamente **no seguir investigando esto** y documentarlo
como no reproducido, en vez de aplicar un fix a ciegas sobre un bug sin
causa raíz confirmada.

**Lo que sí se encontró, real y distinto** (probablemente la explicación
más plausible de lo que vio el usuario): el `valor` pre-llenado por
default en cada fila es `cuota.saldo` — pero para una cuota que **no**
está vencida todavía, `monto_para_liquidar_hoy()` es **menor** que
`saldo` por el descuento de pronto pago (comportamiento documentado
desde la sección 7.2). Enviar el valor pre-llenado sin ajustarlo dispara
un rechazo de negocio legítimo ("no puede superar el monto de
liquidación"), no una corrupción de datos ni un bug de formset.

**Verificación de `dbA1.sqlite3` (BD real, pedido explícito del
usuario)**: `FAC-000024` sigue con sus 3 cuotas `PENDIENTE`, saldo
`$1322.49` intacto, **cero `PagoCuotaVenta` registrados** para esa
factura. Nada se corrompió — no hizo falta revertir ni corregir ningún
dato real.

### 20.2 Fecha de pago — de "editable pero inerte" a "readonly + defensa en profundidad"

Problema real de UX/confiabilidad (distinto de los bugs de 20.1, sí
confirmado): el datepicker de cada fila del formset **sí permitía
seleccionar** visualmente cualquier fecha, aunque `services.registrar_pago`
la ignora completamente y siempre usa `timezone.localdate()` (decisión
de una sesión anterior, sección 7.1/7.3) — engañoso, parecía una opción
real que no hacía nada.

**Fix, en ambos módulos**:
1. `PagoCuotaForm`/`PagoCuotaCompraForm` (`creditos_ventas/forms.py`,
   `creditos_compras/forms.py`): el widget del campo `fecha` ahora tiene
   `'readonly': 'readonly'` — ya no se puede editar desde el navegador,
   sigue pre-llenado con `timezone.localdate()` vía el `initial` que ya
   armaba la vista (`registrar_pagos`, sin cambios ahí). **Efecto
   colateral encontrado y corregido de paso**: el widget no tenía
   `format='%Y-%m-%d'` explícito, así que un `<input type="date">`
   (que exige ISO en el atributo `value`) se estaba renderizando en
   `DD/MM/YYYY` (formato `es-ec`) — técnicamente inválido para ese tipo
   de input HTML5. Se agregó `format='%Y-%m-%d'` al widget.
2. **Defensa en profundidad** en `_parsear_formset_a_pagos_data`
   (compartida entre el submit manual y el staging de PayPal, así que
   el fix cubre ambos flujos con un solo cambio): si una fila marcada
   para pagar trae una `fecha` distinta a `timezone.localdate()`, se
   rechaza con `'La fecha de pago debe ser la fecha actual.'` en vez de
   ignorarla en silencio como antes — cubre un POST manual armado
   saltándose la UI (readonly del navegador no protege contra eso).
   Sin `fecha` en el POST, sigue funcionando igual que siempre (el
   campo es `required=False`).
3. El staging/confirmación de PayPal (`pagar_con_paypal`) reusa la
   misma función, así que queda cubierto automáticamente — la pantalla
   de confirmación de PayPal (`paypal_confirmar`) nunca expuso `fecha`
   en primer lugar (el `pagos_data` guardado en sesión solo lleva
   `cuota_id`/`valor`/`observacion`, confirmado en el código).

**Tests nuevos** (`FechaPagoInmutableTests`, 5 por módulo, 10 en total,
espejados): fecha pasada rechazada, fecha futura rechazada, fecha de
hoy explícita funciona normal, sin fecha en el POST funciona normal,
mismo rechazo en el staging de PayPal.

### 20.3 Incidente operativo durante la sesión (documentado por transparencia)

Durante la investigación de 20.1 se corrió `git stash` para una prueba
rápida, sin considerar que **ninguna parte de esta sesión estaba
commiteada todavía** (nada se ha commiteado desde `2557d8a`) — esto
revirtió momentáneamente todos los archivos trackeados modificados por
esta sesión (no los directorios nuevos `security/`/`facturacion_electronica/`,
que son *untracked* y `git stash` no los toca por default). **Se
detectó y restauró de inmediato con `git stash pop`**, confirmado
`Dropped refs/stash@{0}` sin conflictos, y se verificó explícitamente
que los cambios de fecha/formset seguían intactos antes de continuar.
Ningún trabajo se perdió, pero queda anotado como recordatorio: con
tanto trabajo sin commitear acumulado, cualquier comando de git que
toque el árbol de trabajo (`stash`, `checkout`, `reset`) es
particularmente riesgoso en este proyecto ahora mismo.

### 20.4 Suite final

```
python manage.py test billing purchasing creditos_ventas creditos_compras security facturacion_electronica
Ran 116 tests in ~48s — OK
```
(106 tests previos + 10 nuevos de `FechaPagoInmutableTests`). Sin
migraciones pendientes.

**Cerrado**: fecha de pago inmutable en UI + defensa en profundidad.
**No reproducido, documentado como tal**: los 2 bugs de formset
reportados — no se aplicó ningún fix sobre ellos porque no se confirmó
ninguna causa raíz real. No se tocó el tema de correo real (sigue en
pausa, sección 13.2).
