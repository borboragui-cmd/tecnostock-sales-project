from django import forms
from django.forms import inlineformset_factory
from .models import Brand, Invoice, InvoiceDetail


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class InvoiceForm(forms.ModelForm):
    """Formulario para la cabecera de la factura (cliente + tipo de pago)."""
    num_cuotas = forms.IntegerField(
        required=False, min_value=1, label='Número de cuotas',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_num_cuotas'})
    )

    class Meta:
        model = Invoice
        fields = ['customer', 'tipo_pago']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'tipo_pago': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_pago'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('tipo_pago') == 'CREDITO' and not cleaned.get('num_cuotas'):
            raise forms.ValidationError('Debes indicar el número de cuotas para una venta a crédito.')
        return cleaned


# Formset para las líneas de detalle de la factura.
# extra=3 muestra 3 filas vacías; can_delete=True agrega checkbox para borrar filas.
InvoiceDetailFormSet = inlineformset_factory(
    Invoice,
    InvoiceDetail,
    fields=['product', 'quantity', 'unit_price'],
    extra=3,
    can_delete=True,
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
    }
)