import re
from django.core.exceptions import ValidationError


def validate_only_letters(value):
    """Solo letras y espacios — sin números ni caracteres especiales."""
    if re.search(r'\d', value):
        raise ValidationError(
            'Este campo no puede contener números.',
            code='no_numbers',
        )
    if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\-']+$", value):
        raise ValidationError(
            'Solo se permiten letras, espacios y guiones.',
            code='invalid_chars',
        )


def validate_cedula_ec(value):
    """Valida cédula ecuatoriana (10 dígitos) o RUC (13 dígitos)."""
    if not value.isdigit():
        raise ValidationError('La CI/RUC debe contener solo números.', code='invalid_chars')

    if len(value) not in (10, 13):
        raise ValidationError(
            'La CI debe tener 10 dígitos o el RUC 13 dígitos.',
            code='invalid_length',
        )

    province = int(value[:2])
    if province < 1 or province > 24:
        raise ValidationError(
            f'Código de provincia inválido: {province}. Debe estar entre 01 y 24.',
            code='invalid_province',
        )

    third_digit = int(value[2])

    if third_digit < 6:
        # Persona natural (cédula o RUC de persona natural)
        coefficients = [2, 1, 2, 1, 2, 1, 2, 1, 2]
        total = 0
        for i in range(9):
            result = int(value[i]) * coefficients[i]
            if result > 9:
                result -= 9
            total += result
        verifier = 10 - (total % 10)
        if verifier == 10:
            verifier = 0
        if verifier != int(value[9]):
            raise ValidationError(
                'CI/RUC inválido. El dígito verificador no coincide.',
                code='invalid_verifier',
            )
        if len(value) == 13 and int(value[10:13]) < 1:
            raise ValidationError(
                'El número de establecimiento en el RUC debe ser mayor a 000.',
                code='invalid_establishment',
            )

    elif third_digit == 6:
        # Entidad del sector público (solo RUC de 13 dígitos)
        if len(value) != 13:
            raise ValidationError(
                'Las entidades públicas deben registrarse con RUC de 13 dígitos.',
                code='invalid_length_public',
            )
        coefficients = [3, 2, 7, 6, 5, 4, 3, 2]
        total = sum(int(value[i]) * coefficients[i] for i in range(8))
        verifier = 11 - (total % 11)
        if verifier == 11:
            verifier = 0
        if verifier != int(value[8]):
            raise ValidationError(
                'RUC inválido. El dígito verificador no coincide.',
                code='invalid_verifier',
            )

    elif third_digit == 9:
        # Sociedad privada (solo RUC de 13 dígitos)
        if len(value) != 13:
            raise ValidationError(
                'Las sociedades privadas deben registrarse con RUC de 13 dígitos.',
                code='invalid_length_private',
            )
        coefficients = [4, 3, 2, 7, 6, 5, 4, 3, 2]
        total = sum(int(value[i]) * coefficients[i] for i in range(9))
        verifier = 11 - (total % 11)
        if verifier == 11:
            verifier = 0
        if verifier != int(value[9]):
            raise ValidationError(
                'RUC inválido. El dígito verificador no coincide.',
                code='invalid_verifier',
            )

    else:
        raise ValidationError(
            'Tercer dígito inválido para CI/RUC ecuatoriano.',
            code='invalid_third',
        )

    return value


def calcular_digito_verificador_clave_acceso(digits_48):
    """Módulo 11 de la clave de acceso de comprobantes electrónicos SRI
    (48 dígitos -> 1 dígito verificador, total 49). Algoritmo DISTINTO al
    de validate_cedula_ec de arriba: acá los pesos son cíclicos 2,3,4,5,6,7
    (no una lista fija de 9 coeficientes), recorridos de derecha a
    izquierda sobre los 48 dígitos.
    """
    if not (isinstance(digits_48, str) and digits_48.isdigit() and len(digits_48) == 48):
        raise ValidationError(
            'La clave de acceso debe tener exactamente 48 dígitos numéricos antes del verificador.',
            code='invalid_length',
        )

    pesos = [2, 3, 4, 5, 6, 7]
    total = 0
    for i, digito in enumerate(reversed(digits_48)):
        peso = pesos[i % 6]
        total += int(digito) * peso

    residuo = total % 11
    resultado = 11 - residuo
    if resultado == 10:
        return 1
    if resultado == 11:
        return 0
    return resultado
