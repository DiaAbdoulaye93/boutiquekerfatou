import { Component, input, output } from '@angular/core';

export type MicState = 'idle' | 'recording' | 'busy';

/** Archimedean spiral r = r0 + k·θ around (100, 100), as an SVG path. */
function spiral(rotation: number): string {
  // Few turns per arm: with more, the arms read as concentric circles, not a swirl.
  const turns = 0.8;
  const steps = 160;
  const r0 = 52;
  const r1 = 96;
  const points: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const angle = rotation + t * turns * 2 * Math.PI;
    const r = r0 + (r1 - r0) * t;
    points.push(
      `${(100 + r * Math.cos(angle)).toFixed(1)},${(100 + r * Math.sin(angle)).toFixed(1)}`,
    );
  }
  return `M${points.join('L')}`;
}

// Six arms, 60° apart, computed once.
const ARMS = Array.from({ length: 6 }, (_, i) => spiral((i * Math.PI) / 3));

@Component({
  selector: 'app-mic-spiral',
  template: `
    <button
      type="button"
      class="spiral"
      [class.is-recording]="state() === 'recording'"
      [class.is-busy]="state() === 'busy'"
      [class.is-small]="small()"
      [disabled]="state() === 'busy'"
      [attr.aria-label]="state() === 'recording' ? 'Arrêter et envoyer' : 'Parler'"
      (click)="pressed.emit()"
    >
      <svg class="spiral-art" viewBox="0 0 200 200" aria-hidden="true">
        <defs>
          <linearGradient id="spiral-ink" x1="0" y1="0" x2="1" y2="1">
            <!-- CSS variables only resolve in style, not in presentation attributes. -->
            <stop offset="0" style="stop-color: var(--color-primary)" />
            <stop offset="1" style="stop-color: var(--color-accent)" />
          </linearGradient>
        </defs>
        <g class="spiral-arms">
          @for (d of arms; track $index) {
            <path [attr.d]="d" />
          }
        </g>
      </svg>
      <span class="spiral-ring"></span>
      <span class="spiral-core">
        @if (state() === 'recording') {
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="6" y="6" width="12" height="12" rx="3" />
          </svg>
        } @else {
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.9V21h2v-2.1a7 7 0 0 0 6-6.9h-2Z"
            />
          </svg>
        }
      </span>
    </button>
  `,
})
export class MicSpiral {
  readonly state = input<MicState>('idle');
  readonly small = input(false);
  readonly pressed = output<void>();
  readonly arms = ARMS;
}
