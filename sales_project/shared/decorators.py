import logging
from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger('audit')

def audit_action(action_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user.username if request.user.is_authenticated else 'Anonymous'
            ip = request.META.get('REMOTE_ADDR', 'unknown')
            method = request.method
            timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            path = request.path
            
            logger.info(f'[AUDIT] {timestamp} | User: {user} | Action: {action_name} | Method: {method} | Path: {path} | IP: {ip}')
            print(f'\n[AUDIT] {timestamp} | User: {user} | Action: {action_name} | Method: {method} | Path: {path} | IP: {ip}')
            
            response = view_func(request, *args, **kwargs)
            
            if method == 'POST':
                print(f'[AUDIT] {timestamp} | COMPLETED: {action_name} by {user}')
            
            return response
        return wrapper
    return decorator


def group_required(group_names, redirect_url='/', error_message='No tienes permiso para acceder a esta opción.'):
    """
    Equivalente a GroupRequiredMixin (shared/mixins.py) pero para vistas
    basadas en función. El superusuario siempre pasa.
    Uso:
        @login_required
        @group_required(['Vendedor', 'Administrador'])
        def mi_vista(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser or request.user.groups.filter(name__in=group_names).exists():
                return view_func(request, *args, **kwargs)
            messages.error(request, error_message)
            return redirect(redirect_url)
        return wrapper
    return decorator


def staff_required(redirect_url='/', error_message='No tienes permiso para esta acción. Se requiere acceso de staff.'):
    """
    Equivalente a StaffRequiredMixin (shared/mixins.py) pero para
    vistas basadas en función.
    Uso:
        @login_required
        @staff_required(redirect_url='creditos_ventas:cuotas_pendientes')
        def mi_vista(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_staff:
                messages.error(request, error_message)
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
