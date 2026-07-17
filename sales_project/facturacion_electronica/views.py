from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from billing.models import Invoice
from purchasing.models import Purchase
from .models import ComprobanteElectronico
from . import services


@login_required
def generar_comprobante_factura(request, factura_id):
    factura = get_object_or_404(Invoice, pk=factura_id)
    try:
        comprobante = services.crear_comprobante(factura=factura)
    except ValidationError as e:
        messages.error(request, str(e))
        return redirect('billing:invoice_detail', pk=factura.pk)
    return redirect('facturacion_electronica:comprobante_detail', pk=comprobante.pk)


@login_required
def generar_comprobante_compra(request, compra_id):
    compra = get_object_or_404(Purchase, pk=compra_id)
    try:
        comprobante = services.crear_comprobante(compra=compra)
    except ValidationError as e:
        messages.error(request, str(e))
        return redirect('purchasing:purchase_detail', pk=compra.pk)
    return redirect('facturacion_electronica:comprobante_detail', pk=comprobante.pk)


@login_required
def comprobante_detail(request, pk):
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    puede_forzar = request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()
    return render(request, 'facturacion_electronica/comprobante_detail.html', {
        'comprobante': comprobante,
        'puede_forzar': puede_forzar,
    })


@login_required
def firmar_comprobante(request, pk):
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    if request.method == 'POST':
        try:
            services.firmar(comprobante)
            messages.success(request, 'Comprobante firmado (simulación).')
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect('facturacion_electronica:comprobante_detail', pk=comprobante.pk)


@login_required
def enviar_comprobante(request, pk):
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    if request.method == 'POST':
        try:
            services.enviar(comprobante)
            messages.success(request, 'Comprobante enviado al SRI (simulación) — en procesamiento.')
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect('facturacion_electronica:comprobante_detail', pk=comprobante.pk)


@login_required
def consultar_comprobante(request, pk):
    comprobante = get_object_or_404(ComprobanteElectronico, pk=pk)
    if request.method == 'POST':
        forzar = request.POST.get('forzar') or None
        try:
            services.consultar_respuesta_sri(comprobante, forzar=forzar, usuario=request.user)
            messages.success(request, f'Respuesta del SRI (simulación): {comprobante.get_estado_display()}.')
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect('facturacion_electronica:comprobante_detail', pk=comprobante.pk)


class ComprobanteListView(LoginRequiredMixin, ListView):
    """Listado de auditoría — todos los comprobantes, cualquier origen."""
    model = ComprobanteElectronico
    template_name = 'facturacion_electronica/comprobante_list.html'
    context_object_name = 'items'
    paginate_by = 25

    def get_queryset(self):
        return ComprobanteElectronico.objects.select_related(
            'factura', 'factura__customer', 'compra', 'compra__supplier'
        ).all()
