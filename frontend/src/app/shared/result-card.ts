import { Component, computed, input } from '@angular/core';

import { formatValue, LABELS } from '../core/format';
import { Card, CardData, CardValue } from '../core/models';

interface Figure {
  label: string;
  value: string;
}

interface Table {
  columns: string[];
  rows: CardData[];
  barKey: string | null;
  barMax: number;
}

// Top-level figures shown as big numbers, in this order when present.
const FIGURE_KEYS = [
  'chiffre_affaires_xof',
  'marge_xof',
  'nombre_de_factures',
  'panier_moyen_xof',
  'total_du_xof',
  'nombre_de_clients',
  'nombre_total',
  'montant_total_xof',
  'reste_a_payer_xof',
  'achats_30_derniers_jours_xof',
  'passages_30_derniers_jours',
  'quantite',
  'nombre_de_ventes',
  'moyenne_par_jour',
  'stock',
  'montant_xof',
];
// Columns never shown in tables (redundant or too wide for a phone).
const HIDDEN_COLUMNS = new Set(['unite', 'categorie', 'dernier_remboursement', 'marge_xof']);
const TABLE_KEYS = ['produits', 'factures', 'clients', 'lignes', 'dernieres_factures'];
// Value drawn as a bar under the first column, per tool.
const BAR_KEYS: Record<string, string> = {
  chiffre_affaires: 'chiffre_affaires_xof',
  dettes_clients: 'reste_a_payer_xof',
};
const CRITERION_KEYS: Record<string, string> = {
  nombre_de_ventes: 'nombre_de_ventes',
  quantite: 'quantite',
  chiffre_affaires: 'chiffre_affaires_xof',
  marge: 'marge_xof',
};

@Component({
  selector: 'app-result-card',
  template: `
    <article class="result">
      <header class="result-head">
        <h3>{{ heading() }}</h3>
        @if (period(); as p) {
          <span class="pill">{{ p }}</span>
        }
      </header>

      @if (figures().length) {
        <div class="figures">
          @for (f of figures(); track f.label) {
            <div class="figure">
              <span class="figure-value num">{{ f.value }}</span>
              <span class="figure-label">{{ f.label }}</span>
            </div>
          }
        </div>
      }

      @if (table(); as t) {
        @if (t.rows.length) {
          <div class="table-scroll">
            <table class="tbl">
              <thead>
                <tr>
                  @for (c of t.columns; track c) {
                    <th scope="col">{{ label(c) }}</th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of t.rows; track $index) {
                  <tr>
                    @for (c of t.columns; track c; let first = $first) {
                      <td [class.num]="!first">
                        {{ cell(c, row[c]) }}
                        @if (first && t.barKey) {
                          <span class="bar" [style.width.%]="barWidth(t, row)"></span>
                        }
                      </td>
                    }
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="empty">Aucun résultat sur cette période.</p>
        }
      }
    </article>
  `,
})
export class ResultCard {
  readonly card = input.required<Card>();

  readonly heading = computed(() => {
    const { title, data } = this.card();
    const name = data['produit'] ?? data['client'] ?? data['numero'];
    return typeof name === 'string' && !Array.isArray(data['produits'])
      ? `${title} · ${name}`
      : title;
  });

  readonly period = computed(() => {
    const p = this.card().data['periode'] as CardData | undefined;
    return p && typeof p['libelle'] === 'string' ? p['libelle'] : null;
  });

  readonly figures = computed<Figure[]>(() => {
    const data = this.card().data;
    return FIGURE_KEYS.filter((k) => typeof data[k] === 'number').map((k) => ({
      label: LABELS[k] ?? k,
      value: formatValue(k, data[k]),
    }));
  });

  readonly table = computed<Table | null>(() => {
    const { tool, data } = this.card();
    const key = TABLE_KEYS.find((k) => Array.isArray(data[k]));
    if (!key) {
      return null;
    }
    const rows = data[key] as CardData[];
    const columns = rows.length ? Object.keys(rows[0]).filter((c) => !HIDDEN_COLUMNS.has(c)) : [];
    const barKey =
      tool === 'top_produits'
        ? (CRITERION_KEYS[String(data['critere'])] ?? 'nombre_de_ventes')
        : (BAR_KEYS[tool] ?? null);
    const values = barKey ? rows.map((r) => Number(r[barKey]) || 0) : [];
    return { columns, rows, barKey, barMax: Math.max(1, ...values) };
  });

  label(key: string): string {
    return LABELS[key] ?? key;
  }

  cell(key: string, value: CardValue): string {
    return formatValue(key, value);
  }

  barWidth(table: Table, row: CardData): number {
    return table.barKey ? (100 * (Number(row[table.barKey]) || 0)) / table.barMax : 0;
  }
}
