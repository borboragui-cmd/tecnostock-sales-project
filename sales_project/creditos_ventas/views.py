from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.forms import formset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView

from billing.models import Invoice
from shared.mixins import ExportMixin
from .models import CuotaVenta, PagoCuotaVenta
from .forms import PagoCuotaForm
from . import services
from . import pdf_utils


class CuotaVentaPendientesListView(LoginRequiredMixin, ExportMixin, ListView):
    """Consulta global de cuotas pendientes, con filtro opcional por factura.
    Hereda de ExportMixin para exponer exportación a PDF/Excel sin duplicar
    la lógica ya usada en ProductListView."""
    model = CuotaVenta
    template_name = 'creditos_ventas/cuotas_pendientes.html'
    context_object_name = 'cuotas'

    export_fields = [
        ('factura.numero', 'Factura'),
        ('factura.customer', 'Cliente'),
        ('numero', 'N° Cuota'),
        ('fecha_vencimiento', 'Vencimiento'),
        ('valor', 'Valor'),
        ('saldo', 'Saldo'),
        ('estado', 'Estado'),
    ]
    export_filename = 'cuotas_pendientes'
    export_title = 'Cuotas Pendientes'

    def get_queryset(self):
        qs = CuotaVenta.objects.select_related('factura', 'factura__customer').filter(estado='PENDIENTE')
        factura_id = self.request.GET.get('factura')
        if factura_id:
            qs = qs.filter(factura_id=factura_id)
        return qs

    def get(self, request, *args, **kwargs):
        export_format = request.GET.get('export')
        if export_format == 'pdf':
            return self.export_to_pdf()
        if export_format == 'excel':
            return self.export_to_excel()
        return super().get(request, *args, **kwargs)


class CuotaVentaListView(ListView):
    """Listado completo de cuotas (pendientes y pagadas) para auditoría."""
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_list.html'
    context_object_name = 'items'
    paginate_by = 25

    def get_queryset(self):
        return CuotaVenta.objects.select_related('factura', 'factura__customer').all()


@login_required
def registrar_pagos(request, factura_id):
    """Muestra las cuotas pendientes de UNA factura, permite marcar varias
    para pagarlas en un solo envío (todo o nada)."""
    factura = get_object_or_404(Invoice, pk=factura_id)
    cuotas_qs = factura.cuotas.filter(estado='PENDIENTE').order_by('numero')

    PagoFormSet = formset_factory(PagoCuotaForm, extra=0)

    if request.method == 'POST':
        formset = PagoFormSet(request.POST)
        if formset.is_valid():
            pagos_data = []
            for form in formset:
                if form.cleaned_data.get('pagar'):
                    valor = form.cleaned_data.get('valor')
                    if not valor:
                        messages.error(request, 'Debes indicar un valor para cada cuota marcada.')
                        return render(request, 'creditos_ventas/registrar_pagos.html', {
                            'factura': factura, 'filas': list(zip(formset, cuotas_qs)),
                        })
                    pagos_data.append({
                        'cuota_id': form.cleaned_data['cuota_id'],
                        'valor': valor,
                        'observacion': form.cleaned_data.get('observacion', ''),
                    })

            if not pagos_data:
                messages.warning(request, 'No seleccionaste ninguna cuota para pagar.')
            else:
                try:
                    resultados = services.registrar_pagos_multiples(pagos_data)
                    request.session['ultimo_lote_pagos'] = [str(p.id) for p in resultados]
                    messages.success(request, f'{len(pagos_data)} pago(s) registrado(s) correctamente.')
                    return redirect('creditos_ventas:comprobante_lote')
                except ValidationError as e:
                    messages.error(request, str(e))
    else:
        initial = [{'cuota_id': c.id, 'valor': c.saldo, 'fecha': timezone.now().date()} for c in cuotas_qs]
        formset = PagoFormSet(initial=initial)

    return render(request, 'creditos_ventas/registrar_pagos.html', {
        'factura': factura, 'filas': list(zip(formset, cuotas_qs)),
    })


class HistorialPagosListView(ListView):
    model = PagoCuotaVenta
    template_name = 'creditos_ventas/historial_pagos.html'
    context_object_name = 'items'
    paginate_by = 25

    def get_queryset(self):
        qs = PagoCuotaVenta.objects.select_related(
            'cuota', 'cuota__factura', 'cuota__factura__customer'
        ).all()
        factura_id = self.request.GET.get('factura')
        if factura_id:
            qs = qs.filter(cuota__factura_id=factura_id)
        return qs


@login_required
def imprimir_plan_pagos(request, factura_id):
    factura = get_object_or_404(Invoice, pk=factura_id, tipo_pago='CREDITO')
    return pdf_utils.generar_pdf_plan_pagos(factura)


@login_required
def comprobante_lote(request):
    """Página HTML de confirmación tras registrar uno o varios pagos."""
    ids = request.session.get('ultimo_lote_pagos', [])
    pagos = PagoCuotaVenta.objects.filter(id__in=ids).select_related(
        'cuota', 'cuota__factura', 'cuota__factura__customer'
    )
    return render(request, 'creditos_ventas/comprobante_lote.html', {'pagos': pagos})


@login_required
def comprobante_lote_pdf(request):
    ids = request.session.get('ultimo_lote_pagos', [])
    pagos = PagoCuotaVenta.objects.filter(id__in=ids).select_related(
        'cuota', 'cuota__factura', 'cuota__factura__customer'
    )
    return pdf_utils.generar_pdf_comprobante_lote(pagos)
