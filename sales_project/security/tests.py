import io

from django.contrib.auth.models import User, AnonymousUser, Group
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.test import override_settings

from security.forms import UserUpdateForm
from security.templatetags.security_tags import has_group


def _setup_roles():
    """Corre el comando real setup_roles, silenciando su stdout en los tests."""
    call_command('setup_roles', stdout=io.StringIO())


class SecurityRolesSetupTests(TestCase):
    """Verifica que setup_roles cree los 3 roles y sea idempotente."""

    def setUp(self):
        _setup_roles()

    # 1. setup_roles crea los 3 roles esperados.
    def test_setup_roles_crea_los_3_roles(self):
        nombres = set(Group.objects.values_list('name', flat=True))
        self.assertEqual(nombres, {'Administrador', 'Vendedor', 'Analista de Compras'})

    # 2. Correr setup_roles dos veces no duplica Groups ni cambia el conteo de permisos.
    def test_setup_roles_es_idempotente(self):
        conteo_antes = {
            g.name: g.permissions.count() for g in Group.objects.all()
        }
        total_groups_antes = Group.objects.count()

        _setup_roles()

        self.assertEqual(Group.objects.count(), total_groups_antes)
        conteo_despues = {
            g.name: g.permissions.count() for g in Group.objects.all()
        }
        self.assertEqual(conteo_antes, conteo_despues)


class RegisterViewTests(TestCase):
    """Registro público con selección de rol (security:register)."""

    def setUp(self):
        _setup_roles()
        self.rol_vendedor = Group.objects.get(name='Vendedor')

    # 1. Registro con role válido crea el User y lo asigna al Group correcto.
    def test_registro_con_rol_valido_asigna_el_grupo(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            r = client.post('/security/register/', {
                'username': 'nuevo_vendedor',
                'first_name': 'Ana',
                'last_name': 'Torres',
                'email': 'ana@test.com',
                'cedula': '1000000008',
                'password1': 'ClaveSegura!2026',
                'password2': 'ClaveSegura!2026',
                'role': self.rol_vendedor.pk,
            })
            self.assertEqual(r.status_code, 302)

        user = User.objects.get(username='nuevo_vendedor')
        self.assertTrue(user.groups.filter(name='Vendedor').exists())

    # 2. Registro sin seleccionar role falla la validación del form y no crea el User.
    def test_registro_sin_rol_no_crea_usuario(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            r = client.post('/security/register/', {
                'username': 'sin_rol',
                'first_name': 'Ana',
                'last_name': 'Torres',
                'email': 'ana2@test.com',
                'cedula': '1000000016',
                'password1': 'ClaveSegura!2026',
                'password2': 'ClaveSegura!2026',
                # 'role' omitido a propósito
            })
            self.assertEqual(r.status_code, 200)  # re-renderiza el form con errores, no redirige
            self.assertFormError(r.context['form'], 'role', 'Este campo es obligatorio.')

        self.assertFalse(User.objects.filter(username='sin_rol').exists())

    # 3. Registro con un email ya existente (case-insensitive) es rechazado.
    def test_registro_con_email_duplicado_es_rechazado(self):
        User.objects.create_user(
            username='ya_existe', email='Ana@Test.com', password='x',
        )
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            r = client.post('/security/register/', {
                'username': 'otro_usuario',
                'first_name': 'Otro',
                'last_name': 'Usuario',
                'email': 'ana@test.com',  # mismo email, distinto casing
                'cedula': '1000000024',
                'password1': 'ClaveSegura!2026',
                'password2': 'ClaveSegura!2026',
                'role': self.rol_vendedor.pk,
            })
            self.assertEqual(r.status_code, 200)
            self.assertFormError(
                r.context['form'], 'email',
                'Ya existe una cuenta registrada con este correo electrónico.'
            )
        self.assertFalse(User.objects.filter(username='otro_usuario').exists())

    # 4. Registro con un email nuevo (no usado antes) es aceptado.
    def test_registro_con_email_nuevo_es_aceptado(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            r = client.post('/security/register/', {
                'username': 'usuario_email_nuevo',
                'first_name': 'Nuevo',
                'last_name': 'Usuario',
                'email': 'nuevo_unico@test.com',
                'cedula': '1000000032',
                'password1': 'ClaveSegura!2026',
                'password2': 'ClaveSegura!2026',
                'role': self.rol_vendedor.pk,
            })
            self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(username='usuario_email_nuevo').exists())


class GroupRequiredMixinTests(TestCase):
    """Bloqueo real a nivel de servidor (no solo de menú)."""

    def setUp(self):
        _setup_roles()
        self.vendedor = User.objects.create_user(username='vendedor_mixin', password='x')
        self.vendedor.groups.add(Group.objects.get(name='Vendedor'))

        self.compras = User.objects.create_user(username='compras_mixin', password='x')
        self.compras.groups.add(Group.objects.get(name='Analista de Compras'))

        self.admin_no_super = User.objects.create_user(username='admin_mixin', password='x')
        self.admin_no_super.groups.add(Group.objects.get(name='Administrador'))

        self.superuser_sin_grupos = User.objects.create_superuser(
            username='super_mixin', password='x', email='super@test.com',
        )

    # 1. Modelo nuevo: listados son de lectura abierta a cualquier rol
    # autenticado, ver HANDOFF_FASE2.md sección 1. UserListView ya no exige
    # rol Administrador, solo estar logueado.
    def test_vendedor_accede_a_user_list_lectura_abierta(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.vendedor)
            r = client.get('/security/users/')
            self.assertEqual(r.status_code, 200)

    # 2. Modelo nuevo: idem para GroupListView, ya no exige rol Administrador.
    def test_analista_compras_accede_a_group_list_lectura_abierta(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.compras)
            r = client.get('/security/roles/')
            self.assertEqual(r.status_code, 200)

    # 3. Usuario con Group 'Administrador' (no superuser) SÍ entra a /security/users/.
    def test_administrador_no_superuser_accede_a_user_list(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.admin_no_super)
            r = client.get('/security/users/')
            self.assertEqual(r.status_code, 200)

    # 4. Superusuario SIN ningún Group asignado también entra (bypass real de is_superuser).
    def test_superuser_sin_groups_accede_a_user_list(self):
        self.assertFalse(self.superuser_sin_grupos.groups.exists())

        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.superuser_sin_grupos)
            r = client.get('/security/users/')
            self.assertEqual(r.status_code, 200)

    # 5. Las vistas de MUTACIÓN siguen exigiendo rol Administrador —
    # el aflojamiento del modelo nuevo solo aplica a listados/detalle.
    # Vendedor bloqueado al intentar editar un usuario.
    def test_vendedor_bloqueado_en_user_update(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.vendedor)

            r = client.get(f'/security/users/{self.vendedor.pk}/edit/')
            self.assertEqual(r.status_code, 302)

            r = client.get(f'/security/users/{self.vendedor.pk}/edit/', follow=True)
            msgs = [str(m) for m in r.context['messages']]
            self.assertTrue(any('no tienes permiso' in m.lower() for m in msgs))

    # 6. Analista de Compras bloqueado al intentar eliminar un usuario.
    def test_analista_compras_bloqueado_en_user_delete(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.compras)

            r = client.get(f'/security/users/{self.compras.pk}/delete/')
            self.assertEqual(r.status_code, 302)

            r = client.get(f'/security/users/{self.compras.pk}/delete/', follow=True)
            msgs = [str(m) for m in r.context['messages']]
            self.assertTrue(any('no tienes permiso' in m.lower() for m in msgs))

    # 7. Vendedor bloqueado al intentar crear un rol.
    def test_vendedor_bloqueado_en_group_create(self):
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.vendedor)

            r = client.get('/security/roles/create/')
            self.assertEqual(r.status_code, 302)

            r = client.get('/security/roles/create/', follow=True)
            msgs = [str(m) for m in r.context['messages']]
            self.assertTrue(any('no tienes permiso' in m.lower() for m in msgs))

    # 8. Analista de Compras bloqueado al intentar editar un rol (usa el
    # Group 'Vendedor', no 'Administrador', para no pisar el fix del
    # hallazgo 3 de la auditoría anterior sobre GroupDeleteView).
    def test_analista_compras_bloqueado_en_group_update(self):
        rol_vendedor = Group.objects.get(name='Vendedor')
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.compras)

            r = client.get(f'/security/roles/{rol_vendedor.pk}/edit/')
            self.assertEqual(r.status_code, 302)

            r = client.get(f'/security/roles/{rol_vendedor.pk}/edit/', follow=True)
            msgs = [str(m) for m in r.context['messages']]
            self.assertTrue(any('no tienes permiso' in m.lower() for m in msgs))

    # 9. Administrador (no superuser) SÍ puede entrar a las 4 URLs de
    # mutación de arriba — confirma que la protección es por rol, no que
    # se rompió para todos.
    def test_administrador_no_superuser_accede_a_las_4_vistas_de_mutacion(self):
        rol_vendedor = Group.objects.get(name='Vendedor')
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(self.admin_no_super)

            r = client.get(f'/security/users/{self.vendedor.pk}/edit/')
            self.assertEqual(r.status_code, 200)

            r = client.get(f'/security/users/{self.compras.pk}/delete/')
            self.assertEqual(r.status_code, 200)

            r = client.get('/security/roles/create/')
            self.assertEqual(r.status_code, 200)

            r = client.get(f'/security/roles/{rol_vendedor.pk}/edit/')
            self.assertEqual(r.status_code, 200)


class EmailUniquenessTests(TestCase):
    """Punto 5.2 del roadmap: unicidad real de email (índice UNIQUE en
    auth_user, ver security/migrations/0001_email_unique_index.py) +
    validación de formulario en UserUpdateForm."""

    def setUp(self):
        _setup_roles()
        self.user_a = User.objects.create_user(
            username='usuario_a', email='ocupado@test.com', password='x',
        )
        self.user_b = User.objects.create_user(
            username='usuario_b', email='libre@test.com', password='x',
        )

    # 1. El índice UNIQUE de la migración 0001 rechaza duplicados a nivel de BD,
    # incluso saltándose la validación de formulario (ej. otro punto de entrada
    # como el admin de Django o un script).
    def test_indice_unique_bloquea_email_duplicado_a_nivel_de_bd(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username='usuario_c', email='ocupado@test.com', password='x',
                )
        self.assertFalse(User.objects.filter(username='usuario_c').exists())

    # 2. UserUpdateForm rechaza editar a un usuario con el email de OTRO usuario.
    def test_user_update_form_rechaza_email_de_otro_usuario(self):
        form = UserUpdateForm(
            data={
                'username': 'usuario_b',
                'first_name': '', 'last_name': '',
                'email': 'ocupado@test.com',  # email de user_a
                'is_active': True,
                'groups': [],
            },
            instance=self.user_b,
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Ya existe una cuenta registrada con este correo electrónico.',
            form.errors['email'],
        )

    # 3. UserUpdateForm permite guardar sin cambios (mismo email propio) —
    # el exclude(pk=self.instance.pk) no debe auto-rechazar al dueño del email.
    def test_user_update_form_permite_guardar_su_propio_email_sin_cambios(self):
        form = UserUpdateForm(
            data={
                'username': 'usuario_a',
                'first_name': '', 'last_name': '',
                'email': 'ocupado@test.com',  # su propio email, sin cambios
                'cedula': '1000000040',
                'is_active': True,
                'groups': [],
            },
            instance=self.user_a,
        )
        self.assertTrue(form.is_valid(), form.errors)

    # 4. Lo mismo pero por HTTP real, como Administrador, contra otro usuario.
    def test_administrador_no_puede_asignar_email_duplicado_via_user_update_view(self):
        admin = User.objects.create_user(username='admin_email_test', password='x')
        admin.groups.add(Group.objects.get(name='Administrador'))

        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            client.force_login(admin)
            r = client.post(f'/security/users/{self.user_b.pk}/edit/', {
                'username': 'usuario_b',
                'first_name': '', 'last_name': '',
                'email': 'ocupado@test.com',
                'is_active': True,
                'groups': [],
            })
            self.assertEqual(r.status_code, 200)  # re-renderiza con error, no redirige
            self.assertFormError(
                r.context['form'], 'email',
                'Ya existe una cuenta registrada con este correo electrónico.'
            )

        self.user_b.refresh_from_db()
        self.assertEqual(self.user_b.email, 'libre@test.com')  # no se modificó


class CedulaUsuarioTests(TestCase):
    """Requerimiento agregado fuera de los 5 puntos originales de Fase 3:
    campo cedula en el registro (UserProfile, OneToOneField a User —
    no se migró a AUTH_USER_MODEL custom, mismo criterio que la
    unicidad de email en el punto 5.2). Formato validado con
    shared.validators.validate_cedula_ec (módulo 10), unicidad real vía
    UserProfile.cedula (unique=True)."""

    def setUp(self):
        _setup_roles()
        self.rol_vendedor = Group.objects.get(name='Vendedor')

    def _post_registro(self, **overrides):
        data = {
            'username': 'usuario_cedula',
            'first_name': 'Cedula',
            'last_name': 'Test',
            'email': 'cedula@test.com',
            'cedula': '1000000057',
            'password1': 'ClaveSegura!2026',
            'password2': 'ClaveSegura!2026',
            'role': self.rol_vendedor.pk,
        }
        data.update(overrides)
        with override_settings(ALLOWED_HOSTS=['testserver']):
            client = Client()
            return client.post('/security/register/', data)

    # 1. Cédula con formato inválido (dígito verificador no coincide) es
    # rechazada — reusa validate_cedula_ec, no reimplementa el módulo 10.
    def test_cedula_con_formato_invalido_es_rechazada(self):
        r = self._post_registro(cedula='1234567890')
        self.assertEqual(r.status_code, 200)
        self.assertFormError(
            r.context['form'], 'cedula',
            'CI/RUC inválido. El dígito verificador no coincide.',
        )
        self.assertFalse(User.objects.filter(username='usuario_cedula').exists())

    # 2. Cédula ya usada por otro usuario es rechazada.
    def test_cedula_duplicada_es_rechazada(self):
        from security.models import UserProfile
        otro = User.objects.create_user(username='ya_tiene_cedula', password='x')
        UserProfile.objects.create(user=otro, cedula='1000000057')

        r = self._post_registro(username='usuario_cedula_dup', email='dup@test.com')
        self.assertEqual(r.status_code, 200)
        self.assertFormError(
            r.context['form'], 'cedula',
            'Ya existe una cuenta registrada con esta cédula.',
        )
        self.assertFalse(User.objects.filter(username='usuario_cedula_dup').exists())

    # 3. Cédula válida y única es aceptada: crea el User y su UserProfile.
    def test_cedula_valida_y_unica_es_aceptada(self):
        from security.models import UserProfile
        r = self._post_registro()
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(username='usuario_cedula')
        self.assertEqual(user.profile.cedula, '1000000057')
        self.assertTrue(UserProfile.objects.filter(cedula='1000000057').exists())

    # 4. UserUpdateForm no se autorrechaza al guardar sin cambiar la
    # cédula propia (mismo patrón que el exclude(pk=...) de email).
    def test_user_update_form_permite_guardar_su_propia_cedula_sin_cambios(self):
        from security.models import UserProfile
        from security.forms import UserUpdateForm

        user = User.objects.create_user(username='con_cedula_propia', password='x')
        UserProfile.objects.create(user=user, cedula='1000000057')

        form = UserUpdateForm(
            data={
                'username': 'con_cedula_propia',
                'first_name': '', 'last_name': '',
                'email': '',
                'cedula': '1000000057',  # su propia cédula, sin cambios
                'is_active': True,
                'groups': [],
            },
            instance=user,
        )
        self.assertTrue(form.is_valid(), form.errors)

    # 5. Auditoría 2026-07-17, hallazgo #1: un Administrador debe poder
    # editar CUALQUIER dato (ej. is_active) de un usuario preexistente sin
    # UserProfile (los 12 usuarios previos a este punto) sin verse
    # obligado a inventarle una cédula. Antes del fix, cedula era
    # CharField sin required=False -> este test fallaba con
    # is_valid()==False. Reproduce el bug encontrado en la auditoría
    # exactamente como se probó ahí (editar 'admin', sin mandar cedula).
    def test_user_update_form_permite_editar_usuario_sin_perfil_sin_cedula(self):
        usuario_legacy = User.objects.create_user(username='legacy_sin_perfil', password='x')
        self.assertFalse(hasattr(usuario_legacy, 'profile'))

        form = UserUpdateForm(
            data={
                'username': 'legacy_sin_perfil',
                'first_name': '', 'last_name': '',
                'email': '',
                'is_active': False,  # el cambio real que se quiere guardar
                'groups': [],
                # 'cedula' omitida a propósito, igual que en la auditoría
            },
            instance=usuario_legacy,
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertFalse(user.is_active)
        self.assertFalse(hasattr(user, 'profile'))  # no se le inventó un perfil

    # 6. Aunque cedula ahora sea opcional, la unicidad se sigue
    # respetando cuando SÍ se proporciona un valor — el fix del hallazgo
    # #1 no debilitó la regla de unicidad, solo la hizo condicional.
    def test_user_update_form_sigue_validando_unicidad_si_se_da_cedula(self):
        from security.models import UserProfile
        otro = User.objects.create_user(username='ya_tiene_cedula_2', password='x')
        UserProfile.objects.create(user=otro, cedula='1000000057')

        usuario_legacy = User.objects.create_user(username='legacy_sin_perfil_2', password='x')
        form = UserUpdateForm(
            data={
                'username': 'legacy_sin_perfil_2',
                'first_name': '', 'last_name': '',
                'email': '',
                'cedula': '1000000057',  # cédula de OTRO usuario
                'is_active': True,
                'groups': [],
            },
            instance=usuario_legacy,
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Ya existe una cuenta registrada con esta cédula.',
            form.errors['cedula'],
        )


class HasGroupTemplateTagTests(TestCase):
    """Filtro has_group, probado directamente como función (sin renderizar HTML)."""

    def setUp(self):
        _setup_roles()
        self.vendedor = User.objects.create_user(username='vendedor_tag', password='x')
        self.vendedor.groups.add(Group.objects.get(name='Vendedor'))

        self.superuser_sin_grupos = User.objects.create_superuser(
            username='super_tag', password='x', email='super_tag@test.com',
        )

    # 1. Un Vendedor tiene el rol 'Vendedor'.
    def test_has_group_true_para_su_propio_rol(self):
        self.assertTrue(has_group(self.vendedor, 'Vendedor'))

    # 2. Un Vendedor NO tiene el rol 'Administrador'.
    def test_has_group_false_para_rol_ajeno(self):
        self.assertFalse(has_group(self.vendedor, 'Administrador'))

    # 3. Un superusuario sin Groups asignados igual pasa cualquier chequeo (bypass).
    def test_has_group_true_para_superuser_sin_groups(self):
        self.assertFalse(self.superuser_sin_grupos.groups.exists())
        self.assertTrue(has_group(self.superuser_sin_grupos, 'Administrador'))

    # 4. Un usuario no autenticado nunca tiene ningún rol.
    def test_has_group_false_para_usuario_anonimo(self):
        self.assertFalse(has_group(AnonymousUser(), 'Vendedor'))
