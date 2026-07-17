from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group, Permission
from shared.validators import validate_cedula_ec, validate_only_letters
from .models import UserProfile


class UserRegisterForm(UserCreationForm):
    """Registro público con selección obligatoria de rol y cédula."""
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=100, validators=[validate_only_letters])
    last_name = forms.CharField(max_length=100, validators=[validate_only_letters])
    cedula = forms.CharField(max_length=10, label='Cédula', validators=[validate_cedula_ec])
    role = forms.ModelChoiceField(
        queryset=Group.objects.exclude(name='Administrador'),
        required=True,
        label='Rol',
        empty_label='-- Selecciona un rol --',
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'cedula', 'password1', 'password2', 'role']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields:
            self.fields[f].widget.attrs['class'] = 'form-control'
        self.fields['username'].label = 'Nombre de usuario'
        self.fields['password1'].label = 'Contraseña'
        self.fields['password2'].label = 'Confirmar contraseña'
        self.fields['first_name'].label = 'Nombre'
        self.fields['last_name'].label = 'Apellido'

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'Ya existe una cuenta registrada con este correo electrónico.'
            )
        return email

    def clean_cedula(self):
        cedula = self.cleaned_data['cedula']
        if UserProfile.objects.filter(cedula=cedula).exists():
            raise forms.ValidationError(
                'Ya existe una cuenta registrada con esta cédula.'
            )
        return cedula

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            user.groups.add(self.cleaned_data['role'])
            UserProfile.objects.create(user=user, cedula=self.cleaned_data['cedula'])
        return user


class UserUpdateForm(forms.ModelForm):
    """El Administrador edita datos y roles de un usuario existente."""
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Roles',
    )
    cedula = forms.CharField(
        max_length=10, label='Cédula', required=False, validators=[validate_cedula_ec],
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Opcional si el usuario todavía no tiene cédula registrada.',
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active', 'groups']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, 'profile', None)
        if profile:
            self.fields['cedula'].initial = profile.cedula

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                'Ya existe una cuenta registrada con este correo electrónico.'
            )
        return email

    def clean_cedula(self):
        cedula = self.cleaned_data.get('cedula')
        if not cedula:
            # Opcional: el usuario editado puede no tener cédula todavía
            # (los preexistentes a este punto no la tienen) — sin valor,
            # no hay formato que validar ni unicidad que chequear.
            return cedula
        if UserProfile.objects.filter(cedula=cedula).exclude(user=self.instance).exists():
            raise forms.ValidationError(
                'Ya existe una cuenta registrada con esta cédula.'
            )
        return cedula

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            cedula = self.cleaned_data.get('cedula')
            if cedula:
                UserProfile.objects.update_or_create(
                    user=user, defaults={'cedula': cedula}
                )
        return user


class GroupForm(forms.ModelForm):
    """Crear/editar un rol y marcar sus permisos con checkboxes."""
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.select_related('content_type'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Permisos',
    )

    class Meta:
        model = Group
        fields = ['name', 'permissions']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}
