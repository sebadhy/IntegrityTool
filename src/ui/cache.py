from __future__ import annotations

import streamlit as st

from src.analyzer.corpus_loader import (
    analyze_corpus_documents,
    load_corpus_documents,
    validate_corpus_state,
)
from src.analyzer.llm_reviewer import explain_priority_with_llm, generate_analyst_summary, generate_document_brief
from src.analyzer.review_synthesis import build_corpus_context


@st.cache_data(show_spinner=False)
def cached_generate_document_brief(
    document_text: str,
    prioritized_findings: list[dict],
    corpus_context: dict | None,
    normative_context: dict | None,
    model_name: str,
    base_url: str,
    contract_object: str = "No identificado en las primeras páginas",
) -> dict:
    return generate_document_brief(
        document_text,
        prioritized_findings,
        corpus_context,
        normative_context,
        contract_object=contract_object,
    )


@st.cache_data(show_spinner=False)
def cached_explain_priority_with_llm(
    priority: dict,
    corpus_context: dict | None,
    model_name: str,
    base_url: str,
) -> dict:
    return explain_priority_with_llm(priority, corpus_context)


@st.cache_data(show_spinner=False)
def cached_generate_analyst_summary(
    all_findings: list[dict],
    corpus_context: dict | None,
    document_text: str,
    contract_object: str,
    model_name: str,
    base_url: str,
) -> dict:
    return generate_analyst_summary(
        all_findings=all_findings,
        corpus_context=corpus_context,
        document_text=document_text,
        contract_object=contract_object,
    )


@st.cache_data(show_spinner=False)
def cached_corpus_context() -> dict:
    validation = validate_corpus_state()
    documents, issues = load_corpus_documents(force=False)
    analysis = analyze_corpus_documents(documents)
    total_processes = len({document.process_id for document in documents})
    return {
        "total_processes": total_processes,
        "total_documents": len(documents),
        "issues": issues,
        "validation": validation,
        "analysis": analysis,
        "context": build_corpus_context(analysis, total_processes),
    }
