"""Azure model handoff check. Network access requires an explicit CLI option."""
from __future__ import annotations

import argparse
import json
import os

from dotenv import load_dotenv

from .deployment_check import ROOT, assistance_configuration_errors


def check_assistance(*, request_model: bool = False) -> dict:
    errors = assistance_configuration_errors()
    enabled = os.getenv("INTEGRITY_ASSISTED_ENABLED", "false").lower() == "true"
    budget = os.getenv("INTEGRITY_LLM_MAX_CALLS", "2")
    report = {
        "ok": not errors, "configuration_only": not request_model,
        "enabled": enabled, "errors": errors, "checks": [], "model_calls": 0,
        "notice": "La configuración no acredita conectividad ni calidad analítica. No se leen PDFs ni bases de revisión.",
    }
    if errors or not request_model:
        return report
    if not enabled or int(budget) == 0:
        report.update(ok=False, errors=["Habilite la asistencia con un presupuesto mayor que cero antes de solicitar la prueba."])
        return report

    from .analyzer.llm_reviewer import DOCUMENT_BRIEF_SCHEMA, SEMANTIC_SCHEMA, _request_json
    # Exercise the actual transport and schema validation with synthetic content.
    # This independent diagnostic makes up to two billable calls, not case jobs.
    probes = (
        ("semantic_contract", SEMANTIC_SCHEMA,
         'Prueba de integración con datos ficticios. No hay cláusulas para revisar. Devuelve {"candidates": []}.'),
        ("summary_contract", DOCUMENT_BRIEF_SCHEMA,
         "Prueba de integración con datos ficticios. Genera una síntesis breve conforme al esquema: "
         "convendría verificar la aceptación efectiva de equivalencias en un requisito técnico ficticio. "
         "No hay datos de una contratación real ni contexto histórico. No inventes información."),
    )
    for name, schema, prompt in probes:
        report["model_calls"] += 1
        try:
            _, provenance = _request_json(prompt, schema)
            report["checks"].append({"check": name, "ok": True, "provenance": provenance})
        except Exception:
            # SDK errors can contain endpoints, request content or credentials.
            report["checks"].append({"check": name, "ok": False,
                "message": "Compruebe red, credencial, deployment, versión de API, cuota y soporte del esquema. No se reintentó la solicitud."})
            report["ok"] = False
            break
    report["notice"] = "Prueba sintética de transporte y esquemas; no acredita precisión, cobertura documental ni preparación para acceso público. Puede tener costo."
    return report


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Comprobar configuración de Azure OpenAI sin documentos reales.")
    parser.add_argument("--request-model", action="store_true",
        help="Autoriza hasta dos solicitudes facturables con contenido ficticio; sin reintentos ni persistencia.")
    args = parser.parse_args()
    result = check_assistance(request_model=args.request_model)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
