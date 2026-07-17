from django import forms


class PagoCuotaCompraForm(forms.Form):
    """Una fila del formset de registro de pagos múltiples."""
    cuota_id = forms.IntegerField(widget=forms.HiddenInput())
    pagar = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    valor = forms.DecimalField(
        required=False, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    fecha = forms.DateField(
        required=False,
        # readonly: la fecha de pago siempre es hoy, mismo criterio que
        # PagoCuotaForm en creditos_ventas/forms.py.
        widget=forms.DateInput(attrs={
            'class': 'form-control', 'type': 'date', 'readonly': 'readonly',
        }, format='%Y-%m-%d'),
    )
    observacion = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
