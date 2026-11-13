// Mirror of backend/app/schemas.py.

export type Language = 'fr' | 'wo' | 'en' | 'ff';

export interface TurnIn {
  role: 'user' | 'assistant';
  text: string;
}

export interface AskIn {
  question: string;
  history: TurnIn[];
}

// Card data is the JSON returned by one business tool (backend/app/assistant/tools.py).
export type CardValue = string | number | boolean | null | CardData | CardData[];
export interface CardData {
  [key: string]: CardValue;
}

export interface Card {
  tool: string;
  title: string;
  data: CardData;
}

export interface AskOut {
  answer: string;
  language: Language;
  cards: Card[];
  model: string;
  duration_ms: number;
  llm_calls: number;
  cost_usd: number | null;
}

export interface Shop {
  name: string;
  fictional: true;
  first_day: string | null;
  last_day: string | null;
  products: number;
  customers: number;
  receipts: number;
}
