import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Answer,
  CompanyDetail,
  CompanyOut,
  EvalSummary,
  FilingDetail,
  FilingOut,
  Page,
  PipelineOverview,
  ReviewAction,
  ReviewTaskOut,
  SectionText,
} from './api.models';

export const API_BASE = '/api';

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

/** Builds `/api/<path>?k=v` omitting empty params; path segments are URL-encoded by callers. */
export function buildUrl(path: string, params: QueryParams = {}): string {
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  const clean = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE}${clean}${qs ? `?${qs}` : ''}`;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  health(): Observable<{ status: string }> {
    return this.http.get<{ status: string }>(buildUrl('/health'));
  }

  pipelineOverview(): Observable<PipelineOverview> {
    return this.http.get<PipelineOverview>(buildUrl('/pipeline/overview'));
  }

  companies(params: {
    q?: string;
    sector?: string;
    limit?: number;
    offset?: number;
  }): Observable<Page<CompanyOut>> {
    return this.http.get<Page<CompanyOut>>(buildUrl('/companies', params));
  }

  company(cik: number | string): Observable<CompanyDetail> {
    return this.http.get<CompanyDetail>(buildUrl(`/companies/${encodeURIComponent(cik)}`));
  }

  filings(params: {
    cik?: number;
    form_type?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Observable<Page<FilingOut>> {
    return this.http.get<Page<FilingOut>>(buildUrl('/filings', params));
  }

  filing(accession: string): Observable<FilingDetail> {
    return this.http.get<FilingDetail>(buildUrl(`/filings/${encodeURIComponent(accession)}`));
  }

  section(accession: string, item: string): Observable<SectionText> {
    return this.http.get<SectionText>(
      buildUrl(`/filings/${encodeURIComponent(accession)}/sections/${encodeURIComponent(item)}`),
    );
  }

  reviewTasks(params: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Observable<Page<ReviewTaskOut>> {
    return this.http.get<Page<ReviewTaskOut>>(buildUrl('/review', params));
  }

  review(id: number, action: ReviewAction): Observable<ReviewTaskOut> {
    return this.http.post<ReviewTaskOut>(buildUrl(`/review/${id}`), action);
  }

  ask(question: string): Observable<Answer> {
    return this.http.post<Answer>(buildUrl('/qa'), { question });
  }

  evalSummary(): Observable<EvalSummary> {
    return this.http.get<EvalSummary>(buildUrl('/eval'));
  }
}
