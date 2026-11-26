import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'pipeline' },
  {
    path: 'pipeline',
    title: 'Pipeline | DocFlow',
    loadComponent: () => import('./pages/pipeline/pipeline.page').then((m) => m.PipelinePage),
  },
  {
    path: 'companies',
    title: 'Companies | DocFlow',
    loadComponent: () => import('./pages/companies/companies.page').then((m) => m.CompaniesPage),
  },
  {
    path: 'companies/:cik',
    title: 'Company | DocFlow',
    loadComponent: () =>
      import('./pages/companies/company-detail.page').then((m) => m.CompanyDetailPage),
  },
  {
    path: 'filings/:accession',
    title: 'Filing | DocFlow',
    loadComponent: () => import('./pages/filing/filing.page').then((m) => m.FilingPage),
  },
  {
    path: 'review',
    title: 'Review queue | DocFlow',
    loadComponent: () => import('./pages/review/review.page').then((m) => m.ReviewPage),
  },
  {
    path: 'qa',
    title: 'Ask | DocFlow',
    loadComponent: () => import('./pages/qa/qa.page').then((m) => m.QaPage),
  },
  {
    path: 'eval',
    title: 'Evaluation | DocFlow',
    loadComponent: () => import('./pages/eval/eval.page').then((m) => m.EvalPage),
  },
  { path: '**', redirectTo: 'pipeline' },
];
