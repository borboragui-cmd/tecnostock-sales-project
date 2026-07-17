






































































































































































































































































































































































































































































































































































































































































































































































































# Diagnóstico — Sistema de autenticación actual (previo a app `security`)

> Generado el 2026-07-16. Reporta el estado actual del código antes de crear la app
> `security` (roles/permisos) descrita en la guía "PARTE 13". No incluye ninguna
> propuesta de solución, solo el estado real verificado en el código.

---

## 1. Registro de usuarios — `SignUpForm` + `SignUpView`

Vive en la app **`billing`**, no en una app de seguridad separada.

**`billing/forms.py`** (líneas 1-30, resto del archivo tiene otros forms no relacionados):
```python
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory
from .models import Brand, Invoice, InvoiceDetail
from shared.validators import validate_only_letters


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(
        max_length=100,
        validators=[validate_only_letters],
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        max_length=100,
        validators=[validate_only_letters],
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields:
            self.fields[f].widget.attrs['class'] = 'form-control'
```

**`billing/views.py`** (bloque relevante, líneas 125-134):
```python
# === REGISTRO ===
class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('billing:brand_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response
```

No hay campo `role`/`group` en el form ni en la vista — el usuario registrado no queda en ningún `Group`.

---

## 2. Login/logout

Es una **mezcla**: login/logout usan `django.contrib.auth.urls` (genéricas de Django), pero el signup es propio (CBV de `billing`).

**`config/urls.py`** completo:
```python
"""
URL configuration for config project.
...
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('billing.urls')),
    path('purchases/', include('purchasing.urls')),
    path('creditos/', include('creditos_ventas.urls')),
    path('creditos-compras/', include('creditos_compras.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

`django.contrib.auth.urls` provee (con nombres estándar `login`, `logout`, `password_change`, etc., montados bajo `/accounts/`): `LoginView`, `LogoutView`, y las vistas de reset/cambio de password. Ninguna está sobreescrita.

En **`billing/urls.py`** solo hay una línea relacionada con auth:
```python
    # Signup
    path('signup/', views.SignUpView.as_view(), name='signup'),
```
(dentro del namespace `billing:`, o sea `billing:signup`).

---

## 3. Templates de auth existentes

Solo dos, en `templates/registration/` (carpeta a nivel raíz del proyecto Django, `TEMPLATES.DIRS = [BASE_DIR / 'templates']`):
- `registration/login.html`
- `registration/signup.html`

No existe `registration/logged_out.html`, `password_reset*.html` ni nada más — Django usaría sus templates internos (feos, sin estilo) si alguien navega a esas URLs de `django.contrib.auth.urls`, pero nadie lo ha probado aparentemente.

**`templates/registration/login.html`** — completo (custom, con su propio HTML/CSS standalone, NO extiende `billing/base.html`):
```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ingresar — TecnoStock S.A</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            display: flex;
            background: #F1F5F9;
        }

        /* ── PANEL IZQUIERDO ── */
        .left-panel {
            width: 48%;
            background: #0F172A;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 60px 48px;
            position: relative;
            overflow: hidden;
        }

        .left-panel::before {
            content: '';
            position: absolute;
            width: 420px; height: 420px;
            border-radius: 50%;
            background: rgba(37,99,235,0.08);
            top: -100px; right: -120px;
        }
        .left-panel::after {
            content: '';
            position: absolute;
            width: 280px; height: 280px;
            border-radius: 50%;
            background: rgba(37,99,235,0.05);
            bottom: -60px; left: -80px;
        }

        .brand-box {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
            position: relative;
            z-index: 1;
        }

        .brand-icon-ring {
            width: 88px; height: 88px;
            border-radius: 20px;
            background: #2563EB;
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 24px rgba(37,99,235,0.4);
        }
        .brand-icon-ring i {
            font-size: 2.6rem;
            color: #fff;
        }

        .brand-name {
            font-size: 2rem;
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.3px;
            text-align: center;
        }
        .brand-tagline {
            font-size: 0.9rem;
            color: rgba(255,255,255,0.5);
            text-align: center;
            font-weight: 400;
            max-width: 260px;
            line-height: 1.55;
        }

        .deco-icons {
            display: flex;
            gap: 12px;
            margin-top: 32px;
        }
        .deco-icon {
            width: 44px; height: 44px;
            border-radius: 10px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .deco-icon i { font-size: 1.1rem; color: rgba(255,255,255,0.5); }

        /* ── PANEL DERECHO ── */
        .right-panel {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 48px 56px;
            background: #F1F5F9;
        }

        .login-box {
            width: 100%;
            max-width: 360px;
        }

        .login-greeting {
            font-size: 0.72rem;
            font-weight: 600;
            color: #1E40AF;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .login-title {
            font-size: 1.75rem;
            font-weight: 700;
            color: #0F172A;
            letter-spacing: -0.3px;
            margin-bottom: 6px;
        }
        .login-subtitle {
            font-size: 0.875rem;
            color: #64748B;
            margin-bottom: 32px;
        }

        .field-group { margin-bottom: 16px; }

        .field-label {
            font-size: 0.78rem;
            font-weight: 500;
            color: #374151;
            margin-bottom: 6px;
            display: block;
        }

        .input-wrap {
            position: relative;
        }
        .input-wrap i {
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: #94A3B8;
            font-size: 0.9rem;
            pointer-events: none;
        }
        .input-wrap input {
            width: 100%;
            padding: 11px 14px 11px 40px;
            border-radius: 6px;
            border: 1px solid #E2E8F0;
            background: #fff;
            font-size: 0.9rem;
            color: #0F172A;
            font-family: 'Inter', sans-serif;
            outline: none;
            transition: border-color 0.15s, box-shadow 0.15s;
        }
        .input-wrap input:focus {
            border-color: #2563EB;
            box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
        }
        .input-wrap input::placeholder { color: #94A3B8; }

        .field-error {
            font-size: 0.78rem;
            color: #DC2626;
            margin-top: 5px;
            padding-left: 2px;
        }

        .btn-login {
            width: 100%;
            padding: 12px;
            background: #2563EB;
            border: none;
            border-radius: 6px;
            color: #fff;
            font-size: 0.925rem;
            font-weight: 500;
            font-family: 'Inter', sans-serif;
            cursor: pointer;
            box-shadow: 0 1px 3px rgba(37,99,235,0.3);
            transition: all 0.15s;
            margin-top: 8px;
        }
        .btn-login:hover {
            background: #1D4ED8;
            box-shadow: 0 2px 8px rgba(37,99,235,0.35);
        }

        .register-note {
            text-align: center;
            margin-top: 22px;
            font-size: 0.86rem;
            color: #64748B;
        }
        .register-note a {
            color: #2563EB;
            font-weight: 500;
            text-decoration: none;
        }
        .register-note a:hover {
            text-decoration: underline;
            color: #1D4ED8;
        }

        @media (max-width: 768px) {
            body { flex-direction: column; }
            .left-panel {
                width: 100%;
                padding: 36px 24px;
                min-height: 200px;
            }
            .brand-name { font-size: 1.5rem; }
            .deco-icons { display: none; }
            .right-panel { padding: 32px 24px; }
        }
    </style>
</head>
<body>

    <!-- ── PANEL IZQUIERDO (marca) ── -->
    <div class="left-panel">
        <div class="brand-box">
            <div class="brand-icon-ring">
                <i class="bi bi-cart-fill"></i>
            </div>
            <div class="brand-name">TecnoStock S.A</div>
            <div class="brand-tagline">Sistema integral de ventas, compras e inventario</div>
            <div class="deco-icons">
                <div class="deco-icon"><i class="bi bi-box-seam"></i></div>
                <div class="deco-icon"><i class="bi bi-receipt"></i></div>
                <div class="deco-icon"><i class="bi bi-graph-up-arrow"></i></div>
                <div class="deco-icon"><i class="bi bi-people"></i></div>
            </div>
        </div>
    </div>

    <!-- ── PANEL DERECHO (formulario) ── -->
    <div class="right-panel">
        <div class="login-box">
            <div class="login-greeting">Bienvenido de vuelta</div>
            <h1 class="login-title">Inicia sesión</h1>
            <p class="login-subtitle">Ingresa tus credenciales para continuar</p>

            <form method="post">
                {% csrf_token %}

                <div class="field-group">
                    <label class="field-label">Usuario</label>
                    <div class="input-wrap">
                        <i class="bi bi-person"></i>
                        <input type="text" name="username" placeholder="Tu nombre de usuario"
                               value="{{ form.username.value|default:'' }}" autocomplete="username">
                    </div>
                    {% for error in form.username.errors %}
                    <div class="field-error">{{ error }}</div>
                    {% endfor %}
                </div>

                <div class="field-group">
                    <label class="field-label">Contraseña</label>
                    <div class="input-wrap">
                        <i class="bi bi-lock"></i>
                        <input type="password" name="password" placeholder="••••••••"
                               autocomplete="current-password">
                    </div>
                    {% for error in form.password.errors %}
                    <div class="field-error">{{ error }}</div>
                    {% endfor %}
                </div>

                {% if form.non_field_errors %}
                <div class="field-error" style="margin-bottom:12px; font-size:0.84rem;">
                    {% for error in form.non_field_errors %}{{ error }}{% endfor %}
                </div>
                {% endif %}

                <button type="submit" class="btn-login">
                    <i class="bi bi-box-arrow-in-right"></i> Acceder
                </button>
            </form>

            <p class="register-note">
                ¿No tienes cuenta? <a href="{% url 'billing:signup' %}">Regístrate aquí</a>
            </p>
        </div>
    </div>

</body>
</html>
```

**`templates/registration/signup.html`** — completo (este SÍ extiende `billing/base.html`):
```html
{% extends 'billing/base.html' %}

{% block title %}Registro{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card form-card shadow-sm">
            <div class="card-header bg-white text-dark border-bottom" style="border-color: var(--primary);">
                <h4 class="mb-0">Crear cuenta</h4>
            </div>
            <div class="card-body">
                <form method="post">
                    {% csrf_token %}
                    {% for field in form %}
                    <div class="mb-3">
                        <label class="form-label">{{ field.label }}</label>
                        {{ field }}
                        <small class="text-muted">{{ field.help_text }}</small>
                        {% for error in field.errors %}
                        <div class="text-danger">{{ error }}</div>
                        {% endfor %}
                    </div>
                    {% endfor %}
                    <button type="submit" class="btn btn-primary w-100">Registrarse</button>
                </form>
                <p class="mt-3 text-center">
                    ¿Ya tienes una cuenta? <a href="{% url 'login' %}">Ingresar</a>
                </p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

---

## 4. `LOGIN_URL` / `LOGIN_REDIRECT_URL` / `LOGOUT_REDIRECT_URL`

En `config/settings.py`:
```python
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
LOGIN_URL = '/accounts/login/'
```

---

## 5. Grupos/permisos custom existentes

**Ninguno.** Todas las coincidencias de "Group"/"Permission" en el código son el modelo propio `ProductGroup` (catálogo de productos), no `auth.Group`:
```python
class ProductGroupListView(LoginRequiredMixin, ListView):
    model = ProductGroup
class ProductGroupCreateView(LoginRequiredMixin, CreateView):
    model = ProductGroup
class ProductGroupUpdateView(LoginRequiredMixin, UpdateView):
    model = ProductGroup
class ProductGroupDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = ProductGroup
```
No hay ninguna migración que toque `auth_group` ni `auth_permission`, ni ningún `Group.objects.create(...)` en el código. La base de datos no tiene roles creados (más allá de lo que Django trae de fábrica: `add_/change_/delete_/view_` por modelo).

---

## 6. Navbar actual de `billing/base.html`

**No es un `<ul class="navbar-nav">` de Bootstrap** — el proyecto usa un sidebar propio (`<aside class="sidebar">`) con clases custom (`nav-item`, `nav-section`, `nav-label`). Esto es importante porque la guía en PDF asume Bootstrap navbar con dropdown; ese bloque HTML de la guía no calza literal aquí.

Bloque completo (líneas 367-436 de `billing/Templates/billing/base.html`):
```html
<div style="display:flex; min-height:100vh; width:100%;">

    <!-- ══════════ SIDEBAR ══════════ -->
    <aside class="sidebar">

        <a href="{% url 'billing:home' %}" class="sidebar-logo">
            <div class="logo-icon-box"><i class="bi bi-cart-fill"></i></div>
            <div>
                <div class="logo-title">TECNOSTOCK</div>
                <div class="logo-sub">S.A</div>
            </div>
        </a>

        <nav class="nav-section">
            {% if user.is_authenticated %}
            <div class="nav-label">Operaciones</div>
            <a href="{% url 'billing:brand_list' %}"
               class="nav-item {% if '/brands' in request.path %}active{% endif %}">
                <i class="bi bi-tag"></i> Marcas
            </a>
            <a href="{% url 'billing:productgroup_list' %}"
               class="nav-item {% if '/groups' in request.path %}active{% endif %}">
                <i class="bi bi-layers"></i> Grupos
            </a>
            <a href="{% url 'billing:supplier_list' %}"
               class="nav-item {% if '/suppliers' in request.path %}active{% endif %}">
                <i class="bi bi-shop"></i> Proveedores
            </a>
            <a href="{% url 'billing:product_list' %}"
               class="nav-item {% if '/products' in request.path %}active{% endif %}">
                <i class="bi bi-box-seam"></i> Productos
            </a>
            <a href="{% url 'billing:customer_list' %}"
               class="nav-item {% if '/customers' in request.path %}active{% endif %}">
                <i class="bi bi-people"></i> Clientes
            </a>
            <a href="{% url 'billing:invoice_list' %}"
               class="nav-item {% if '/invoices' in request.path %}active{% endif %}">
                <i class="bi bi-receipt"></i> Facturas
            </a>
            <a href="{% url 'purchasing:purchase_list' %}"
               class="nav-item {% if '/purchases' in request.path %}active{% endif %}">
                <i class="bi bi-cart"></i> Compras
            </a>
            {% else %}
            <a href="{% url 'login' %}"          class="nav-item"><i class="bi bi-box-arrow-in-right"></i> Ingresar</a>
            <a href="{% url 'billing:signup' %}" class="nav-item"><i class="bi bi-person-plus"></i> Registrarse</a>
            {% endif %}
        </nav>

        {% if user.is_authenticated %}
        <div class="sidebar-footer">
            <div class="user-info">
                <div class="user-avatar">{{ user.username|slice:":2"|upper }}</div>
                <div>
                    <div class="user-name">{{ user.get_full_name|default:user.username|capfirst }}</div>
                    <div class="user-role">{{ user.email|default:"Sistema" }}</div>
                </div>
            </div>
            <form method="post" action="{% url 'logout' %}">
                {% csrf_token %}
                <button type="submit" class="logout-btn-sidebar">
                    <i class="bi bi-box-arrow-right"></i> Salir
                </button>
            </form>
        </div>
        {% endif %}

    </aside>
    <!-- ══════════ FIN SIDEBAR ══════════ -->

    <!-- ══════════ MAIN ══════════ -->
    <main class="main-content">
```

Nota: el sidebar actual NO tiene enlaces a `creditos_ventas`/`creditos_compras` (cuotas pendientes, historial de pagos, etc.) — esos módulos solo se acceden desde tarjetas del dashboard (`home.html`), no desde el menú lateral. Tampoco hay campo `is_staff`/rol visible en `user-role` — hoy muestra el email.

---

## 7. Modelos por app (con `app_label`, igual al nombre de la app en los 4 casos — sin overrides en `apps.py`)

**`billing`** (`app_label='billing'`):
- `Brand`
- `ProductGroup`
- `Supplier`
- `Product`
- `Customer`
- `CustomerProfile`
- `Invoice`
- `InvoiceDetail`

**`purchasing`** (`app_label='purchasing'`):
- `Purchase`
- `PurchaseDetail`
(reutiliza `billing.Supplier` y `billing.Product` vía FK, no los redefine — confirmado, no aparecen en `purchasing/models.py`)

**`creditos_ventas`** (`app_label='creditos_ventas'`):
- `CuotaVenta`
- `PagoCuotaVenta`

**`creditos_compras`** (`app_label='creditos_compras'`):
- `CuotaCompra`
- `PagoCuotaCompra`

Por lo tanto los codenames de permisos automáticos serían, por ejemplo: `billing.add_invoice`, `purchasing.view_purchase`, `creditos_ventas.change_cuotaventa`, `creditos_compras.delete_pagocuotacompra`, etc. — sin prefijo distinto al nombre de la app.

**`shared`** no está en `INSTALLED_APPS` (no tiene `apps.py`, no es una app Django registrada, solo un paquete Python de utilidades) — no genera modelos ni permisos.

**`INSTALLED_APPS` completo actual** (para contexto de dónde habría que insertar `'security'`):
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'billing',
    'purchasing',
    'creditos_ventas',
    'creditos_compras',
    #user apps
   'debug_toolbar',
   'django_extensions',

]
```
