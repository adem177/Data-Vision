import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';

/** Réponse de l'API Django /api/projets. */
interface Projet {
  id: number;
  nom: string;
  fichier: string;
  lignes: number;
  ca: string | null;
  date: string;
}

/** Réponse de l'API Django /api/donnees (extraits utiles ici). */
interface ReponseDonnees {
  kpis: Record<string, unknown>;
  mois: string[];
  ca_mensuel: number[];
}

/**
 * Preuve de concept : une page rendue par Angular et alimentée par les
 * API JSON de Django (aucun rendu côté serveur pour ce composant).
 *
 * L'état est stocké dans des **signaux** : en Angular 22, la détection de
 * changement ne repose plus sur zone.js, seuls les signaux (et les évènements)
 * déclenchent le rafraîchissement de l'écran.
 */
@Component({
  selector: 'app-root',
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  private readonly http = inject(HttpClient);

  readonly projets = signal<Projet[]>([]);
  readonly kpis = signal<Record<string, unknown>>({});
  readonly mois = signal<string[]>([]);
  readonly caMensuel = signal<number[]>([]);
  readonly analyseActive = signal('');
  readonly chargement = signal(true);
  readonly chargementDonnees = signal(false);
  readonly erreur = signal('');

  constructor() {
    this.http.get<{ projets: Projet[] }>('/api/projets').subscribe({
      next: (reponse) => {
        const liste = reponse.projets ?? [];
        this.projets.set(liste);
        this.chargement.set(false);
        if (liste.length) {
          this.charger(liste[0]);
        }
      },
      error: () => {
        this.chargement.set(false);
        this.erreur.set('Impossible de charger /api/projets (session expirée ?).');
      },
    });
  }

  selectionner(e: Event): void {
    const id = Number((e.target as HTMLSelectElement).value);
    const projet = this.projets().find((p) => p.id === id);
    if (projet) {
      this.charger(projet);
    }
  }

  private charger(projet: Projet): void {
    this.analyseActive.set(projet.nom);
    this.chargementDonnees.set(true);
    this.erreur.set('');
    this.http.get<ReponseDonnees>(`/api/donnees?id=${projet.id}`).subscribe({
      next: (donnees) => {
        this.kpis.set(donnees.kpis ?? {});
        this.mois.set(donnees.mois ?? []);
        this.caMensuel.set(donnees.ca_mensuel ?? []);
        this.chargementDonnees.set(false);
      },
      error: () => {
        this.chargementDonnees.set(false);
        this.erreur.set('Impossible de charger /api/donnees.');
      },
    });
  }

  /** Hauteur (2 à 100 %) d'une barre du mini-graphe en CSS pur. */
  hauteur(valeur: number): number {
    const serie = this.caMensuel();
    const max = Math.max(...serie, 1);
    return Math.max(2, Math.round((valeur / max) * 100));
  }

  /** Nombre au format français, ou « — » si la valeur est absente. */
  formatNombre(valeur: unknown): string {
    const n = Number(valeur);
    if (valeur === null || valeur === undefined || !Number.isFinite(n)) {
      return '—';
    }
    return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(n);
  }
}
