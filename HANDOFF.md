# HANDOFF — Sales Project (TecnoStock S.A.)

> Documento de traspaso técnico. Escrito para que otra IA o desarrollador
> entienda el proyecto completo sin tener que releer todo el código fuente.
> Fecha de la auditoría: 2026-07-13.

---

## 1. Qué es esto

Sistema de facturación/ERP simplificado para una empresa ficticia
("TecnoStock S.A.", ver el PDF de facturas), hecho en **Django 6.0.6**,
orientado al mercado ecuatoriano (validación de cédula/RUC, IVA 15%,
zona horaria Guayaquil). Es un proyecto de aprendizaje/portafolio, no un
sistema en producción: `DEBUG=True`, `SECRET_KEY` hardcodeada, SQLite,
sin variables de entorno.

Ubicación real del código Django: **`sales_project/sales_project/`**
(hay dos carpetas anidadas con el mismo nombre — ver sección 4, es la
trampa #1 para cualquiera que llegue nuevo).

## 2. Stack

| Capa | Tecnología |
|---|---|
| Backend | Django 6.0.6 (Python 3.13) |
| DB | SQLite3 (`dbA1.sqlite3`) — **está commiteada en git** |
| Frontend | Bootstrap 5.3.0 vía CDN + Django Templates |
| Auth | `django.contrib.auth` (login/signup propios) |
| PDF | ReportLab |
| Excel | openpyxl |
| Debug | `django-debug-toolbar`, `django-extensions` (declarados pero mal instalados, ver Hallazgo #1) |
| Locale | `es-ec`, `America/Guayaquil` |

## 3. Apps Django y su rol

- **`billing`** — app principal: Brand, ProductGroup, Supplier, Product,
  Customer, CustomerProfile, Invoice, InvoiceDetail. CRUD completo +
  dashboard + búsqueda global + exportación PDF/Excel de productos.
- **`purchasing`** — módulo de compras a proveedores. Reutiliza
  `Supplier` y `Product` de `billing` (no duplica catálogo). Purchase +
  PurchaseDetail, formset maestro-detalle, PDF/Excel, reporte de costo
  promedio.
- **`shared`** — utilidades cross-app: validador de cédula/RUC
  ecuatoriano, decorador de auditoría por logging, `StaffRequiredMixin`,
  `ExportMixin` (PDF/Excel genérico para CBVs).
- **`config`** — settings/urls/wsgi/asgi del proyecto.

Diagrama de relaciones y tablas de campos completas: ver
`sales_project/README.md` (ya está muy detallado, no lo dupliques).

## 4. Trampas de estructura (leer antes de tocar nada)

1. **Doble anidación**: el repo raíz (`sales_project/`) tiene un
   `README.md` y un `requirements.txt` propios, y DENTRO otra carpeta
   `sales_project/` que es el proyecto Django real (con su propio
   `manage.py`, `requirements.txt` y `README.md`). Para correr el
   servidor hay que `cd` a la carpeta interna:
   ```
   cd sales_project/sales_project
   python manage.py runserver
   ```
   (Ya me pasó a mí en esta sesión: ejecuté `manage.py` desde la raíz y
   falló con "No such file or directory".)

2. **Dos `requirements.txt` distintos y desincronizados**:
   - Raíz (`/requirements.txt`): incluye `django-debug-toolbar`,
     `django-extensions`, **Flask**, **Werkzeug**, `blinker`,
     `click`, `Jinja2`, `itsdangerous` — dependencias que no tienen
     nada que ver con este proyecto Django (parecen arrastradas de
     otro entorno/tutorial).
   - Interno (`/sales_project/requirements.txt`): más limpio, sin
     Flask, pero **tampoco** incluye `django-debug-toolbar` aunque
     `settings.py` lo declara en `INSTALLED_APPS`.
   Antes de tocar dependencias, decidir cuál es la fuente de verdad y
   fusionar/limpiar.

3. **Entorno virtual**: hay una carpeta `sales_project/ent_sales/`
   (venv real, con Python 3.13 embebido) — correctamente ignorada por
   `.gitignore` (`/ent_sales/`, `/venv/`), no está en git.

## 5. Hallazgos de la auditoría (ordenados por severidad)

### 🔴 Alto

1. **La base de datos SQLite (`dbA1.sqlite3`) está versionada en git**
   (`git ls-files` la lista). Contiene datos reales de prueba
   (usuarios, hashes de contraseña, clientes con DNI, etc.) que quedan
   en el historial para siempre. El `.gitignore` tiene la línea que la
   excluiría comentada: `# *.sqlite3`. Recomendación: descomentar esa
   línea, hacer `git rm --cached dbA1.sqlite3`, y si el repo se va a
   compartir/publicar, considerar limpiar el historial.

2. **`SECRET_KEY` hardcodeada y `DEBUG=True`** en `config/settings.py`.
   Aceptable en desarrollo, pero si esto se despliega alguna vez hay
   que moverlo a variables de entorno antes que nada. El propio
   `README.md` ya documenta esto en "Consideraciones para Producción",
   así que es una decisión consciente, no un descuido — pero conviene
   confirmarlo antes de cualquier deploy.

3. **Permisos inconsistentes en borrado**: `invoice_delete` y
   `purchase_delete` son FBV protegidas solo con `@login_required`
   (cualquier usuario autenticado, no solo staff, puede borrar
   facturas/compras — y el borrado de compras revierte stock
   automáticamente). El resto de los `DeleteView` (Brand, Group,
   Supplier, Product, Customer) sí usan `StaffRequiredMixin`. Esto está
   **documentado explícitamente** en el README como diferencia
   FBV/CBV, así que parece intencional para esta entrega — pero es la
   primera pregunta que haría un revisor de seguridad.

### 🟡 Medio

4. **`debug_toolbar` en `INSTALLED_APPS` pero sin su middleware**
   (`config/settings.py` lista la app en `INSTALLED_APPS` pero
   `MIDDLEWARE` no incluye
   `debug_toolbar.middleware.DebugToolbarMiddleware`). Django lo marca
   como warning (`debug_toolbar.W001`) en cada arranque — lo vimos al
   levantar el servidor en esta sesión. O se termina de instalar bien
   (middleware + `INTERNAL_IPS`) o se saca de `INSTALLED_APPS`.

5. **`billing/tests.py` está vacío** (solo el boilerplate de Django).
   No hay tests para: validador de cédula/RUC (lógica no trivial con
   varias ramas), cálculo de subtotales/IVA, reversión de stock en
   compras/facturas, ni permisos. Dado que hay lógica de negocio real
   (dígito verificador ecuatoriano, `F()` para concurrencia de stock),
   esto es lo primero que yo priorizaría si el objetivo es
   robustecer el proyecto.

6. **Duplicación de `ExportMixin` / lógica de exportación**: la vista
   `ProductListView` en `billing/views.py` reimplementa manualmente
   `get_export_data()` (con la misma lógica de "campo con punto para
   relaciones") en vez de heredarla completa de `shared/mixins.py:ExportMixin`,
   que ya la define. Redundancia menor, no bug.

7. **`shared/decorators.py` usa `print()` además de `logger.info()`**
   para las auditorías — el `print` no tiene sentido en un logger de
   auditoría real (no queda en ningún archivo de log, se pierde en
   consola). Si se corre con Gunicorn/servidor real, ese `print` no
   sirve para nada.

8. **Filtros numéricos en `ProductListView.get_queryset()` usan
   `except:` desnudo** (sin especificar excepción) al parsear
   `min_price`/`max_price`/`min_stock`/`max_stock`. Funciona, pero
   oculta cualquier error inesperado, no solo `ValueError`/
   `InvalidOperation`.

### 🟢 Bajo / observaciones

9. Solo hay **1 commit** en el historial (`74a7803` — "Checkpoint:
   modulo purchasing completo..."), es decir todo el proyecto llegó
   como un solo squash. No hay historial incremental que consultar con
   `git blame`/`git log` para entender decisiones pasadas.

10. El módulo `purchasing` no tiene `tests.py` en absoluto (ni el
    boilerplate).

11. Migraciones de `billing` van hasta `0005` (incluye migraciones
    correctivas: `alter_customer_dni`, `product_image`,
    `alter_brand_description_alter_brand_is_active_and_more`,
    `add_name_validators_to_customer` — indican iteración real sobre
    el modelo). `purchasing` solo tiene `0001_initial` — módulo más
    reciente y estable desde que se creó.

12. El README del proyecto (`sales_project/README.md`) es
    **extensivo y confiable** — documenta modelos, URLs, permisos,
    validadores, admin y configuración con detalle. Prioriza leerlo a
    él antes que inferir del código para todo lo que no sea lógica
    fina (allí puede haber desactualizaciones puntuales, ej. la tabla
    de migraciones solo llega a `0002`, faltan `0003`-`0005`).

## 6. Cómo correr el proyecto

```bash
cd sales_project/sales_project
python manage.py runserver
```
Servidor en `http://127.0.0.1:8000/`. La ruta `/` redirige (302) a
login si no hay sesión — comportamiento esperado, todas las vistas
requieren autenticación.

Para crear un usuario admin (acceso a `/admin/`):
```bash
python manage.py createsuperuser
```

## 7. Qué haría a continuación (sugerencias, no decisiones tomadas)

- Resolver la db versionada en git (hallazgo #1) — es lo único que
  yo trataría como urgente de verdad, el resto es normal para un
  proyecto de portafolio en curso.
- Unificar los dos `requirements.txt` y decidir si Flask/Werkzeug
  deben seguir ahí (probablemente no).
- Escribir tests para `shared/validators.py:validate_cedula_ec` — es
  la pieza de lógica más "quisquillosa" del proyecto y la que más se
  beneficia de tests (muchas ramas: cédula natural / RUC público / RUC
  privado / dígito verificador).
- Decidir a propósito si `invoice_delete`/`purchase_delete` deben
  requerir staff (hoy no lo requieren) — está documentado pero vale la
  pena confirmarlo como decisión de producto, no solo como nota al
  pie.

## 8. Preferencias de quien pidió este audit

- Prefiere trabajar en español.
- Pidió explícitamente "detallitas" — este documento prioriza
  completitud y contexto sobre brevedad a propósito.
