import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { AskIn, AskOut, Language, Shop, SpokenLanguage, TranscribeOut } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  shop(): Observable<Shop> {
    return this.http.get<Shop>('/api/shop');
  }

  ask(body: AskIn): Observable<AskOut> {
    return this.http.post<AskOut>('/api/ask', body);
  }

  /** Without `language`, the spoken language is detected by the transcription. */
  transcribe(audio: Blob, language?: SpokenLanguage): Observable<TranscribeOut> {
    const extension = audio.type.includes('mp4')
      ? 'm4a'
      : audio.type.includes('ogg')
        ? 'ogg'
        : 'webm';
    const form = new FormData();
    form.append('audio', audio, `question.${extension}`);
    if (language) {
      form.append('language', language);
    }
    return this.http.post<TranscribeOut>('/api/transcribe', form);
  }

  /** The text read aloud, as an audio file. */
  speak(text: string, language: Language): Observable<Blob> {
    return this.http.post('/api/speak', { text, language }, { responseType: 'blob' });
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
      const sentence = detail.charAt(0).toUpperCase() + detail.slice(1);
      return /[.!?]$/.test(sentence) ? sentence : sentence + '.';
    }
    return `Erreur du serveur (${error.status}).`;
  }
  return 'Une erreur inattendue est survenue.';
}
