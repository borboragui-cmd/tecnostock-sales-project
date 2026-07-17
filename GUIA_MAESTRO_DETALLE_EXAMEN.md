# Guía práctica — Patrón Maestro-Detalle (Préstamos y Sobretiempos)

> Material de práctica post-examen. Reutiliza la arquitectura ya existente en
> TecnoStock: apps separadas por módulo, CBVs, formsets maestro-detalle
> (mismo patrón que `InvoiceDetailFormSet` en `billing/forms.py`), templates
> que extienden `billing/base.html`.

---

# FILA 1 — Sistema de Préstamos

## Paso 1 — Crear la app

```bash
cd sales_project/sales_project
python manage.py startapp prestamos
```

Agregar a `INSTALLED_APPS` en `config/settings.py`:
```python
INSTALLED_APPS = [
    ...
    'prestamos',
]
```

## Paso 2 — Modelos (`prestamos/models.py`)

```python
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.core.exceptions import ValidationError


class TipoPrestamo(models.Model):
    """Solo Django Admin, sin CRUD propio."""
    descripcion = models.CharField(max_length=100)
    tasa_interes = models.IntegerField(default=0)  # porcentaje, ej. 10 = 10%

    def __str__(self):
        return self.descripcion


class Empleado(models.Model):
    """Solo Django Admin, sin CRUD propio."""
    nombres = models.CharField(max_length=100)
    sueldo = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.nombres


class Prestamo(models.Model):
    ESTADOS = [
        ('PEND', 'Pendiente'),
        ('PAG', 'Pagado'),
        ('ANU', 'Anulado'),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    tipo_prestamo = models.ForeignKey(TipoPrestamo, on_delete=models.CASCADE)
    fecha_prestamo = models.DateField()
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    interes = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    monto_pagar = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    numero_cuotas = models.PositiveIntegerField(default=1)
    saldo = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    estado = models.CharField(max_length=4, choices=ESTADOS, default='PEND')

    def __str__(self):
        return f'Préstamo {self.pk} - {self.empleado}'

    def calcular_montos(self):
        """Calcula interés y monto a pagar en base al tipo de préstamo.
        No guarda todavía — lo hace save()."""
        if self.numero_cuotas < 1:
            raise ValidationError('El número de cuotas debe ser al menos 1.')
        tasa = Decimal(self.tipo_prestamo.tasa_interes) / Decimal(100)
        self.interes = (self.monto * tasa).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.monto_pagar = self.monto + self.interes

    def save(self, *args, **kwargs):
        es_nuevo = self.pk is None
        if es_nuevo:
            self.calcular_montos()
            self.saldo = self.monto_pagar
        super().save(*args, **kwargs)
        if es_nuevo:
            self._generar_cuotas()

    def _generar_cuotas(self):
        """Divide monto_pagar en numero_cuotas partes iguales; la última
        cuota absorbe el residuo de redondeo para que la suma cuadre
        exacto (mismo criterio que creditos_ventas.services.generar_cuotas
        en el proyecto real)."""
        from dateutil.relativedelta import relativedelta
        valor_base = (self.monto_pagar / self.numero_cuotas).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        acumulado = Decimal('0.00')
        for i in range(1, self.numero_cuotas + 1):
            if i < self.numero_cuotas:
                valor_cuota = valor_base
                acumulado += valor_cuota
            else:
                valor_cuota = self.monto_pagar - acumulado
            PrestamoDetalle.objects.create(
                prestamo=self,
                numero_cuota=i,
                fecha_vencimiento=self.fecha_prestamo + relativedelta(months=i),
                valor_cuota=valor_cuota,
                saldo_cuota=valor_cuota,
            )


class PrestamoDetalle(models.Model):
    prestamo = models.ForeignKey(Prestamo, related_name='detalles', on_delete=models.CASCADE)
    numero_cuota = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor_cuota = models.DecimalField(max_digits=10, decimal_places=2)
    saldo_cuota = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['prestamo', 'numero_cuota']

    def __str__(self):
        return f'Cuota {self.numero_cuota} - Préstamo {self.prestamo_id}'
```

**Por qué así**: el cálculo (interés, monto a pagar, generación de cuotas) vive en el modelo (`save()`), no en la vista — así cualquier forma de crear un `Prestamo` (admin, shell, CBV) dispara el mismo cálculo, sin duplicarlo.

## Paso 3 — Registrar admin para `TipoPrestamo`/`Empleado` (`prestamos/admin.py`)

```python
from django.contrib import admin
from .models import TipoPrestamo, Empleado

admin.site.register(TipoPrestamo)
admin.site.register(Empleado)
```

## Paso 4 — Migraciones

```bash
python manage.py makemigrations prestamos
python manage.py migrate prestamos
```

Cargar algunos `TipoPrestamo`/`Empleado` de prueba desde `/admin/`.

## Paso 5 — Vista para registrar el pago de una cuota (`prestamos/views.py`)

Como el enunciado pide "actualizar el saldo pendiente" y "gestionar el estado", hace falta una acción de pago (mismo patrón que `registrar_pagos` del proyecto real, pero más simple: sin mora ni descuento, no se pidió):

```python
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from .models import Prestamo, PrestamoDetalle
from .forms import PrestamoForm


class PrestamoListView(LoginRequiredMixin, ListView):
    model = Prestamo
    template_name = 'prestamos/prestamo_list.html'
    context_object_name = 'items'


class PrestamoDetailView(LoginRequiredMixin, DetailView):
    model = Prestamo
    template_name = 'prestamos/prestamo_detail.html'
    context_object_name = 'prestamo'


class PrestamoCreateView(LoginRequiredMixin, CreateView):
    model = Prestamo
    form_class = PrestamoForm
    template_name = 'prestamos/prestamo_form.html'
    success_url = reverse_lazy('prestamos:prestamo_list')


class PrestamoUpdateView(LoginRequiredMixin, UpdateView):
    """Solo permite editar si sigue PENDIENTE — no tiene sentido editar
    monto/cuotas de un préstamo ya pagado o anulado."""
    model = Prestamo
    form_class = PrestamoForm
    template_name = 'prestamos/prestamo_form.html'
    success_url = reverse_lazy('prestamos:prestamo_list')

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.estado != 'PEND':
            messages.error(request, 'Solo se puede editar un préstamo Pendiente.')
            return redirect('prestamos:prestamo_list')
        return super().dispatch(request, *args, **kwargs)


class PrestamoDeleteView(LoginRequiredMixin, DeleteView):
    model = Prestamo
    template_name = 'prestamos/prestamo_confirm_delete.html'
    success_url = reverse_lazy('prestamos:prestamo_list')


def registrar_pago_cuota(request, pk):
    """Marca una cuota como pagada (saldo_cuota=0), descuenta del saldo
    del préstamo, y si todas las cuotas quedan en 0, marca el préstamo
    como PAG."""
    detalle = get_object_or_404(PrestamoDetalle, pk=pk)
    if request.method == 'POST':
        if detalle.saldo_cuota <= 0:
            messages.error(request, 'Esta cuota ya está pagada.')
        else:
            valor_abonado = detalle.saldo_cuota
            detalle.saldo_cuota = 0
            detalle.save(update_fields=['saldo_cuota'])

            prestamo = detalle.prestamo
            prestamo.saldo = prestamo.saldo - valor_abonado
            if prestamo.saldo <= 0:
                prestamo.estado = 'PAG'
            prestamo.save(update_fields=['saldo', 'estado'])
            messages.success(request, f'Cuota {detalle.numero_cuota} pagada.')
    return redirect('prestamos:prestamo_detail', pk=detalle.prestamo_id)
```

## Paso 6 — Form (`prestamos/forms.py`)

```python
from django import forms
from .models import Prestamo


class PrestamoForm(forms.ModelForm):
    class Meta:
        model = Prestamo
        fields = ['empleado', 'tipo_prestamo', 'fecha_prestamo', 'monto', 'numero_cuotas']
        widgets = {
            'empleado': forms.Select(attrs={'class': 'form-select'}),
            'tipo_prestamo': forms.Select(attrs={'class': 'form-select'}),
            'fecha_prestamo': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'numero_cuotas': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

    def clean_monto(self):
        monto = self.cleaned_data['monto']
        if monto <= 0:
            raise forms.ValidationError('El monto debe ser mayor a cero.')
        return monto

    def clean_numero_cuotas(self):
        numero_cuotas = self.cleaned_data['numero_cuotas']
        if numero_cuotas < 1:
            raise forms.ValidationError('El número de cuotas debe ser al menos 1.')
        return numero_cuotas
```

## Paso 7 — URLs (`prestamos/urls.py`, nuevo archivo)

```python
from django.urls import path
from . import views

app_name = 'prestamos'

urlpatterns = [
    path('', views.PrestamoListView.as_view(), name='prestamo_list'),
    path('crear/', views.PrestamoCreateView.as_view(), name='prestamo_create'),
    path('<int:pk>/', views.PrestamoDetailView.as_view(), name='prestamo_detail'),
    path('<int:pk>/editar/', views.PrestamoUpdateView.as_view(), name='prestamo_update'),
    path('<int:pk>/eliminar/', views.PrestamoDeleteView.as_view(), name='prestamo_delete'),
    path('cuota/<int:pk>/pagar/', views.registrar_pago_cuota, name='pagar_cuota'),
]
```

Montar en `config/urls.py`:
```python
path('prestamos/', include('prestamos.urls')),
```

## Paso 8 — Templates (`prestamos/templates/prestamos/`)

**`prestamo_list.html`** (reusa `.list-table` del proyecto):
```html
{% extends 'billing/base.html' %}
{% block title %}Préstamos{% endblock %}
{% block content %}

<div class="page-header">
    <div>
        <div class="page-label">Talento Humano</div>
        <h1 class="page-title">Préstamos</h1>
    </div>
    <div class="page-actions">
        <a href="{% url 'prestamos:prestamo_create' %}" class="btn btn-primary">
            <i class="bi bi-plus-lg"></i> Nuevo Préstamo
        </a>
    </div>
</div>

<div class="content-card">
    <table class="table list-table mb-0">
        <thead>
            <tr>
                <th>Empleado</th><th>Tipo</th><th>Fecha</th>
                <th class="text-end">Monto</th><th class="text-end">A Pagar</th>
                <th class="text-end">Saldo</th><th>Estado</th><th></th>
            </tr>
        </thead>
        <tbody>
            {% for p in items %}
            <tr>
                <td><a href="{% url 'prestamos:prestamo_detail' p.pk %}">{{ p.empleado }}</a></td>
                <td>{{ p.tipo_prestamo }}</td>
                <td>{{ p.fecha_prestamo|date:"d/m/Y" }}</td>
                <td class="text-end">${{ p.monto }}</td>
                <td class="text-end">${{ p.monto_pagar }}</td>
                <td class="text-end">${{ p.saldo }}</td>
                <td><span class="badge bg-{% if p.estado == 'PAG' %}success{% elif p.estado == 'ANU' %}secondary{% else %}warning{% endif %}">{{ p.get_estado_display }}</span></td>
                <td>
                    {% if p.estado == 'PEND' %}
                    <a href="{% url 'prestamos:prestamo_update' p.pk %}" class="btn btn-sm btn-outline-primary">Editar</a>
                    {% endif %}
                    <a href="{% url 'prestamos:prestamo_delete' p.pk %}" class="btn btn-sm btn-outline-danger">Eliminar</a>
                </td>
            </tr>
            {% empty %}
            <tr><td colspan="8" class="text-center py-4 text-muted">No hay préstamos registrados.</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

**`prestamo_detail.html`** (muestra los cálculos + detalle de cuotas):
```html
{% extends 'billing/base.html' %}
{% block title %}Préstamo #{{ prestamo.id }}{% endblock %}
{% block content %}

<div class="page-header">
    <div>
        <div class="page-label">Talento Humano</div>
        <h1 class="page-title">Préstamo #{{ prestamo.id }}</h1>
        <p class="page-subtitle">{{ prestamo.empleado }} — {{ prestamo.tipo_prestamo }}</p>
    </div>
    <div class="page-actions">
        <a href="{% url 'prestamos:prestamo_list' %}" class="btn btn-secondary">Volver</a>
    </div>
</div>

<div class="content-card mb-4">
    <div class="content-card-body row">
        <div class="col-md-3"><strong>Monto:</strong> ${{ prestamo.monto }}</div>
        <div class="col-md-3"><strong>Interés:</strong> ${{ prestamo.interes }}</div>
        <div class="col-md-3"><strong>Total a pagar:</strong> ${{ prestamo.monto_pagar }}</div>
        <div class="col-md-3"><strong>Saldo:</strong> ${{ prestamo.saldo }}</div>
    </div>
</div>

<div class="content-card">
    <table class="table list-table mb-0">
        <thead>
            <tr><th>N° Cuota</th><th>Vencimiento</th><th class="text-end">Valor</th><th class="text-end">Saldo</th><th></th></tr>
        </thead>
        <tbody>
            {% for d in prestamo.detalles.all %}
            <tr>
                <td>{{ d.numero_cuota }}</td>
                <td>{{ d.fecha_vencimiento|date:"d/m/Y" }}</td>
                <td class="text-end">${{ d.valor_cuota }}</td>
                <td class="text-end">${{ d.saldo_cuota }}</td>
                <td>
                    {% if d.saldo_cuota > 0 %}
                    <form method="post" action="{% url 'prestamos:pagar_cuota' d.pk %}">
                        {% csrf_token %}
                        <button class="btn btn-sm btn-success">Pagar</button>
                    </form>
                    {% else %}
                    <span class="badge bg-success">Pagada</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

**`prestamo_form.html`**:
```html
{% extends 'billing/base.html' %}
{% block title %}Préstamo{% endblock %}
{% block content %}
<div class="content-card" style="max-width:600px;">
    <div class="content-card-body">
        <form method="post">
            {% csrf_token %}
            {{ form.as_p }}
            <button type="submit" class="btn btn-primary">Guardar</button>
            <a href="{% url 'prestamos:prestamo_list' %}" class="btn btn-secondary">Cancelar</a>
        </form>
    </div>
</div>
{% endblock %}
```

**`prestamo_confirm_delete.html`** (calcá el patrón de `security/templates/security/confirm_delete.html` del proyecto: título + botón confirmar/cancelar).

---

# FILA 2 — Sistema de Sobretiempos

## Paso 1 — Crear la app

```bash
python manage.py startapp sobretiempos
```
Agregar `'sobretiempos'` a `INSTALLED_APPS`.

## Paso 2 — Modelos (`sobretiempos/models.py`)

```python
from decimal import Decimal, ROUND_HALF_UP
from django.db import models


class TipoSobretiempo(models.Model):
    codigo = models.CharField(max_length=10)
    descripcion = models.CharField(max_length=100)
    factor = models.DecimalField(max_digits=4, decimal_places=2)  # ej. 1.50, 2.00

    def __str__(self):
        return self.descripcion


class Empleado(models.Model):
    nombres = models.CharField(max_length=100)
    sueldo = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.nombres


class Sobretiempo(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha_registro = models.DateField()
    total_horas = models.PositiveIntegerField(default=240)  # horas mensuales base
    sueldo_mensual = models.DecimalField(max_digits=10, decimal_places=2)
    total_calculado = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)

    def __str__(self):
        return f'Sobretiempo {self.pk} - {self.empleado}'

    @property
    def valor_hora(self):
        """Valor por hora del empleado, usado por cada detalle."""
        return (self.sueldo_mensual / self.total_horas).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    def recalcular_total(self):
        """Suma todos los detalles y actualiza total_calculado. Se llama
        después de guardar/borrar cualquier detalle (ver forms.py:
        SobretiempoDetalleFormSet, o la vista)."""
        total = self.detalles.aggregate(
            suma=models.Sum('valor_calculado')
        )['suma'] or Decimal('0.00')
        self.total_calculado = total
        self.save(update_fields=['total_calculado'])


class SobretiempoDetalle(models.Model):
    sobretiempo = models.ForeignKey(Sobretiempo, related_name='detalles', on_delete=models.CASCADE)
    tipo_sobretiempo = models.ForeignKey(TipoSobretiempo, on_delete=models.CASCADE)
    numero_horas = models.DecimalField(max_digits=6, decimal_places=2)
    valor_calculado = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        # valor_calculado = valor_hora del maestro * horas * factor del tipo
        valor_hora = self.sobretiempo.valor_hora
        self.valor_calculado = (
            valor_hora * self.numero_horas * self.tipo_sobretiempo.factor
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.tipo_sobretiempo} x {self.numero_horas}h'
```

**Por qué así**: acá el detalle SÍ se ingresa manualmente (a diferencia de Préstamos, donde las cuotas se generan solas) — el usuario elige tipo de sobretiempo + horas por fila, como en `InvoiceDetail` del proyecto real. Por eso el cálculo vive en `SobretiempoDetalle.save()`, y el total del maestro se recalcula aparte (`recalcular_total()`), llamado desde la vista después de guardar el formset.

## Paso 3 — Admin (`sobretiempos/admin.py`)

```python
from django.contrib import admin
from .models import TipoSobretiempo, Empleado

admin.site.register(TipoSobretiempo)
admin.site.register(Empleado)
```

## Paso 4 — Migraciones

```bash
python manage.py makemigrations sobretiempos
python manage.py migrate sobretiempos
```

## Paso 5 — Forms con formset maestro-detalle (`sobretiempos/forms.py`)

Mismo patrón que `InvoiceDetailFormSet` en `billing/forms.py` del proyecto real:

```python
from django import forms
from django.forms import inlineformset_factory
from .models import Sobretiempo, SobretiempoDetalle


class SobretiempoForm(forms.ModelForm):
    class Meta:
        model = Sobretiempo
        fields = ['empleado', 'fecha_registro', 'total_horas', 'sueldo_mensual']
        widgets = {
            'empleado': forms.Select(attrs={'class': 'form-select'}),
            'fecha_registro': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'total_horas': forms.NumberInput(attrs={'class': 'form-control'}),
            'sueldo_mensual': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def clean_sueldo_mensual(self):
        sueldo = self.cleaned_data['sueldo_mensual']
        if sueldo <= 0:
            raise forms.ValidationError('El sueldo debe ser mayor a cero.')
        return sueldo


class SobretiempoDetalleForm(forms.ModelForm):
    class Meta:
        model = SobretiempoDetalle
        fields = ['tipo_sobretiempo', 'numero_horas']
        widgets = {
            'tipo_sobretiempo': forms.Select(attrs={'class': 'form-select'}),
            'numero_horas': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def clean_numero_horas(self):
        horas = self.cleaned_data['numero_horas']
        if horas <= 0:
            raise forms.ValidationError('Las horas deben ser mayores a cero.')
        return horas


SobretiempoDetalleFormSet = inlineformset_factory(
    Sobretiempo, SobretiempoDetalle,
    form=SobretiempoDetalleForm,
    extra=1, can_delete=True,
)
```

## Paso 6 — Vistas (`sobretiempos/views.py`)

```python
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DeleteView

from .models import Sobretiempo
from .forms import SobretiempoForm, SobretiempoDetalleFormSet


class SobretiempoListView(LoginRequiredMixin, ListView):
    model = Sobretiempo
    template_name = 'sobretiempos/sobretiempo_list.html'
    context_object_name = 'items'


def sobretiempo_create(request):
    """CreateView clásica no alcanza acá porque necesitamos el formset
    del detalle en el mismo submit (igual que invoice_create en el
    proyecto real, que también es FBV por el mismo motivo)."""
    if request.method == 'POST':
        form = SobretiempoForm(request.POST)
        if form.is_valid():
            sobretiempo = form.save()
            formset = SobretiempoDetalleFormSet(request.POST, instance=sobretiempo)
            if formset.is_valid():
                formset.save()
                sobretiempo.recalcular_total()
                messages.success(request, 'Sobretiempo registrado correctamente.')
                return redirect('sobretiempos:sobretiempo_list')
            else:
                sobretiempo.delete()  # revertir si el detalle falla
        else:
            formset = SobretiempoDetalleFormSet(request.POST)
    else:
        form = SobretiempoForm()
        formset = SobretiempoDetalleFormSet()

    return render(request, 'sobretiempos/sobretiempo_form.html', {
        'form': form, 'formset': formset, 'title': 'Nuevo Sobretiempo',
    })


def sobretiempo_update(request, pk):
    sobretiempo = get_object_or_404(Sobretiempo, pk=pk)
    if request.method == 'POST':
        form = SobretiempoForm(request.POST, instance=sobretiempo)
        formset = SobretiempoDetalleFormSet(request.POST, instance=sobretiempo)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            sobretiempo.recalcular_total()
            messages.success(request, 'Sobretiempo actualizado.')
            return redirect('sobretiempos:sobretiempo_list')
    else:
        form = SobretiempoForm(instance=sobretiempo)
        formset = SobretiempoDetalleFormSet(instance=sobretiempo)

    return render(request, 'sobretiempos/sobretiempo_form.html', {
        'form': form, 'formset': formset, 'title': 'Editar Sobretiempo',
    })


class SobretiempoDeleteView(LoginRequiredMixin, DeleteView):
    model = Sobretiempo
    template_name = 'sobretiempos/sobretiempo_confirm_delete.html'
    success_url = reverse_lazy('sobretiempos:sobretiempo_list')
```

> **Nota sobre "CBVs obligatorias"**: el enunciado pide CBVs para el CRUD.
> `ListView`/`DeleteView` ya lo son. Para Create/Update con formset inline,
> el proyecto real (`billing.invoice_create`) también usa FBV por la misma
> razón: una `CreateView` estándar no maneja un formset relacionado en el
> mismo POST sin sobreescribir bastante. Si tu profesor exige CBV estricta
> ahí también, se puede lograr con `CreateView` + override de
> `form_valid()` para meter el formset ahí — decíme si querés esa versión,
> es más código pero es 100% CBV.

## Paso 7 — URLs (`sobretiempos/urls.py`, nuevo archivo)

```python
from django.urls import path
from . import views

app_name = 'sobretiempos'

urlpatterns = [
    path('', views.SobretiempoListView.as_view(), name='sobretiempo_list'),
    path('crear/', views.sobretiempo_create, name='sobretiempo_create'),
    path('<int:pk>/editar/', views.sobretiempo_update, name='sobretiempo_update'),
    path('<int:pk>/eliminar/', views.SobretiempoDeleteView.as_view(), name='sobretiempo_delete'),
]
```

Montar en `config/urls.py`:
```python
path('sobretiempos/', include('sobretiempos.urls')),
```

## Paso 8 — Templates (`sobretiempos/templates/sobretiempos/`)

**`sobretiempo_list.html`**: igual patrón que `prestamo_list.html` de arriba, columnas `Empleado`/`Fecha`/`Sueldo Mensual`/`Total Calculado`/acciones.

**`sobretiempo_form.html`** (formset inline, mismo patrón visual que `invoice_form.html` del proyecto):
```html
{% extends 'billing/base.html' %}
{% block title %}{{ title }}{% endblock %}
{% block content %}

<div class="content-card mb-4">
    <div class="content-card-body">
        <form method="post">
            {% csrf_token %}
            <h5>Datos del sobretiempo</h5>
            {{ form.as_p }}

            <h5 class="mt-4">Detalle de horas</h5>
            {{ formset.management_form }}
            <table class="table table-bordered">
                <thead>
                    <tr><th>Tipo</th><th>Horas</th><th></th></tr>
                </thead>
                <tbody>
                    {% for f in formset %}
                    <tr>
                        <td>{{ f.tipo_sobretiempo }}</td>
                        <td>{{ f.numero_horas }}</td>
                        <td>{% if f.instance.pk %}{{ f.DELETE }} Eliminar{% endif %}</td>
                        {{ f.id }}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <button type="submit" class="btn btn-primary">Guardar</button>
            <a href="{% url 'sobretiempos:sobretiempo_list' %}" class="btn btn-secondary">Cancelar</a>
        </form>
    </div>
</div>
{% endblock %}
```

---

# Versión 100% CBV (Create/Update con formset, sin FBV de por medio)

Si el profesor marcó que "todos se olvidaron" de usar CBV en la parte de
Create/Update con el detalle, es porque una `CreateView`/`UpdateView`
estándar no trae el formset relacionado resuelto solo — hay que
sobreescribir `get_context_data()` (para inyectar el formset en el
template) y `form_valid()` (para validar y guardar el formset junto con
el maestro, todo en una transacción). Es el patrón oficial que documenta
Django para esto. Reemplaza las FBV `sobretiempo_create`/`sobretiempo_update`
de más arriba.

## Sobretiempos — `sobretiempos/views.py` (reemplaza las FBV)

```python
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .models import Sobretiempo
from .forms import SobretiempoForm, SobretiempoDetalleFormSet


class SobretiempoListView(LoginRequiredMixin, ListView):
    model = Sobretiempo
    template_name = 'sobretiempos/sobretiempo_list.html'
    context_object_name = 'items'


class SobretiempoCreateView(LoginRequiredMixin, CreateView):
    model = Sobretiempo
    form_class = SobretiempoForm
    template_name = 'sobretiempos/sobretiempo_form.html'
    success_url = reverse_lazy('sobretiempos:sobretiempo_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['title'] = 'Nuevo Sobretiempo'
        if self.request.POST:
            data['formset'] = SobretiempoDetalleFormSet(self.request.POST)
        else:
            data['formset'] = SobretiempoDetalleFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            self.object.recalcular_total()
        messages.success(self.request, 'Sobretiempo registrado correctamente.')
        return redirect(self.success_url)


class SobretiempoUpdateView(LoginRequiredMixin, UpdateView):
    model = Sobretiempo
    form_class = SobretiempoForm
    template_name = 'sobretiempos/sobretiempo_form.html'
    success_url = reverse_lazy('sobretiempos:sobretiempo_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['title'] = 'Editar Sobretiempo'
        if self.request.POST:
            data['formset'] = SobretiempoDetalleFormSet(self.request.POST, instance=self.object)
        else:
            data['formset'] = SobretiempoDetalleFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            self.object.recalcular_total()
        messages.success(self.request, 'Sobretiempo actualizado correctamente.')
        return redirect(self.success_url)


class SobretiempoDeleteView(LoginRequiredMixin, DeleteView):
    model = Sobretiempo
    template_name = 'sobretiempos/sobretiempo_confirm_delete.html'
    success_url = reverse_lazy('sobretiempos:sobretiempo_list')
```

**Por qué funciona**: `get_context_data()` es lo que arma el diccionario
que recibe el template — ahí metemos el `formset` a mano, dos casos
(`self.request.POST` para cuando el usuario ya envió el form y hay que
revalidar con esos datos, o vacío/con instancia para el GET inicial).
`form_valid()` es el método que Django llama automáticamente cuando
`form.is_valid()` ya dio True — ahí, en vez de dejar que Django guarde
solo, guardamos el maestro (`form.save()`), le asignamos la instancia al
formset (`formset.instance = self.object`, necesario porque en el
`POST` inicial el formset no sabe todavía a qué `Sobretiempo` pertenece)
y lo guardamos también, todo dentro de un `with transaction.atomic()`
para que si el formset falla después de guardar el maestro, no quede un
`Sobretiempo` huérfano sin detalle.

## `sobretiempos/urls.py` (actualizado a `.as_view()`)

```python
from django.urls import path
from . import views

app_name = 'sobretiempos'

urlpatterns = [
    path('', views.SobretiempoListView.as_view(), name='sobretiempo_list'),
    path('crear/', views.SobretiempoCreateView.as_view(), name='sobretiempo_create'),
    path('<int:pk>/editar/', views.SobretiempoUpdateView.as_view(), name='sobretiempo_update'),
    path('<int:pk>/eliminar/', views.SobretiempoDeleteView.as_view(), name='sobretiempo_delete'),
]
```

`sobretiempo_form.html` **no cambia** — sigue leyendo `{{ form }}` y
`{{ formset }}` del contexto, que ahora vienen de `get_context_data()`
en vez de pasarse a mano desde una FBV con `render()`.

## Préstamos — ya estaba 100% CBV, nada que cambiar

A diferencia de Sobretiempos, en Préstamos el detalle (`PrestamoDetalle`)
**se genera solo** dentro de `Prestamo.save()` (paso 2, sección Fila 1)
— no hay ningún formset que el usuario llene a mano al crear/editar. Por
eso `PrestamoCreateView`/`PrestamoUpdateView` de la sección anterior ya
son `CreateView`/`UpdateView` estándar sin ningún truco — cumplen el
requisito de CBV tal cual están, no hace falta tocarlas. Lo único que
sigue siendo función (`registrar_pago_cuota`) es una acción puntual de
pago sobre una cuota individual, no parte del CRUD del maestro — si tu
profesor la quiere como CBV también, se puede convertir a una `View`
genérica con `post()`, avisame y te la doy.

---

## Checklist final antes de entregar cualquiera de las dos

- [ ] `python manage.py makemigrations` + `migrate` corridos sin error.
- [ ] Cargaste `TipoPrestamo`/`Empleado` (o `TipoSobretiempo`/`Empleado`) de prueba desde `/admin/`.
- [ ] El cálculo se ve reflejado en pantalla (no solo en BD) — revisá `prestamo_detail.html`/`sobretiempo_form.html`.
- [ ] Probaste crear, editar, eliminar, y ver el detalle al menos una vez cada uno.
- [ ] Las validaciones (`clean_monto`, `clean_numero_cuotas`, `clean_sueldo_mensual`, `clean_numero_horas`) rechazan valores inválidos si los probás a mano.
- [ ] La app nueva quedó en `INSTALLED_APPS` y montada en `config/urls.py`.
