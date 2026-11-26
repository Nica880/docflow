/**
 * TypeScript mirror of the FastAPI contract in `api/schemas.py`.
 * Dates/datetimes are ISO-8601 strings on the wire.
 */

export interface Page<T> {
  items: T[];
  total: number;
}

// --- pipeline ------------------------------------------------------------------------------

export interface PipelineRunOut {
  run_id: string;
  dag_id: string;
  started_at: string;
  finished_at: string | null;
  docs_in: number;
  docs_ok: number;
  docs_quarantined: number;
  status: string;
  duration_s?: number | null;
}

export interface QuarantineOut {
  id: number;
  accession_no: string;
  stage: string;
  error: string;
  created_at: string;
}

export interface ThroughputPoint {
  day: string;
  filings: number;
}

export type TotalsKey =
  'companies' | 'filings' | 'sections' | 'chunks' | 'extractions' | 'open_reviews' | 'quarantined';

export interface PipelineOverview {
  totals: Record<string, number>;
  filings_by_status: Record<string, number>;
  queue?: Record<string, number> | null;
  runs: PipelineRunOut[];
  quarantine: QuarantineOut[];
  throughput: ThroughputPoint[];
}

// --- companies / filings -------------------------------------------------------------------

export interface CompanyOut {
  cik: number;
  name: string;
  ticker: string | null;
  sic_code: string | null;
  sector: string | null;
  filings: number;
}

export interface FinancialPoint {
  fiscal_year: number;
  revenue: number | null;
  net_income: number | null;
  operating_cash_flow: number | null;
  /** "llm" | "xbrl" */
  source: string;
}

export interface RiskPoint {
  year: number;
  category: string;
  mentions: number;
}

export interface FilingOut {
  accession_no: string;
  cik: number;
  company_name?: string | null;
  form_type: string;
  filed_at: string;
  period_end: string | null;
  source_url: string;
  status: string;
  size_bytes?: number | null;
}

export interface CompanyDetail {
  company: CompanyOut;
  financials: FinancialPoint[];
  risks: RiskPoint[];
  filings: FilingOut[];
}

export interface SectionOut {
  id: number;
  item: string;
  title: string | null;
  char_count: number;
}

export interface ExtractionOut {
  id: number;
  schema_name: string;
  schema_version: string;
  model: string;
  prompt_version: string;
  payload: Record<string, unknown>;
  confidence: Record<string, unknown>;
  latency_ms: number;
  created_at: string;
}

export interface FilingDetail {
  filing: FilingOut;
  sections: SectionOut[];
  extractions: ExtractionOut[];
}

export interface Highlight {
  field: string;
  value: string;
  snippet: string;
  start: number;
  end: number;
}

export interface SectionText {
  accession_no: string;
  item: string;
  title: string | null;
  text: string;
  highlights: Highlight[];
}

// --- review queue --------------------------------------------------------------------------

export type ReviewStatus = 'open' | 'approved' | 'corrected' | 'rejected';

export interface ReviewTaskOut {
  id: number;
  extraction_id: number;
  accession_no: string;
  company_name: string | null;
  schema_name: string;
  field: string;
  value: string | null;
  confidence: number;
  reason: string | null;
  status: string;
  reviewer_value: string | null;
  reviewed_at: string | null;
  snippet?: string | null;
}

export interface ReviewAction {
  action: 'approve' | 'correct' | 'reject';
  value?: string | null;
}

// --- Q&A agent -----------------------------------------------------------------------------

export interface Question {
  question: string;
}

export interface Citation {
  accession_no: string;
  item: string | null;
  company: string | null;
  snippet: string;
}

export interface ToolCallOut {
  tool: string;
  input: Record<string, unknown>;
  output_preview: string;
}

export interface Answer {
  answer: string;
  citations: Citation[];
  tool_calls: ToolCallOut[];
  refused: boolean;
}

// --- evaluation ----------------------------------------------------------------------------

export interface EvalRunOut {
  id: number;
  model: string;
  prompt_version: string;
  n_docs: number;
  metrics: Record<string, unknown>;
  created_at: string;
}

export interface EvalSummary {
  runs: EvalRunOut[];
  confidence_threshold: number;
}
