export type Priority = "alta" | "media" | "baja";
export type ReviewState = "pending" | "confirmed" | "discarded" | "followup";
export type Evidence = {
  page: number;
  section: string;
  text: string;
  matched_text?: string;
  document_id: string;
  document_name: string;
  role: string;
  version: string;
  rects?: number[][];
  location_precision?: string;
};
export type ReviewItem = {
  id: string;
  title: string;
  pattern_id: string;
  dimension: string;
  dimension_label: string;
  priority: Priority;
  explanation: string;
  evidence: Evidence[];
  occurrence_count: number;
  mitigants: string[];
  questions: string[];
  limitations: string[];
  priority_factors: string[];
  sources: string[];
  analysis_methods?: string[];
  historical_context: {
    frequency_label?: string;
    comparative_comment?: string;
  };
  assisted_explanation?: string;
};
export type CaseDocument = {
  id: string;
  name: string;
  role: string;
  version: string;
  sha256: string;
  size: number;
  supersedes: string | null;
  metadata?: Record<string, string>;
  analysis?: {
    page_count: number;
    analyzed_at: string;
    analysis_key: string;
    page_statuses: { page: number; status: string }[];
  };
};
export type Review = {
  state: ReviewState;
  comment: string;
  reviewer: string;
  updated_at: string;
};
export type CaseSummary = {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
};
export type ReviewCase = CaseSummary & {
  error?: string;
  documents: CaseDocument[];
  reviews: Record<string, Review>;
  result: null | {
    documents: CaseDocument[];
    items: ReviewItem[];
    summary: string;
    assisted_summary?: string;
    semantic_review?: {
      status: string;
      accepted_count?: number;
      rejected_count?: number;
      visible_semantic_item_count?: number;
      coverage: null | {
        active_clause_count: number;
        selected_clause_count: number;
        partial: boolean;
        limitation: string;
      };
    };
    messages: string[];
    provenance: {
      engine_version: string;
      taxonomy_sha256: string;
      rule_version?: string;
      taxonomy_archived?: boolean;
      service_version?: string;
      finished_at?: string;
    };
    assistance: {
      status: string;
      calls: {
        purpose: string;
        item_id: string | null;
        status: string;
        provider?: string;
        model?: string;
        input_tokens?: number;
        output_tokens?: number;
        cached: boolean;
      }[];
    };
    version_changes: {
      pattern_id: string;
      title: string;
      previous_document: string;
      current_document: string;
      previous_version?: string;
      current_version?: string;
      change: string;
      limitation: string;
      previous_evidence: Evidence[];
      current_evidence: Evidence[];
      removed_evidence?: Evidence[];
      added_evidence?: Evidence[];
      unchanged_reference_count?: number;
    }[];
    corpus: { total_processes?: number; scope?: string };
  };
};
export const PRIORITIES: Record<Priority, string> = {
  alta: "Revisión prioritaria",
  media: "Revisión sugerida",
  baja: "Revisión general",
};
export const STATES: Record<ReviewState, string> = {
  pending: "Pendiente",
  confirmed: "Revisada",
  discarded: "Descartada",
  followup: "Seguimiento",
};
export const ROLES: Record<string, string> = {
  pliego: "Pliego",
  especificaciones: "Especificaciones",
  adenda: "Adenda",
  anexo: "Anexo",
};
