import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ApiService, buildUrl } from './api.service';

describe('buildUrl', () => {
  it('prefixes /api and omits empty params', () => {
    expect(buildUrl('/companies', { q: '', sector: undefined, limit: 25, offset: 0 })).toBe(
      '/api/companies?limit=25&offset=0',
    );
  });

  it('encodes query values', () => {
    expect(buildUrl('companies', { q: 'AT&T inc' })).toBe('/api/companies?q=AT%26T%20inc');
  });
});

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('requests a filing section with encoded path segments', () => {
    api.section('0000320193-24-000123', '1A').subscribe();
    const req = http.expectOne('/api/filings/0000320193-24-000123/sections/1A');
    expect(req.request.method).toBe('GET');
    req.flush({ accession_no: '', item: '1A', title: null, text: '', highlights: [] });
  });

  it('posts review actions and questions as JSON bodies', () => {
    api.review(7, { action: 'correct', value: '42' }).subscribe();
    const review = http.expectOne('/api/review/7');
    expect(review.request.method).toBe('POST');
    expect(review.request.body).toEqual({ action: 'correct', value: '42' });
    review.flush({});

    api.ask('What is revenue?').subscribe();
    const qa = http.expectOne('/api/qa');
    expect(qa.request.body).toEqual({ question: 'What is revenue?' });
    qa.flush({ answer: '', citations: [], tool_calls: [], refused: false });
  });

  it('builds filtered review queue URLs', () => {
    api.reviewTasks({ status: 'open', limit: 100 }).subscribe();
    http.expectOne('/api/review?status=open&limit=100').flush({ items: [], total: 0 });
  });
});
