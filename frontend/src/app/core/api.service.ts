import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { AskIn, AskOut, Shop } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  shop(): Observable<Shop> {
    return this.http.get<Shop>('/api/shop');
  }

  ask(body: AskIn): Observable<AskOut> {
    return this.http.post<AskOut>('/api/ask', body);
  }
}

/** French message for the user from an HTTP error. */
export function errorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) {
      return 'Le serveur est injoignable. Vérifiez la connexion.';
    }
    const detail = (error.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail.charAt(0).toUpperCase() + detail.slice(1) + '.';
    }
    return `Erreur du serveur (${error.status}).`;
  }
  return 'Une erreur inattendue est survenue.';
}
