import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  ApplicationConfig,
  isDevMode,
  LOCALE_ID,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideServiceWorker } from '@angular/service-worker';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withFetch()),
    { provide: LOCALE_ID, useValue: 'fr-FR' },
    // Installable PWA: caches the app shell; /api calls always go to the network.
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
