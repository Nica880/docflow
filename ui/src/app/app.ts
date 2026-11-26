import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

interface NavItem {
  path: string;
  label: string;
  icon: string;
}

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  protected readonly nav: NavItem[] = [
    { path: '/pipeline', label: 'Pipeline', icon: '⚙' },
    { path: '/companies', label: 'Companies', icon: '▦' },
    { path: '/review', label: 'Review queue', icon: '✓' },
    { path: '/qa', label: 'Ask DocFlow', icon: '✦' },
    { path: '/eval', label: 'Evaluation', icon: '◔' },
  ];
}
