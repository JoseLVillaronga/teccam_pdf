"""
Metadatos adicionales de documento (Vigencia y Fecha de publicación).

Módulo compartido entre ``app.py`` (extracción/edición) y ``rag_api.py``
(índice RAG) para que las constantes y la normalización de fecha sean idénticas
en ambos servicios y no se duplique lógica. MongoDB es schemaless, así que estos
campos se agregan como claves nuevas sin alterar la estructura existente.
"""

import re
from datetime import datetime
from typing import Optional

#: Valores válidos/posibles para el campo ``vigencia``.
VIGENCIA_OPCIONES = [
    'vigente',
    'derogado',
    'parcialmente-vigente',
    'en-proyecto',
    'NA (no aplica)',
]

#: Valor por defecto para ``vigencia``.
VIGENCIA_DEFECTO = 'NA (no aplica)'

#: Campos nuevos de metadatos que se esperan en los documentos.
CAMPOS_METADATOS = ('vigencia', 'fecha_publicacion')

# Mapas de meses (español e inglés, completos y abreviados) para parsear fechas
# en texto libre y devolverlas en formato ISO 8601 compatible con LLMs.
_MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12,
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6, 'jul': 7,
    'ago': 8, 'sep': 9, 'set': 9, 'oct': 10, 'nov': 11, 'dic': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11,
    'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7,
    'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

_ISO_FULL = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_ISO_MONTH = re.compile(r'^\d{4}-\d{2}$')
_ISO_YEAR = re.compile(r'^\d{4}$')
_NUM = re.compile(r'^\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\s*$')
_MES_DIA_ANYO = re.compile(
    r'^\s*(\d{1,2})\s+(?:de\s+)?([A-Za-záéíóúñÁÉÍÓÚÑ]+)\s+(?:de\s+)?(\d{4})\s*$',
    re.IGNORECASE,
)
_MES_ANYO = re.compile(
    r'^\s*([A-Za-záéíóúñÁÉÍÓÚÑ]+)\s+(?:de\s+)?(\d{4})\s*$',
    re.IGNORECASE,
)
_ANYO_SUELTO = re.compile(r'\b(19|20)\d{2}\b')


def _iso(mes: int, dia: Optional[int], anyo: int) -> Optional[str]:
    """Devuelve una cadena ISO (YYYY-MM-DD o YYYY-MM) o None si es inválida."""
    try:
        if dia is not None:
            return datetime(anyo, mes, dia).date().isoformat()
        return f"{anyo:04d}-{mes:02d}"
    except ValueError:
        return None


def normalizar_fecha_publicacion(valor: Optional[str]) -> str:
    """
    Normaliza una fecha de publicación en texto libre a formato ISO 8601,
    compatible con el consumo por parte de LLMs (``YYYY-MM-DD`` o parcial
    ``YYYY-MM`` / ``YYYY`` según la información disponible).

    Acepta ISO ya normalizada, fechas numéricas (dd/mm/aaaa, con punto o guion),
    fechas con nombre de mes en español o inglés (p. ej. "15 de marzo de 2020",
    "marzo 2020", "2020-03"). Si no se puede interpretar, devuelve el valor
    original recortado, sin perder datos.

    :param valor: Texto libre de la fecha de publicación (o ``None``).
    :return: Cadena normalizada o el valor recortado original.
    """
    if valor is None:
        return ''
    v = ' '.join(str(valor).strip().split())
    if not v:
        return ''

    # Ya está en formato ISO
    if _ISO_FULL.match(v) or _ISO_MONTH.match(v) or _ISO_YEAR.match(v):
        return v

    # Numérico (día primero, típico de es-AR): dd/mm/aaaa
    m = _NUM.match(v)
    if m:
        g1, g2, g3 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        iso = _iso(g2, g1, g3)  # d/m/y
        if iso:
            return iso
        iso = _iso(g1, g2, g3)  # m/d/y (fallback)
        if iso:
            return iso

    # "15 de marzo de 2020" / "15 marzo 2020" / "15 Mar, 2020"
    m = _MES_DIA_ANYO.match(v)
    if m:
        mes = _MESES.get(m.group(2).lower())
        if mes:
            iso = _iso(mes, int(m.group(1)), int(m.group(3)))
            if iso:
                return iso

    # "marzo de 2020" / "marzo 2020" / "March 2020"
    m = _MES_ANYO.match(v)
    if m:
        mes = _MESES.get(m.group(1).lower())
        if mes:
            iso = _iso(mes, None, int(m.group(2)))
            if iso:
                return iso

    # Último intento: extraer el año si aparece en otra forma
    y = _ANYO_SUELTO.search(v)
    if y:
        return y.group(0)

    # Sin interpretación posible: conservar el valor original recortado
    return v
