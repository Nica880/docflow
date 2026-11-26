import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  afterRenderEffect,
  input,
  viewChild,
} from '@angular/core';
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  ChartDataset,
  ChartOptions,
  ChartType,
  Filler,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js';
import { compactNumber } from '../core/format';

Chart.register(
  BarController,
  BarElement,
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
  Filler,
);

/** Thin standalone wrapper around chart.js; re-renders whenever any input signal changes. */
@Component({
  selector: 'app-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="chart-box" [style.height.px]="height()">
    <canvas #canvas [attr.aria-label]="ariaLabel()" role="img"></canvas>
  </div>`,
  styles: `
    .chart-box {
      position: relative;
      width: 100%;
    }
  `,
})
export class ChartComponent implements OnDestroy {
  readonly type = input<'bar' | 'line'>('bar');
  readonly labels = input<(string | number)[]>([]);
  readonly datasets = input<ChartDataset<'bar' | 'line'>[]>([]);
  readonly stacked = input(false);
  readonly horizontal = input(false);
  readonly height = input(260);
  readonly ariaLabel = input('chart');
  /** Value-axis tick format. */
  readonly valueFormat = input<'number' | 'compact' | 'percent'>('number');

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private chart?: Chart;

  constructor() {
    afterRenderEffect(() => {
      const el = this.canvas().nativeElement;
      const type = this.type() as ChartType;
      const stacked = this.stacked();
      const horizontal = this.horizontal();
      const fmt = this.valueFormat();
      const tick = (v: string | number): string => {
        const n = Number(v);
        if (fmt === 'percent') return `${Math.round(n * 100)}%`;
        if (fmt === 'compact') return compactNumber(n);
        return String(v);
      };
      const valueAxis = { stacked, beginAtZero: true, ticks: { callback: tick } };
      const categoryAxis = { stacked, grid: { display: false } };
      const options: ChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        indexAxis: horizontal ? 'y' : 'x',
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } },
        scales: horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis },
      };
      const data = { labels: this.labels(), datasets: this.datasets() };
      this.chart?.destroy();
      if (!el.getContext) return;
      try {
        this.chart = new Chart(el, { type, data: data as never, options });
      } catch {
        // Canvas unsupported (e.g. jsdom); the <canvas> element is still rendered.
        this.chart = undefined;
      }
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }
}
