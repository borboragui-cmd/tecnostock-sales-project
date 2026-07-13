# Sales Project - Sistema de Facturación

Sistema web de facturación y gestión de ventas desarrollado con Django, orientado al mercado ecuatoriano. Permite gestionar productos, clientes, proveedores y facturas desde un panel web con autenticación de usuarios.

---

## Tabla de Contenidos

- [Descripción General](#descripción-general)
- [Tecnologías](#tecnologías)
- [Requisitos Previos](#requisitos-previos)
- [Instalación](#instalación)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Modelos de Base de Datos](#modelos-de-base-de-datos)
- [Funcionalidades](#funcionalidades)
- [URLs y Endpoints](#urls-y-endpoints)
- [Autenticación y Permisos](#autenticación-y-permisos)
- [Utilidades Personalizadas](#utilidades-personalizadas)
- [Panel de Administración](#panel-de-administración)
- [Configuración](#configuración)

---

## Descripción General

Sales Project es un ERP/Sistema de Facturación web que centraliza la gestión de:

- Marcas y categorías de productos
- Catálogo de productos con stock
- Proveedores
- Clientes con validación de cédula/RUC ecuatoriano
- Emisión de facturas con cálculo automático de subtotales e impuestos
- Dashboard con estadísticas y alertas de bajo stock
- Auditoría de acciones de usuario

---

## Tecnologías

| Componente     | Tecnología               |
|----------------|--------------------------|
| Backend        | Django 6.0.6 (Python)    |
| Base de datos  | SQLite3                  |
| Frontend       | Bootstrap 5.3.0 (CDN)    |
| Templates      | Django Template Language |
| Autenticación  | Django Auth (built-in)   |
| Localización   | Español Ecuador (es-ec)  |

**Dependencias principales** (`requirements.txt`):
```
asgiref==3.11.1
Django==6.0.6
sqlparse==0.5.5
tzdata==2026.2
```

---

## Requisitos Previos

- Python 3.10 o superior
- pip

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd sales_project

# 2. Crear y activar entorno virtual
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Aplicar migraciones
python manage.py migrate

# 5. Crear superusuario (opcional, para acceder al admin)
python manage.py createsuperuser

# 6. Iniciar el servidor de desarrollo
python manage.py runserver
```

Acceder a `http://127.0.0.1:8000/`

---

## Estructura del Proyecto

```
sales_project/
├── config/                        # Configuración principal del proyecto Django
│   ├── settings.py                # Ajustes globales (BD, apps, auth, i18n)
│   ├── urls.py                    # Rutas raíz del proyecto
│   ├── wsgi.py                    # Punto de entrada WSGI (producción)
│   └── asgi.py                    # Punto de entrada ASGI (async)
│
├── billing/                       # App principal del sistema
│   ├── migrations/                # Historial de cambios en la BD
│   │   ├── 0001_initial.py        # Creación de todos los modelos
│   │   └── 0002_alter_customer_dni.py  # Añade validador al campo DNI
│   ├── Templates/billing/         # Plantillas HTML de la app
│   │   ├── base.html              # Plantilla base con navbar y layout
│   │   ├── home.html              # Dashboard principal
│   │   ├── *_list.html            # Vistas de listado (6 modelos)
│   │   ├── *_form.html            # Formularios crear/editar (6 modelos)
│   │   └── *_confirm_delete.html  # Confirmación de eliminación (6 modelos)
│   ├── admin.py                   # Configuración del panel admin
│   ├── apps.py                    # Configuración de la app
│   ├── forms.py                   # Formularios Django (SignUpForm, BrandForm)
│   ├── models.py                  # Modelos de base de datos (8 modelos)
│   ├── urls.py                    # Rutas de la app billing
│   ├── views.py                   # Vistas FBV y CBV
│   └── tests.py                   # Tests unitarios
│
├── purchasing/                    # App de compras a proveedores
│   ├── migrations/                # Migraciones de la app purchasing
│   ├── templates/purchasing/      # Plantillas HTML de la app
│   │   ├── purchase_list.html     # Listado con filtros por proveedor/fecha
│   │   ├── purchase_form.html     # Formulario maestro-detalle (formset)
│   │   ├── purchase_detail.html   # Detalle con botones PDF y Excel
│   │   ├── purchase_confirm_delete.html
│   │   └── purchase_report.html   # Reporte de costos promedio
│   ├── admin.py                   # PurchaseAdmin + PurchaseDetailInline (edición normal)
│   ├── apps.py
│   ├── forms.py                   # PurchaseForm + PurchaseDetailFormSet
│   ├── models.py                  # Purchase, PurchaseDetail (FK a billing)
│   ├── urls.py                    # Rutas de la app purchasing
│   └── views.py                   # CRUD + PDF (ReportLab) + Excel (openpyxl)
│
├── shared/                        # Utilidades reutilizables entre apps
│   ├── decorators.py              # Decorador de auditoría @audit_action
│   ├── mixins.py                  # StaffRequiredMixin para CBV
│   └── validators.py              # Validador de cédula/RUC ecuatoriano
│
├── templates/                     # Plantillas globales del proyecto
│   └── registration/
│       ├── login.html             # Página de inicio de sesión
│       └── signup.html            # Página de registro
│
├── dbA1.sqlite3                   # Base de datos SQLite3
├── manage.py                      # CLI de Django
└── requirements.txt               # Dependencias del proyecto
```

---

## Modelos de Base de Datos

El sistema cuenta con **8 modelos** organizados en torno al flujo de facturación:

### Brand (Marcas)

Representa las marcas de los productos.

| Campo         | Tipo            | Descripción                        |
|---------------|-----------------|------------------------------------|
| `id`          | BigAutoField    | Clave primaria                     |
| `name`        | CharField(100)  | Nombre único de la marca           |
| `description` | TextField       | Descripción opcional               |
| `is_active`   | BooleanField    | Estado activo/inactivo             |
| `created_at`  | DateTimeField   | Fecha de creación (auto)           |
| `updated_at`  | DateTimeField   | Última modificación (auto)         |

- Ordenado por: `name`
- Relaciones: OneToMany → `Product`

---

### ProductGroup (Grupos / Categorías)

Organiza los productos en categorías.

| Campo        | Tipo           | Descripción              |
|--------------|----------------|--------------------------|
| `id`         | BigAutoField   | Clave primaria           |
| `name`       | CharField(100) | Nombre único del grupo   |
| `is_active`  | BooleanField   | Estado activo/inactivo   |
| `created_at` | DateTimeField  | Fecha de creación (auto) |
| `updated_at` | DateTimeField  | Última modificación      |

- Ordenado por: `name`
- Relaciones: OneToMany → `Product`

---

### Supplier (Proveedores)

Registro de los proveedores de productos.

| Campo          | Tipo           | Descripción                 |
|----------------|----------------|-----------------------------|
| `id`           | BigAutoField   | Clave primaria              |
| `name`         | CharField(200) | Nombre del proveedor        |
| `contact_name` | CharField(100) | Nombre del contacto (opt.)  |
| `email`        | EmailField     | Correo electrónico (opt.)   |
| `phone`        | CharField(20)  | Teléfono (opt.)             |
| `address`      | TextField      | Dirección (opt.)            |
| `is_active`    | BooleanField   | Estado activo/inactivo      |
| `created_at`   | DateTimeField  | Fecha de creación (auto)    |
| `updated_at`   | DateTimeField  | Última modificación         |

- Ordenado por: `name`
- Relaciones: ManyToMany ↔ `Product`

---

### Product (Productos)

Catálogo de productos con precio y stock.

| Campo        | Tipo                | Descripción                           |
|--------------|---------------------|---------------------------------------|
| `id`         | BigAutoField        | Clave primaria                        |
| `name`       | CharField(200)      | Nombre del producto                   |
| `description`| TextField           | Descripción opcional                  |
| `brand`      | ForeignKey → Brand  | Marca (PROTECT al eliminar)           |
| `group`      | ForeignKey → Group  | Categoría (PROTECT al eliminar)       |
| `suppliers`  | ManyToManyField     | Proveedores asociados                 |
| `unit_price` | DecimalField(12,2)  | Precio unitario                       |
| `stock`      | IntegerField        | Unidades en stock (default: 0)        |
| `is_active`  | BooleanField        | Estado activo/inactivo                |
| `created_at` | DateTimeField       | Fecha de creación (auto)              |
| `updated_at` | DateTimeField       | Última modificación (auto)            |

- Alerta de bajo stock: `stock <= 5` (visible en dashboard)

---

### Customer (Clientes)

Registro de clientes con validación de identificación fiscal ecuatoriana.

| Campo        | Tipo           | Descripción                                    |
|--------------|----------------|------------------------------------------------|
| `id`         | BigAutoField   | Clave primaria                                 |
| `dni`        | CharField(13)  | Cédula (10 dígitos) o RUC (13 dígitos), único |
| `first_name` | CharField(100) | Nombres                                        |
| `last_name`  | CharField(100) | Apellidos                                      |
| `email`      | EmailField     | Correo electrónico (opt.)                      |
| `phone`      | CharField(20)  | Teléfono (opt.)                                |
| `address`    | TextField      | Dirección (opt.)                               |
| `is_active`  | BooleanField   | Estado activo/inactivo                         |
| `created_at` | DateTimeField  | Fecha de creación (auto)                       |
| `updated_at` | DateTimeField  | Última modificación                            |

- Ordenado por: `last_name`, `first_name`
- Propiedad calculada: `full_name` → `first_name + last_name`
- Validación: El campo `dni` aplica el validador `validate_cedula_ec`
- Relaciones: OneToOne → `CustomerProfile`, OneToMany → `Invoice`

---

### CustomerProfile (Perfil Extendido del Cliente)

Información fiscal y comercial adicional del cliente.

| Campo           | Tipo               | Opciones                                   |
|-----------------|--------------------|--------------------------------------------|
| `id`            | BigAutoField       | Clave primaria                             |
| `customer`      | OneToOneField      | Cliente asociado (CASCADE)                 |
| `taxpayer_type` | CharField(choices) | `final`, `ruc`, `rise`                     |
| `payment_terms` | CharField(choices) | `cash`, `credit_15`, `credit_30`, `credit_60` |
| `credit_limit`  | DecimalField(12,2) | Límite de crédito (default: 0)             |
| `notes`         | TextField          | Notas adicionales (opt.)                   |

---

### Invoice (Facturas)

Cabecera de cada factura emitida.

| Campo          | Tipo                    | Descripción                      |
|----------------|-------------------------|----------------------------------|
| `id`           | BigAutoField            | Clave primaria                   |
| `customer`     | ForeignKey → Customer   | Cliente (PROTECT al eliminar)    |
| `invoice_date` | DateTimeField           | Fecha de emisión (auto)          |
| `subtotal`     | DecimalField(12,2)      | Subtotal antes de impuestos      |
| `tax`          | DecimalField(12,2)      | Monto de impuestos               |
| `total`        | DecimalField(12,2)      | Total de la factura              |
| `is_active`    | BooleanField            | Estado activo/inactivo           |

- Ordenado por: `-invoice_date` (más reciente primero)
- Relaciones: OneToMany → `InvoiceDetail`

---

### InvoiceDetail (Líneas de Factura)

Detalle de cada producto incluido en una factura.

| Campo        | Tipo                  | Descripción                            |
|--------------|-----------------------|----------------------------------------|
| `id`         | BigAutoField          | Clave primaria                         |
| `invoice`    | ForeignKey → Invoice  | Factura (CASCADE al eliminar)          |
| `product`    | ForeignKey → Product  | Producto (PROTECT al eliminar)         |
| `quantity`   | IntegerField          | Cantidad (default: 1)                  |
| `unit_price` | DecimalField(12,2)    | Precio unitario al momento de la venta |
| `subtotal`   | DecimalField(12,2)    | Calculado automáticamente en `save()`  |

- `subtotal` se calcula automáticamente: `quantity × unit_price`

---

### Diagrama de Relaciones

```
Brand ─────────────────────────── Product ──── ManyToMany ──── Supplier
                                     │
ProductGroup ───────────────────────┘
                                     │
                               InvoiceDetail
                                     │
Customer ──── CustomerProfile   Invoice ──────────────────── Customer
                │
                └─── Invoice (OneToMany)

Purchase ──── ForeignKey ──── Supplier (PROTECT)
   │
PurchaseDetail ──── ForeignKey ──── Product (PROTECT)
(Purchase → PurchaseDetail es OneToMany con CASCADE)
```

---

## Funcionalidades

### Dashboard (`/`)

Vista principal con:
- Contador total de Marcas, Productos, Clientes y Facturas
- Tabla de las últimas 5 facturas emitidas
- Alerta de productos con stock igual o menor a 5 unidades

### Gestión de Marcas (`/brands/`)

CRUD completo con auditoría de acciones mediante `@audit_action`.

### Gestión de Grupos / Categorías (`/groups/`)

CRUD completo para organizar productos.

### Gestión de Proveedores (`/suppliers/`)

CRUD completo con datos de contacto.

### Gestión de Productos (`/products/`)

CRUD completo. Permite asignar marca, grupo, múltiples proveedores, precio y stock.

### Gestión de Clientes (`/customers/`)

CRUD completo con:
- Validación de cédula ecuatoriana (10 dígitos) y RUC (13 dígitos)
- Perfil extendido con tipo de contribuyente y términos de pago

### Gestión de Facturas (`/invoices/`)

- Crear factura con líneas de detalle
- Cálculo automático de subtotal por línea
- Vista de listado y eliminación (no se permite edición post-emisión)
- Exportación a **PDF** (ReportLab) en `/invoices/<pk>/pdf/`

### Módulo de Compras (`/purchases/`)

Gestiona las órdenes de compra a proveedores. Reutiliza directamente los modelos `Supplier` y `Product` de `billing` (sin duplicar tablas).

- Crear compra con múltiples líneas de producto (formset: hasta N productos por orden)
- Cálculo automático: subtotal por línea → subtotal global → IVA 15 % → total
- Al guardar: stock de cada producto se incrementa con `F('stock') + quantity` (safe ante concurrencia)
- Al eliminar: stock se revierte con `F('stock') - quantity`, todo dentro de `transaction.atomic()`
- Filtros en listado: por proveedor, rango de fechas, año
- Exportación a **PDF** por orden (`/purchases/<pk>/pdf/`)
- Exportación a **Excel** por orden (`/purchases/<pk>/excel/`) y listado completo (`/purchases/export/excel/`)
- Reporte de costos promedio por producto (`/purchases/report/`) con `Avg`, `Sum`, `Count`
- `UniqueConstraint` por `(supplier, document_number)` para evitar duplicados

### Autenticación

- Registro de nuevos usuarios (`/signup/`)
- Login / Logout (`/accounts/login/`, `/accounts/logout/`)
- Todas las vistas requieren autenticación
- Eliminación de registros requiere permiso de staff

---

## URLs y Endpoints

### Raíz del Proyecto (`config/urls.py`)

| Prefijo       | Destino              |
|---------------|----------------------|
| `/admin/`     | Panel de admin       |
| `/accounts/`  | Auth de Django       |
| `/`           | App billing          |
| `/purchases/` | App purchasing       |

### App Billing (`billing/urls.py`)

| Método   | URL                         | Vista / Nombre           | Descripción                   |
|----------|-----------------------------|--------------------------|-------------------------------|
| GET      | `/`                         | `home`                   | Dashboard principal           |
| GET/POST | `/signup/`                  | `signup`                 | Registro de usuarios          |
| GET      | `/brands/`                  | `brand_list`             | Listado de marcas             |
| GET/POST | `/brands/create/`           | `brand_create`           | Crear marca                   |
| GET/POST | `/brands/<pk>/edit/`        | `brand_update`           | Editar marca                  |
| POST     | `/brands/<pk>/delete/`      | `brand_delete`           | Eliminar marca                |
| GET      | `/groups/`                  | `productgroup_list`      | Listado de grupos             |
| GET/POST | `/groups/create/`           | `productgroup_create`    | Crear grupo                   |
| GET/POST | `/groups/<pk>/edit/`        | `productgroup_update`    | Editar grupo                  |
| POST     | `/groups/<pk>/delete/`      | `productgroup_delete`    | Eliminar grupo                |
| GET      | `/suppliers/`               | `supplier_list`          | Listado de proveedores        |
| GET/POST | `/suppliers/create/`        | `supplier_create`        | Crear proveedor               |
| GET/POST | `/suppliers/<pk>/edit/`     | `supplier_update`        | Editar proveedor              |
| POST     | `/suppliers/<pk>/delete/`   | `supplier_delete`        | Eliminar proveedor            |
| GET      | `/products/`                | `product_list`           | Listado de productos          |
| GET/POST | `/products/create/`         | `product_create`         | Crear producto                |
| GET/POST | `/products/<pk>/edit/`      | `product_update`         | Editar producto               |
| POST     | `/products/<pk>/delete/`    | `product_delete`         | Eliminar producto             |
| GET      | `/customers/`               | `customer_list`          | Listado de clientes           |
| GET/POST | `/customers/create/`        | `customer_create`        | Crear cliente                 |
| GET/POST | `/customers/<pk>/edit/`     | `customer_update`        | Editar cliente                |
| POST     | `/customers/<pk>/delete/`   | `customer_delete`        | Eliminar cliente              |
| GET      | `/invoices/`                | `invoice_list`           | Listado de facturas           |
| GET/POST | `/invoices/create/`         | `invoice_create`         | Crear factura                 |
| GET      | `/invoices/<pk>/`           | `invoice_detail`         | Detalle de factura            |
| GET      | `/invoices/<pk>/pdf/`       | `invoice_pdf`            | Exportar factura a PDF        |
| POST     | `/invoices/<pk>/delete/`    | `invoice_delete`         | Eliminar factura              |

### App Purchasing (`purchasing/urls.py`)

| Método   | URL                              | Nombre                   | Descripción                          |
|----------|----------------------------------|--------------------------|--------------------------------------|
| GET      | `/purchases/`                    | `purchase_list`          | Listado con filtros                  |
| GET/POST | `/purchases/create/`             | `purchase_create`        | Nueva orden de compra (formset)      |
| GET      | `/purchases/<pk>/`               | `purchase_detail`        | Detalle de la compra                 |
| GET      | `/purchases/<pk>/pdf/`           | `purchase_pdf`           | Exportar orden a PDF                 |
| GET      | `/purchases/<pk>/excel/`         | `purchase_excel`         | Exportar orden a Excel               |
| POST     | `/purchases/<pk>/delete/`        | `purchase_delete`        | Eliminar compra (revierte stock)     |
| GET      | `/purchases/report/`             | `purchase_report`        | Reporte de costos promedio           |
| GET      | `/purchases/export/excel/`       | `purchase_list_excel`    | Exportar listado filtrado a Excel    |

---

## Autenticación y Permisos

El sistema implementa dos niveles de protección:

### Login Required

Todas las vistas del sistema requieren que el usuario esté autenticado:
- **FBV**: mediante el decorador `@login_required`
- **CBV**: mediante `LoginRequiredMixin`

Usuarios no autenticados son redirigidos al login.

### Eliminación de registros
Las vistas de eliminación (invoice_delete, purchase_delete) son vistas basadas
en función (FBV) protegidas únicamente con el decorador @login_required. Por lo
tanto, cualquier usuario autenticado puede eliminar facturas y compras (al borrar
una compra, el stock se revierte automáticamente).

Nota: el StaffRequiredMixin definido en shared/mixins.py está diseñado para
vistas basadas en clase (CBV) y NO aplica a estas vistas FBV. Se documenta aquí
para dejar clara la diferencia entre ambos enfoques.

### Registro de Usuarios

`SignUpView` extiende `UserCreationForm` con campos adicionales:
- `username`, `first_name`, `last_name`, `email`
- `password1`, `password2`

Al registrarse, el usuario es autenticado automáticamente y redirigido al dashboard.

---

## Utilidades Personalizadas

### Validador de Cédula Ecuatoriana (`shared/validators.py`)

```python
validate_cedula_ec(value)
```

Valida que un número de identificación cumpla con el formato ecuatoriano:

1. Solo contiene dígitos numéricos
2. Tiene 10 dígitos (cédula) o 13 dígitos (RUC)
3. El código de provincia es válido (01 a 24)
4. El tercer dígito es menor que 6
5. El dígito verificador es correcto (algoritmo módulo 10)

Lanza `ValidationError` con mensaje descriptivo ante cualquier incumplimiento.

---

### Decorador de Auditoría (`shared/decorators.py`)

```python
@audit_action('ACTION_NAME')
def my_view(request):
    ...
```

Registra en el logger `audit` información de cada acción ejecutada:

```
[AUDIT] 2026-06-15 10:30:00 | admin | BRAND_LIST | GET | /brands/ | 127.0.0.1
```

Datos registrados: timestamp, usuario, acción, método HTTP, path, dirección IP.

Aplicado a las vistas de Brand: `BRAND_LIST`, `BRAND_CREATE`, `BRAND_UPDATE`, `BRAND_DELETE`.

---

### StaffRequiredMixin (`shared/mixins.py`)

```python
class StaffRequiredMixin:
    staff_redirect_url = 'billing:home'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, "Acceso denegado.")
            return redirect(self.staff_redirect_url)
        return super().dispatch(request, *args, **kwargs)
```

---

## Panel de Administración

Accesible en `/admin/` para superusuarios. Todos los modelos están registrados con configuraciones personalizadas:

| Modelo           | list_display                                | Extras                            |
|------------------|---------------------------------------------|-----------------------------------|
| `Brand`          | name, is_active, created_at                 | search, filter por is_active      |
| `ProductGroup`   | name, is_active                             |                                   |
| `Supplier`       | name, contact_name, email, is_active        |                                   |
| `Product`        | name, brand, group, unit_price, stock       | filter por brand/group; M2M horizontal |
| `Customer`       | dni, last_name, first_name, email           | Inline: CustomerProfile           |
| `Invoice`        | id, customer, invoice_date, total           | Inline: InvoiceDetail (tabular)   |

---

## Configuración

### Settings relevantes (`config/settings.py`)

```python
# Base de datos
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'dbA1.sqlite3',
    }
}

# Internacionalización
LANGUAGE_CODE = 'es-ec'
TIME_ZONE = 'America/Guayaquil'
USE_I18N = True
USE_TZ = True

# Autenticación
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
```

### Consideraciones para Producción

Antes de desplegar en producción, se deben ajustar los siguientes parámetros en `settings.py`:

- `DEBUG = False`
- `SECRET_KEY`: usar variable de entorno
- `ALLOWED_HOSTS`: agregar el dominio del servidor
- `DATABASES`: migrar a PostgreSQL o MySQL para producción
- Configurar archivos estáticos con `STATIC_ROOT` y `collectstatic`
- Configurar servidor WSGI/ASGI (Gunicorn, Uvicorn)

---

## Migraciones

| Migración                        | Fecha       | Descripción                      |
|----------------------------------|-------------|----------------------------------|
| `0001_initial`                   | 2026-06-11  | Creación de los 8 modelos        |
| `0002_alter_customer_dni`        | Posterior   | Añade validador al campo DNI     |

Para crear nuevas migraciones tras modificar modelos:

```bash
python manage.py makemigrations
python manage.py migrate
```
