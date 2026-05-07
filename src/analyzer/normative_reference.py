from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormativeReference:
    principle: str
    review_criterion: str
    suggested_question: str


DEFAULT_REFERENCE = NormativeReference(
    principle="concurrencia / trato justo / transparencia",
    review_criterion=(
        "Validar si la condición se relaciona con el objeto contractual, está redactada "
        "con claridad y cuenta con justificación técnica proporcional."
    ),
    suggested_question=(
        "¿El requisito describe una necesidad verificable y permite participación en "
        "condiciones comparables?"
    ),
)

REFERENCE_BY_CATEGORY = {
    "Autorizaciones comerciales o de fabricante": NormativeReference(
        principle="concurrencia / igualdad / no discriminación",
        review_criterion=(
            "Validar si exigir canal comercial autorizado está funcionalmente justificado "
            "por garantía, soporte o naturaleza del bien."
        ),
        suggested_question=(
            "¿El requisito admite alternativas equivalentes o limita innecesariamente "
            "oferentes no vinculados al fabricante?"
        ),
    ),
    "Referencias a marca, origen o fabricante": NormativeReference(
        principle="concurrencia / igualdad / especificaciones relacionadas con bienes",
        review_criterion=(
            "Verificar si la referencia describe una necesidad funcional del bien y no "
            "una característica exclusiva de un proveedor."
        ),
        suggested_question=(
            "¿La referencia a marca, origen o fabricante admite equivalentes funcionales?"
        ),
    ),
    "Certificaciones específicas": NormativeReference(
        principle="concurrencia / proporcionalidad / mejor valor por dinero",
        review_criterion=(
            "Revisar si la certificación específica es necesaria para el objeto contractual "
            "y si existen estándares equivalentes aceptables."
        ),
        suggested_question=(
            "¿La certificación exigida es proporcional al bien o servicio requerido?"
        ),
    ),
    "Requisitos técnicos cerrados": NormativeReference(
        principle="claridad de especificaciones / concurrencia",
        review_criterion=(
            "Verificar si la especificación responde al objeto contractual y no a "
            "características de un proveedor."
        ),
        suggested_question=(
            "¿La especificación describe una necesidad funcional o reproduce características "
            "de una solución específica?"
        ),
    ),
    "Garantías, repuestos y postventa": NormativeReference(
        principle="mejor valor por dinero / proporcionalidad / concurrencia",
        review_criterion=(
            "Validar si las garantías, repuestos o postventa exigidos son proporcionales "
            "a la operación esperada y no cierran innecesariamente la participación."
        ),
        suggested_question=(
            "¿El nivel de garantía o postventa puede cumplirse mediante alternativas "
            "técnicamente equivalentes?"
        ),
    ),
    "Restricciones geográficas o de presencia local": NormativeReference(
        principle="igualdad / no discriminación / concurrencia",
        review_criterion=(
            "Revisar si la presencia local o condición geográfica es necesaria para "
            "ejecutar el contrato y está justificada por el objeto."
        ),
        suggested_question=(
            "¿La atención requerida puede cumplirse sin exigir presencia local permanente?"
        ),
    ),
    "Experiencia o capacidad excesivamente específica": NormativeReference(
        principle="trato justo / concurrencia / proporcionalidad",
        review_criterion=(
            "Validar si la experiencia solicitada guarda relación directa y proporcional "
            "con el objeto contractual."
        ),
        suggested_question=(
            "¿La experiencia requerida mide capacidad técnica real o restringe innecesariamente "
            "el universo de oferentes?"
        ),
    ),
    "Combinaciones de requisitos potencialmente limitantes": NormativeReference(
        principle="concurrencia / igualdad / justificación técnica",
        review_criterion=(
            "Analizar si la combinación acumulada de requisitos mantiene proporcionalidad "
            "y no eleva barreras de entrada sin justificación técnica."
        ),
        suggested_question=(
            "¿La combinación de requisitos es necesaria en conjunto o podría aceptarse "
            "cumplimiento equivalente?"
        ),
    ),
    "Completitud y trazabilidad documental": NormativeReference(
        principle="transparencia / claridad / consistencia entre pliego y anexos",
        review_criterion=(
            "Validar que el pliego, anexos, enlaces y referencias sean completos, accesibles "
            "y consistentes para todos los oferentes."
        ),
        suggested_question=(
            "¿La información necesaria para preparar la oferta está completa, disponible "
            "y trazable?"
        ),
    ),
    "Requisitos regulatorios o habituales": NormativeReference(
        principle="transparencia / habilitación administrativa / trato justo",
        review_criterion=(
            "Distinguir requisitos administrativos estándar de condiciones adicionales que "
            "podrían afectar participación."
        ),
        suggested_question=(
            "¿El requisito es una exigencia regulatoria habitual o incorpora condiciones "
            "adicionales no proporcionales?"
        ),
    ),
    "Elementos que favorecen concurrencia": NormativeReference(
        principle="concurrencia / igualdad / apertura competitiva",
        review_criterion=(
            "Verificar que el elemento de apertura sea claro, aplicable y consistente con "
            "los demás requisitos del pliego."
        ),
        suggested_question=(
            "¿La cláusula de apertura se aplica efectivamente durante la evaluación?"
        ),
    ),
}

REFERENCE_BY_PATTERN = {
    "distribuidor autorizado": REFERENCE_BY_CATEGORY[
        "Autorizaciones comerciales o de fabricante"
    ],
    "comercializador autorizado": REFERENCE_BY_CATEGORY[
        "Autorizaciones comerciales o de fabricante"
    ],
    "certificación ISO": REFERENCE_BY_CATEGORY["Certificaciones específicas"],
    "ficha técnica": REFERENCE_BY_CATEGORY["Requisitos técnicos cerrados"],
    "fabricante": REFERENCE_BY_CATEGORY["Referencias a marca, origen o fabricante"],
    "marca": REFERENCE_BY_CATEGORY["Referencias a marca, origen o fabricante"],
}


def get_normative_reference(signal: dict) -> dict[str, str]:
    pattern = str(signal.get("patrón detectado", ""))
    category = str(signal.get("categoría de revisión") or signal.get("categoría", ""))
    reference = (
        REFERENCE_BY_PATTERN.get(pattern)
        or REFERENCE_BY_CATEGORY.get(category)
        or DEFAULT_REFERENCE
    )
    return {
        "principio_normativo_relacionado": reference.principle,
        "criterio_normativo_de_revision": reference.review_criterion,
        "pregunta_normativa_sugerida": reference.suggested_question,
    }


NORMATIVE_SOURCES = [
    {
        "name": "Ley Orgánica del Sistema Nacional de Contratación Pública (LOSNCP)",
        "reference": "Principios de legalidad, trato justo, igualdad, calidad, concurrencia, transparencia, publicidad y participación nacional.",
        "url": "https://portal.compraspublicas.gob.ec/sercop/normativa/",
    },
    {
        "name": "Reglamento General a la LOSNCP (RLOSNCP)",
        "reference": "Reglas de desarrollo aplicables a fases preparatoria, precontractual y contractual, según régimen vigente.",
        "url": "https://portal.compraspublicas.gob.ec/sercop/normativa/",
    },
    {
        "name": "Resoluciones SERCOP vigentes y régimen de transición",
        "reference": "Directrices transitorias y normativa secundaria aplicable cuando corresponda.",
        "url": "https://portal.compraspublicas.gob.ec/sercop/cat_normativas/nor_res_ext",
    },
]
