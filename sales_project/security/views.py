from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group, Permission
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, DeleteView

from shared.mixins import GroupRequiredMixin
from .forms import UserRegisterForm, UserUpdateForm, GroupForm


class AdminOnlyMixin(LoginRequiredMixin, GroupRequiredMixin):
    """Combina login + rol Administrador. El superusuario siempre pasa."""
    group_required = ['Administrador']
    group_redirect_url = '/'


# === Registro público (reemplaza billing.SignUpView) ===
class RegisterView(CreateView):
    form_class = UserRegisterForm
    template_name = 'security/register.html'
    success_url = reverse_lazy('billing:home')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


# === Usuarios (lectura: cualquier autenticado; mutación: solo Administrador) ===
class UserListView(LoginRequiredMixin, ListView):
    model = User
    template_name = 'security/user_list.html'
    context_object_name = 'items'


class UserUpdateView(AdminOnlyMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'security/user_form.html'
    success_url = reverse_lazy('security:user_list')

    def form_valid(self, form):
        editando_a_si_mismo = self.get_object().pk == self.request.user.pk
        pierde_rol_admin = 'Administrador' not in form.cleaned_data['groups'].values_list('name', flat=True)
        if editando_a_si_mismo and pierde_rol_admin:
            es_unico_admin = User.objects.filter(
                groups__name='Administrador', is_active=True
            ).count() == 1
            if es_unico_admin:
                messages.error(
                    self.request,
                    'No puedes quitarte el rol Administrador: eres el único '
                    'Administrador activo del sistema.'
                )
                return self.form_invalid(form)
        return super().form_valid(form)


class UserDeleteView(AdminOnlyMixin, DeleteView):
    model = User
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:user_list')

    def post(self, request, *args, **kwargs):
        if self.get_object().pk == request.user.pk:
            messages.error(request, 'No puedes eliminar tu propio usuario.')
            return redirect('security:user_list')
        return super().post(request, *args, **kwargs)


# === Roles / Group (lectura: cualquier autenticado; mutación: solo Administrador) ===
class GroupListView(LoginRequiredMixin, ListView):
    model = Group
    template_name = 'security/group_list.html'
    context_object_name = 'items'


class GroupCreateView(AdminOnlyMixin, CreateView):
    model = Group
    form_class = GroupForm
    template_name = 'security/group_form.html'
    success_url = reverse_lazy('security:group_list')


class GroupUpdateView(AdminOnlyMixin, UpdateView):
    model = Group
    form_class = GroupForm
    template_name = 'security/group_form.html'
    success_url = reverse_lazy('security:group_list')


class GroupDeleteView(AdminOnlyMixin, DeleteView):
    model = Group
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:group_list')

    def post(self, request, *args, **kwargs):
        if self.get_object().name == 'Administrador':
            messages.error(
                request,
                'No puedes eliminar el rol "Administrador": es requerido por el sistema.'
            )
            return redirect('security:group_list')
        return super().post(request, *args, **kwargs)


# === Permisos (solo lectura — sin crear/editar, ver nota abajo) ===
class PermissionListView(LoginRequiredMixin, ListView):
    model = Permission
    template_name = 'security/permission_list.html'
    context_object_name = 'items'
    queryset = Permission.objects.select_related('content_type')
