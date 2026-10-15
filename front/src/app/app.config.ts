import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Requêtes vers les API JSON de Django (cookies de session inclus :
    // même origine, aucune configuration CORS n'est nécessaire).
    // Pas de routeur Angular : cette page unique est rendue par Django.
    provideHttpClient(),
  ],
};
