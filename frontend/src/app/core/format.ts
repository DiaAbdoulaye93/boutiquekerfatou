import { CardValue, Language } from './models';

const number = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 });
const dayMonth = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' });
const dayMonthTime = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

export const LANGUAGES: Record<Language, string> = {
  fr: 'Français',
  wo: 'Wolof',
  en: 'English',
  ff: 'Pulaar',
};

// Column and figure labels for the keys returned by the backend tools.
export const LABELS: Record<string, string> = {
  produit: 'Produit',
  quantite: 'Quantité',
  chiffre_affaires_xof: "Chiffre d'affaires",
  marge_xof: 'Marge',
  nombre_de_ventes: 'Ventes',
  nombre_de_factures: 'Factures',
  panier_moyen_xof: 'Panier moyen',
  numero: 'N°',
  date: 'Date',
  client: 'Client',
  paiement: 'Paiement',
  montant_xof: 'Montant',
  articles: 'Articles',
  reste_a_payer_xof: 'Reste à payer',
  dernier_achat_a_credit: 'Dernier crédit',
  total_du_xof: 'Total dû',
  nombre_de_clients: 'Clients',
  nombre_total: 'Factures',
  montant_total_xof: 'Montant total',
  achats_30_derniers_jours_xof: 'Achats (30 j)',
  passages_30_derniers_jours: 'Passages (30 j)',
  stock: 'Stock',
  seuil: 'Seuil',
  jours_restants: 'Jours restants',
  a_commander: 'À commander',
  libelle: 'Période',
  factures: 'Factures',
  prix_unitaire_xof: 'Prix',
  prix_xof: 'Prix',
  total_xof: 'Total',
  moyenne_par_jour: 'Moyenne / jour',
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

export function formatValue(key: string, value: CardValue): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (typeof value === 'number') {
    return key.endsWith('_xof') ? `${number.format(value)} FCFA` : number.format(value);
  }
  if (typeof value === 'string') {
    if (ISO_DATETIME.test(value)) {
      return dayMonthTime.format(new Date(value));
    }
    if (ISO_DATE.test(value)) {
      return dayMonth.format(new Date(value + 'T00:00'));
    }
    return value;
  }
  return String(value);
}

export function formatDuration(ms: number): string {
  return `${(ms / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s`;
}
