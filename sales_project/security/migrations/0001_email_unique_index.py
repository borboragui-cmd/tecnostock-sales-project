from django.db import migrations


class Migration(migrations.Migration):
    """
    Fuerza unicidad real de email en auth_user a nivel de base de datos.

    auth.User es un modelo de django.contrib.auth (no de una app propia de
    este proyecto), así que no se le puede agregar unique=True al campo
    email vía una AlterField normal desde acá — Django no reconocería el
    cambio de estado de un modelo que no pertenece a esta app. En su lugar,
    se crea un índice UNIQUE directo por SQL sobre la tabla auth_user, que
    SQLite sí soporta sin reescribir la tabla completa.

    Precondición: no debe haber emails duplicados en auth_user al momento
    de aplicar esta migración (verificado y corregido manualmente antes,
    ver HANDOFF.md sección 14). Si quedara algún duplicado, CREATE UNIQUE
    INDEX falla con un error explícito y la migración no se aplica.

    El índice es PARCIAL (WHERE email != '') a propósito: un UNIQUE index
    normal en SQLite trata '' como un valor real, no como NULL, así que
    dos usuarios sin email (patrón común: User.objects.create_user(...)
    sin pasar email, usado extensamente en los tests del proyecto) chocan
    entre sí como si fueran duplicados. El filtro deja pasar cualquier
    cantidad de emails vacíos, pero sigue exigiendo unicidad real en
    cuanto el email no está vacío.
    """

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE UNIQUE INDEX security_uq_auth_user_email "
                "ON auth_user (email) WHERE email != '';"
            ),
            reverse_sql=(
                "DROP INDEX security_uq_auth_user_email;"
            ),
        ),
    ]
