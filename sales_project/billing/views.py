from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth import login
from django.http import HttpResponse
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum, F, Avg
from django.db.models.deletion import ProtectedError
from django.core.exceptions import ValidationError
from creditos_ventas import services as creditos_services
from django.utils import timezone
from datetime import timedelta, datetime
from io import BytesIO
import json
import html as html_module

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from .models import *
from .forms import SignUpForm, BrandForm, InvoiceForm, InvoiceDetailFormSet
from .ProductForm import ProductForm
from shared.mixins import StaffRequiredMixin, ExportMixin
from shared.decorators import audit_action

# === HOME (Página principal) ===
@login_required
def home(request):
    """Vista principal del sistema. Muestra resumen general."""
    from purchasing.models import Purchase, PurchaseDetail
    from creditos_ventas.models import CuotaVenta
    from creditos_compras.models import CuotaCompra

    low_stock_qs = Product.objects.filter(stock__lte=5, is_active=True)
    low_stock_count = low_stock_qs.count()
    top_products = (
        Product.objects
        .annotate(total_sold=Sum('invoice_details__quantity'))
        .filter(total_sold__isnull=False)
        .order_by('-total_sold')[:3]
    )

    # Gráfico semanal
    DAYS_ES = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM']
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_data = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        total = float(Invoice.objects.filter(
            invoice_date__date=day
        ).aggregate(t=Sum('total'))['t'] or 0)
        week_data.append({'day': DAYS_ES[i], 'total': total, 'is_today': day == today})
    max_val = max((d['total'] for d in week_data), default=0)
    for d in week_data:
        d['height'] = max(10, int(d['total'] / max_val * 80)) if max_val > 0 else 16
        d['is_max'] = max_val > 0 and d['total'] == max_val

    # Reporte de compras para el dashboard
    purchase_report = (
        PurchaseDetail.objects
        .values('product__name', 'product__brand__name')
        .annotate(
            avg_cost=Avg('unit_cost'),
            total_spent=Sum('subtotal'),
            total_qty=Sum('quantity'),
        )
        .order_by('-total_spent')[:5]
    )
    total_purchases = Purchase.objects.aggregate(s=Sum('total'))['s'] or 0
    total_purchase_count = Purchase.objects.count()

    active_customers = Customer.objects.filter(is_active=True).count()
    total_customers  = Customer.objects.count()
    active_invoices  = Invoice.objects.filter(is_active=True)
    total_invoices   = active_invoices.count()
    total_sales      = active_invoices.aggregate(s=Sum('total'))['s'] or 0

    cartera_pendiente = Invoice.objects.filter(
        tipo_pago='CREDITO', estado='PENDIENTE'
    ).aggregate(total=Sum('saldo'))['total'] or 0

    cuotas_vencidas = CuotaVenta.objects.filter(
        estado='PENDIENTE', fecha_vencimiento__lt=timezone.now().date()
    ).count()

    cuentas_por_pagar = Purchase.objects.filter(
        tipo_pago='CREDITO', estado='PENDIENTE'
    ).aggregate(total=Sum('saldo'))['total'] or 0

    cuotas_compra_vencidas = CuotaCompra.objects.filter(
        estado='PENDIENTE', fecha_vencimiento__lt=timezone.now().date()
    ).count()

    context = {
        'total_brands': Brand.objects.count(),
        'total_products': Product.objects.filter(is_active=True).count(),
        'total_customers': total_customers,
        'active_customers': active_customers,
        'total_invoices': total_invoices,
        'recent_invoices': active_invoices[:5],
        'low_stock': low_stock_qs,
        'total_sales': total_sales,
        'low_stock_count': low_stock_count,
        'top_products': top_products,
        'week_data': week_data,
        'purchase_report': purchase_report,
        'total_purchases': total_purchases,
        'total_purchase_count': total_purchase_count,
        'cartera_pendiente': cartera_pendiente,
        'cuotas_vencidas': cuotas_vencidas,
        'cuentas_por_pagar': cuentas_por_pagar,
        'cuotas_compra_vencidas': cuotas_compra_vencidas,
    }
    return render(request, 'billing/home.html', context)

# === REGISTRO ===
class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('billing:brand_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

# === BRAND (FBV) ===
@login_required
@audit_action('LIST_BRANDS')
def brand_list(request):
    brands = Brand.objects.all()
    return render(request, 'billing/brand_list.html', {'brands': brands})

@login_required
@audit_action('CREATE_BRAND')
def brand_create(request):
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Marca creada!')
            return redirect('billing:brand_list')
    else:
        form = BrandForm()
    return render(request, 'billing/brand_form.html', {'form': form, 'title': 'Crear Marca'})

@login_required
@audit_action('UPDATE_BRAND')
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Marca actualizada!')
            return redirect('billing:brand_list')
    else:
        form = BrandForm(instance=brand)
    return render(request, 'billing/brand_form.html', {'form': form, 'title': 'Editar Marca'})

@login_required
@audit_action('DELETE_BRAND')
def brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        brand.delete()
        messages.success(request, 'Brand deleted!')
        return redirect('billing:brand_list')
    return render(request, 'billing/brand_confirm_delete.html', {'object': brand})

# === PRODUCTGROUP (CBV) ===
@method_decorator(audit_action('LIST_PRODUCT_GROUPS'), name='dispatch')
class ProductGroupListView(LoginRequiredMixin, ListView):
    model = ProductGroup
    template_name = 'billing/productgroup_list.html'
    context_object_name = 'items'

@method_decorator(audit_action('CREATE_PRODUCT_GROUP'), name='dispatch')
class ProductGroupCreateView(LoginRequiredMixin, CreateView):
    model = ProductGroup
    fields = ['name', 'is_active']
    template_name = 'billing/productgroup_form.html'
    success_url = reverse_lazy('billing:productgroup_list')

@method_decorator(audit_action('UPDATE_PRODUCT_GROUP'), name='dispatch')
class ProductGroupUpdateView(LoginRequiredMixin, UpdateView):
    model = ProductGroup
    fields = ['name', 'is_active']
    template_name = 'billing/productgroup_form.html'
    success_url = reverse_lazy('billing:productgroup_list')

@method_decorator(audit_action('DELETE_PRODUCT_GROUP'), name='dispatch')
class ProductGroupDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = ProductGroup
    template_name = 'billing/productgroup_confirm_delete.html'
    success_url = reverse_lazy('billing:productgroup_list')
    staff_redirect_url = '/groups/'

# === SUPPLIER (CBV) ===
@method_decorator(audit_action('LIST_SUPPLIERS'), name='dispatch')
class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier
    template_name = 'billing/supplier_list.html'
    context_object_name = 'items'

@method_decorator(audit_action('CREATE_SUPPLIER'), name='dispatch')
class SupplierCreateView(LoginRequiredMixin, CreateView):
    model = Supplier
    fields = ['name', 'contact_name', 'email', 'phone', 'address', 'is_active']
    template_name = 'billing/supplier_form.html'
    success_url = reverse_lazy('billing:supplier_list')

@method_decorator(audit_action('UPDATE_SUPPLIER'), name='dispatch')
class SupplierUpdateView(LoginRequiredMixin, UpdateView):
    model = Supplier
    fields = ['name', 'contact_name', 'email', 'phone', 'address', 'is_active']
    template_name = 'billing/supplier_form.html'
    success_url = reverse_lazy('billing:supplier_list')

@method_decorator(audit_action('DELETE_SUPPLIER'), name='dispatch')
class SupplierDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Supplier
    template_name = 'billing/supplier_confirm_delete.html'
    success_url = reverse_lazy('billing:supplier_list')
    staff_redirect_url = '/suppliers/'

# === PRODUCT (CBV) ===
@method_decorator(audit_action('LIST_PRODUCTS'), name='dispatch')
class ProductListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Product
    template_name = 'billing/product_list.html'
    context_object_name = 'items'
    paginate_by = 10
    
    # Configuración de exportación
    export_fields = [
        ('name', 'Nombre'),
        ('description', 'Descripción'),
        ('brand.name', 'Marca'),
        ('group.name', 'Grupo'),
        ('unit_price', 'Precio Unitario'),
        ('stock', 'Stock'),
        ('is_active', 'Activo'),
    ]
    export_filename = 'productos'
    export_title = 'Lista de Productos'
    
    # Mapa de clave URL → tupla de campo de exportación
    _export_field_map = {
        'name':        ('name',        'Nombre'),
        'description': ('description', 'Descripción'),
        'brand':       ('brand.name',  'Marca'),
        'group':       ('group.name',  'Grupo'),
        'unit_price':  ('unit_price',  'Precio Unitario'),
        'stock':       ('stock',       'Stock'),
        'is_active':   ('is_active',   'Activo'),
    }

    def get(self, request, *args, **kwargs):
        export_format = request.GET.get('export')
        if export_format in ('pdf', 'excel'):
            cols_param = request.GET.get('cols', '')
            if cols_param:
                selected_keys = [k.strip() for k in cols_param.split(',') if k.strip() in self._export_field_map]
                if selected_keys:
                    self.export_fields = [self._export_field_map[k] for k in selected_keys]
            if export_format == 'pdf':
                return self.export_to_pdf()
            return self.export_to_excel()
        return super().get(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Product.objects.all()
        
        # Búsqueda por nombre
        name = self.request.GET.get('name', '')
        if name:
            queryset = queryset.filter(name__icontains=name)
        
        # Búsqueda por descripción
        description = self.request.GET.get('description', '')
        if description:
            queryset = queryset.filter(description__icontains=description)
        
        # Filtro por marca
        brand = self.request.GET.get('brand', '')
        if brand:
            queryset = queryset.filter(brand_id=brand)
        
        # Filtro por grupo
        group = self.request.GET.get('group', '')
        if group:
            queryset = queryset.filter(group_id=group)
        
        # Filtro por proveedor
        supplier = self.request.GET.get('supplier', '')
        if supplier:
            queryset = queryset.filter(suppliers__id=supplier)
        
        # Filtro por precio mínimo
        min_price = self.request.GET.get('min_price', '')
        if min_price:
            try:
                queryset = queryset.filter(unit_price__gte=Decimal(min_price))
            except:
                pass
        
        # Filtro por precio máximo
        max_price = self.request.GET.get('max_price', '')
        if max_price:
            try:
                queryset = queryset.filter(unit_price__lte=Decimal(max_price))
            except:
                pass
        
        # Filtro por stock mínimo
        min_stock = self.request.GET.get('min_stock', '')
        if min_stock:
            try:
                queryset = queryset.filter(stock__gte=int(min_stock))
            except:
                pass
        
        # Filtro por stock máximo
        max_stock = self.request.GET.get('max_stock', '')
        if max_stock:
            try:
                queryset = queryset.filter(stock__lte=int(max_stock))
            except:
                pass
        
        # Filtro por estado
        is_active = self.request.GET.get('is_active', '')
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)
        elif is_active == 'false':
            queryset = queryset.filter(is_active=False)
        
        return queryset.distinct()
    
    def get_export_data(self):
        """Obtiene los datos del queryset actual con soporte para campos relacionados"""
        queryset = self.get_queryset()
        data = []
        
        for obj in queryset:
            row = []
            for field_name, label in self.export_fields:
                try:
                    # Manejar campos con punto (relaciones)
                    if '.' in field_name:
                        parts = field_name.split('.')
                        value = obj
                        for part in parts:
                            value = getattr(value, part)
                    else:
                        value = getattr(obj, field_name)
                    
                    # Traducir booleanos y convertir a string
                    if isinstance(value, bool):
                        value = 'Sí' if value else 'No'
                    elif hasattr(value, '__str__'):
                        value = str(value)
                    row.append(value or '')
                except AttributeError:
                    row.append('')
            data.append(row)
        
        return data
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['brands'] = Brand.objects.all()
        context['groups'] = ProductGroup.objects.all()
        context['suppliers'] = Supplier.objects.all()
        
        # Pasar los valores de búsqueda actuales
        context['name'] = self.request.GET.get('name', '')
        context['description'] = self.request.GET.get('description', '')
        context['brand'] = self.request.GET.get('brand', '')
        context['group'] = self.request.GET.get('group', '')
        context['supplier'] = self.request.GET.get('supplier', '')
        context['min_price'] = self.request.GET.get('min_price', '')
        context['max_price'] = self.request.GET.get('max_price', '')
        context['min_stock'] = self.request.GET.get('min_stock', '')
        context['max_stock'] = self.request.GET.get('max_stock', '')
        context['is_active'] = self.request.GET.get('is_active', '')
        context['export_field_choices'] = [
            ('name',        'Nombre'),
            ('description', 'Descripción'),
            ('brand',       'Marca'),
            ('group',       'Grupo'),
            ('unit_price',  'Precio Unitario'),
            ('stock',       'Stock'),
            ('is_active',   'Activo'),
        ]
        return context

@method_decorator(audit_action('CREATE_PRODUCT'), name='dispatch')
class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

@method_decorator(audit_action('VIEW_PRODUCT'), name='dispatch')
class ProductDetailView(LoginRequiredMixin, DetailView):
    model = Product
    template_name = 'billing/product_detail.html'
    context_object_name = 'product'

@method_decorator(audit_action('UPDATE_PRODUCT'), name='dispatch')
class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

@method_decorator(audit_action('DELETE_PRODUCT'), name='dispatch')
class ProductDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Product
    template_name = 'billing/product_confirm_delete.html'
    success_url = reverse_lazy('billing:product_list')
    staff_redirect_url = '/products/'

# === CUSTOMER (CBV) ===
@method_decorator(audit_action('LIST_CUSTOMERS'), name='dispatch')
class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = 'billing/customer_list.html'
    context_object_name = 'items'

@method_decorator(audit_action('CREATE_CUSTOMER'), name='dispatch')
class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    fields = ['dni', 'first_name', 'last_name', 'email', 'phone', 'address', 'is_active']
    template_name = 'billing/customer_form.html'
    success_url = reverse_lazy('billing:customer_list')

@method_decorator(audit_action('UPDATE_CUSTOMER'), name='dispatch')
class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    fields = ['dni', 'first_name', 'last_name', 'email', 'phone', 'address', 'is_active']
    template_name = 'billing/customer_form.html'
    success_url = reverse_lazy('billing:customer_list')

@method_decorator(audit_action('DELETE_CUSTOMER'), name='dispatch')
class CustomerDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Customer
    template_name = 'billing/customer_confirm_delete.html'
    success_url = reverse_lazy('billing:customer_list')
    staff_redirect_url = '/customers/'

# === INVOICE (FBV - con formset de detalle) ===
@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    invoices = customers = products = suppliers = []

    if q:
        invoices = Invoice.objects.select_related('customer').filter(
            Q(customer__first_name__icontains=q) |
            Q(customer__last_name__icontains=q) |
            Q(customer__dni__icontains=q)
        )[:10]
        try:
            invoices = list(invoices) + list(
                Invoice.objects.select_related('customer').filter(id=int(q))[:1]
            )
        except (ValueError, TypeError):
            pass

        customers = Customer.objects.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(dni__icontains=q) |
            Q(email__icontains=q)
        )[:10]

        products = Product.objects.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q)
        )[:10]

        suppliers = Supplier.objects.filter(
            Q(name__icontains=q) |
            Q(contact_name__icontains=q) |
            Q(email__icontains=q)
        )[:10]

    total = len(invoices) + len(list(customers)) + len(list(products)) + len(list(suppliers))

    return render(request, 'billing/search_results.html', {
        'q': q,
        'invoices': invoices,
        'customers': customers,
        'products': products,
        'suppliers': suppliers,
        'total': total,
    })


@login_required
def invoice_list(request):
    """Lista todas las facturas."""
    invoices = Invoice.objects.select_related('customer').all()
    return render(request, 'billing/invoice_list.html', {'items': invoices})


@login_required
def invoice_create(request):
    """Crea una factura con sus líneas de detalle usando formset."""
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceDetailFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    invoice = form.save(commit=False)
                    invoice.save()
                    formset.instance = invoice
                    formset.save()
                    # Calcular subtotal, IVA 15% y total
                    subtotal = sum(d.subtotal for d in invoice.details.all())
                    invoice.subtotal = subtotal
                    invoice.tax = subtotal * Decimal('0.15')
                    invoice.total = invoice.subtotal + invoice.tax
                    invoice.save()
                    # Descontar stock — dentro del atomic para que sea todo-o-nada
                    for detail in invoice.details.all():
                        Product.objects.filter(pk=detail.product.pk).update(
                            stock=F('stock') - detail.quantity
                        )
                    creditos_services.procesar_tipo_pago(
                        invoice,
                        form.cleaned_data['tipo_pago'],
                        form.cleaned_data.get('num_cuotas'),
                    )
            except ValidationError as e:
                messages.error(request, str(e))
            else:
                messages.success(
                    request, f'Factura #{invoice.numero} creada. Total: ${invoice.total}'
                )
                return redirect('billing:invoice_list')

    else:
        form = InvoiceForm()
        formset = InvoiceDetailFormSet()
    products_prices = json.dumps(
        {str(p.id): str(p.unit_price) for p in Product.objects.filter(is_active=True)}
    )
    return render(request, 'billing/invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Crear Factura',
        'products_prices': products_prices,
    })


@login_required
def invoice_detail(request, pk):
    """Muestra el detalle completo de una factura."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})


@login_required
def invoice_delete(request, pk):
    """Elimina una factura y todos sus detalles (CASCADE)."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        invoice_id = invoice.id
        invoice_numero = invoice.numero
        try:
            invoice.delete()
        except ProtectedError:
            messages.error(
                request,
                f'No se puede eliminar la Factura #{invoice_numero}: tiene cuotas de '
                f'crédito asociadas. Elimina o reasigna las cuotas primero.'
            )
            return redirect('billing:invoice_list')
        messages.success(request, f'Invoice #{invoice_id} deleted!')
        return redirect('billing:invoice_list')
    return render(request, 'billing/invoice_confirm_delete.html', {'object': invoice})


@login_required
def invoice_pdf(request, pk):
    """Genera y descarga un PDF de la factura."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product'),
        pk=pk,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    elements = []
    styles = getSampleStyleSheet()
    esc = html_module.escape  # helper de escape XML

    available_width = letter[0] - 80

    # ── Estilos ──────────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        'InvTitle', parent=styles['Heading1'],
        fontSize=22, textColor=colors.HexColor('#1f4788'),
        alignment=1, spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        'InvSub', parent=styles['Normal'],
        fontSize=11, textColor=colors.grey,
        alignment=1, spaceAfter=16,
    )
    label_style = ParagraphStyle(
        'InvLabel', parent=styles['Normal'],
        fontSize=10, fontName='Helvetica-Bold',
    )
    value_style = ParagraphStyle('InvValue', parent=styles['Normal'], fontSize=10)
    hdr_style = ParagraphStyle(
        'TblHdr', parent=styles['Normal'],
        fontSize=10, fontName='Helvetica-Bold',
        textColor=colors.whitesmoke,
    )
    cell_style = ParagraphStyle('TblCell', parent=styles['Normal'], fontSize=10, leading=14)
    cell_r = ParagraphStyle('TblCellR', parent=styles['Normal'], fontSize=10, leading=14, alignment=2)
    tot_lbl = ParagraphStyle('TotLbl', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', alignment=2)
    tot_val = ParagraphStyle('TotVal', parent=styles['Normal'], fontSize=10, alignment=2)
    grand_lbl = ParagraphStyle('GrandLbl', parent=styles['Normal'], fontSize=12, fontName='Helvetica-Bold', alignment=2)
    grand_val = ParagraphStyle('GrandVal', parent=styles['Normal'], fontSize=12, fontName='Helvetica-Bold', alignment=2)

    # ── Encabezado ───────────────────────────────────────────────────────
    elements.append(Paragraph('FACTURA', title_style))
    elements.append(Paragraph('TecnoStock S.A', sub_style))

    # ── Info cliente / factura ────────────────────────────────────────────
    def lp(text): return Paragraph(esc(text), label_style)
    def vp(text): return Paragraph(esc(str(text)), value_style)

    cw = available_width / 4
    info_rows = [
        [lp('Factura #:'), vp(invoice.id),
         lp('Fecha:'),     vp(invoice.invoice_date.strftime('%d/%m/%Y %H:%M'))],
        [lp('Cliente:'),   vp(invoice.customer.full_name),
         lp('CI / RUC:'),  vp(invoice.customer.dni)],
    ]
    if invoice.customer.email:
        info_rows.append([lp('Email:'), vp(invoice.customer.email), vp(''), vp('')])
    if invoice.customer.phone:
        info_rows.append([lp('Teléfono:'), vp(invoice.customer.phone), vp(''), vp('')])

    info_table = Table(info_rows, colWidths=[cw * 0.8, cw * 1.4, cw * 0.8, cw * 1.0])
    info_table.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('INNERGRID',     (0, 0), (-1, -1), 0.25, colors.HexColor('#dee2e6')),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3 * inch))

    # ── Tabla de detalles ─────────────────────────────────────────────────
    col_w = [available_width * p for p in (0.45, 0.15, 0.20, 0.20)]

    detail_rows = [[
        Paragraph('Producto',     hdr_style),
        Paragraph('Cantidad',     hdr_style),
        Paragraph('Precio Unit.', hdr_style),
        Paragraph('Subtotal',     hdr_style),
    ]]
    for detail in invoice.details.all():
        detail_rows.append([
            Paragraph(esc(detail.product.name), cell_style),
            Paragraph(str(detail.quantity),     cell_r),
            Paragraph(f'${detail.unit_price}',  cell_r),
            Paragraph(f'${detail.subtotal}',    cell_r),
        ])

    num_data_rows = len(detail_rows)  # encabezado + filas de datos

    # Filas de totales
    detail_rows.append(['', '', Paragraph('Subtotal:',   tot_lbl), Paragraph(f'${invoice.subtotal}', tot_val)])
    detail_rows.append(['', '', Paragraph('IVA (15%):', tot_lbl), Paragraph(f'${invoice.tax}',      tot_val)])
    detail_rows.append(['', '', Paragraph('TOTAL:',      grand_lbl), Paragraph(f'${invoice.total}', grand_val)])

    det_table = Table(detail_rows, colWidths=col_w, repeatRows=1)
    det_table.setStyle(TableStyle([
        # Encabezado
        ('BACKGROUND',    (0, 0),              (-1, 0),               colors.HexColor('#1f4788')),
        ('LINEBELOW',     (0, 0),              (-1, 0),               2, colors.HexColor('#1f4788')),
        # Filas de datos con bandas
        ('ROWBACKGROUNDS',(0, 1),              (-1, num_data_rows - 1), [colors.white, colors.HexColor('#f0f0f0')]),
        ('GRID',          (0, 0),              (-1, num_data_rows - 1), 0.5, colors.HexColor('#cccccc')),
        # Totales
        ('LINEABOVE',     (2, num_data_rows),  (3, num_data_rows),    1, colors.HexColor('#1f4788')),
        ('BACKGROUND',    (2, num_data_rows + 2), (3, num_data_rows + 2), colors.HexColor('#fff3cd')),
        ('BOX',           (2, num_data_rows + 2), (3, num_data_rows + 2), 1.5, colors.HexColor('#1f4788')),
        # Padding general
        ('VALIGN',        (0, 0),              (-1, -1),              'MIDDLE'),
        ('LEFTPADDING',   (0, 0),              (-1, -1),              8),
        ('RIGHTPADDING',  (0, 0),              (-1, -1),              8),
        ('TOPPADDING',    (0, 0),              (-1, -1),              7),
        ('BOTTOMPADDING', (0, 0),              (-1, -1),              7),
    ]))
    elements.append(det_table)

    # ── Pie de página ─────────────────────────────────────────────────────
    elements.append(Spacer(1, 0.4 * inch))
    foot_style = ParagraphStyle(
        'Foot', parent=styles['Normal'],
        fontSize=8, textColor=colors.grey, alignment=1,
    )
    elements.append(Paragraph(
        f'Documento generado el {datetime.now().strftime("%d/%m/%Y a las %H:%M")}',
        foot_style,
    ))

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="factura_{invoice.id}.pdf"'
    return response