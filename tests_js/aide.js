/* Harnais de test : fournit un DOM jsdom et une fausse Chart.js au code front.
 *
 * Le but est de tester `static/js/dashboard.js` tel qu'il est servi au
 * navigateur, sans le modifier pour les besoins des tests. On réutilise donc
 * le gabarit minimale ci-dessous (qui reproduit la structure réelle du
 * tableau de bord) et on intercepte les dépendances non fournies par Node.
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const RACINE = path.join(__dirname, "..");
const CHEMIN_CODE = require.resolve(path.join(RACINE, "static", "js", "dashboard.js"));
const DOSSIERS_GABARITS = [
  path.join(RACINE, "core", "templates", "core", "base.html"),
  path.join(RACINE, "core", "templates", "core", "dashboard.html"),
];

/* ------------------------------------------------------------------ */
/* Fausses Chart.js                                                     */
/* ------------------------------------------------------------------ */

// Enregistre les configurations pour que les tests puissent les inspecter.
class ChartFactice {
  constructor(cible, config) {
    this.cible = cible;
    // Chart.js réel expose l'élément canvas sous `.canvas`.
    this.canvas = cible;
    this.config = config;
    this.data = config.data;
    this.options = config.options;
    this.maj = 0;
    this.detruit = false;
    // Équivalent minimal de la méthode réelle : une image factice.
    this.toBase64Image = () => "data:image/png;base64,factice";
    ChartFactice.instances.push(this);
  }
  update() { this.maj += 1; }
  destroy() { this.detruit = true; }
}
ChartFactice.instances = [];

/* ------------------------------------------------------------------ */
/* Gabarit de test                                                      */
/* ------------------------------------------------------------------ */

/* Reproduit la structure que dashboard.js attend. Les tests de rendu
 * s'appuient ici ; le test de contrat vérifie séparément que les mêmes id
 * existent bien dans les vrais gabarits Django. */
const GABARIT = `<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><title>DataVision — test</title></head>
<body>
  <a class="lien-evitement" href="#contenu-principal">Aller au contenu</a>
  <div id="contenu-principal">
    <button id="btn-theme" type="button"></button>

    <div id="loader" hidden></div>
    <div id="alerte-api" hidden></div>

    <span data-kpi="ca_total"></span>
    <span data-kpi="nb_ventes"></span>
    <span data-kpi="panier_moyen"></span>
    <span data-kpi="produits_vendus"></span>
    <span data-kpi="nb_categories"></span>
    <span data-kpi="valeurs_manquantes"></span>

    <section class="carte carte-resume" id="carte-resume" hidden>
      <p class="resume-texte" id="resume-texte"></p>
    </section>

    <select id="filtre-categorie">
      <option value=""></option>
      <option value="Electronique">Électronique</option>
    </select>
    <input type="date" id="filtre-debut">
    <input type="date" id="filtre-fin">
    <button id="btn-reset" type="button">Réinitialiser</button>

    <!-- Structure réelle de dashboard.html : l'id est posé sur le <canvas>,
         à l'intérieur d'une zone qui reçoit le message d'état vide. -->
    <section class="grille-graphiques">
      <div class="carte graphique large">
        <h3>Évolution <span id="legende-projection" hidden></span>
          <button type="button" class="btn-png" data-png="chart-evolution"
                  title="Télécharger ce graphique en PNG"><i class="bi bi-download"></i></button>
        </h3>
        <div class="zone-graphique"><canvas id="chart-evolution"></canvas></div>
      </div>
      <div class="carte graphique">
        <h3>Catégories
          <button type="button" class="btn-png" data-png="chart-categories"
                  title="Télécharger ce graphique en PNG"><i class="bi bi-download"></i></button>
        </h3>
        <div class="zone-graphique"><canvas id="chart-categories"></canvas></div>
      </div>
      <div class="carte graphique" id="carte-nuage" hidden>
        <h3>Dispersion <span id="nuage-total" class="badge">—</span>
          <button type="button" class="btn-png" data-png="chart-nuage"
                  title="Télécharger ce graphique en PNG"><i class="bi bi-download"></i></button>
        </h3>
        <p class="aide" id="nuage-legende"></p>
        <div class="zone-graphique"><canvas id="chart-nuage"></canvas></div>
      </div>
      <div class="carte graphique">
        <h3>Répartition
          <button type="button" class="btn-png" data-png="chart-repartition"
                  title="Télécharger ce graphique en PNG"><i class="bi bi-download"></i></button>
        </h3>
        <div class="zone-graphique"><canvas id="chart-repartition"></canvas></div>
      </div>
      <div class="carte graphique">
        <h3>Top
          <button type="button" class="btn-png" data-png="chart-top"
                  title="Télécharger ce graphique en PNG"><i class="bi bi-download"></i></button>
        </h3>
        <div class="zone-graphique"><canvas id="chart-top"></canvas></div>
      </div>
      <div class="carte graphique">
        <h3>Flop
          <button type="button" class="btn-png" data-png="chart-flop"
                  title="Télécharger ce graphique en PNG"><i class="bi bi-download"></i></button>
        </h3>
        <div class="zone-graphique"><canvas id="chart-flop"></canvas></div>
      </div>
    </section>

    <section class="carte" id="carte-tendance" hidden>
      <div class="tendance-grille" id="tendance-grille"></div>
    </section>

    <table id="table-apercu"></table>
    <table id="table-anomalies"></table>
    <span id="anomalies-total">0</span>
    <div id="apercu-pagination"></div>

    <table id="table-correlations"></table>
    <span id="correlations-total">0</span>

    <a data-export="csv" href="#">CSV</a>
    <a data-export="xlsx" href="#">Excel</a>
    <a data-rapport data-base="/projet/1/rapport" href="#">PDF</a>

    <div id="resultat-comparaison" hidden>
      <div id="comparaison-lignes"></div>
      <div id="comparaison-avertissement" hidden></div>
    </div>
    <button id="btn-comparer" type="button">Comparer</button>
  </div>
</body>
</html>`;

/* Réponse JSON complète et réaliste, telle que renvoyée par /api/donnees. */
function reponseValide(overrides = {}) {
  const base = {
    kpis: {
      ca_total: 15000,
      nb_ventes: 320,
      panier_moyen: 46.875,
      produits_vendus: 980,
      nb_categories: 3,
      valeurs_manquantes: 4,
    },
    resume: "Sur 320 ventes, le chiffre d'affaires atteint 15 000,00 DT.",
    tendance: {
      disponible: true,
      pente: 120.5,
      r2: 0.82,
      unite: "mois",
      projection_labels: ["avr. 2026", "mai 2026"],
      projection_valeurs: [16000, 17200],
    },
    mois: ["janv. 2026", "févr. 2026", "mars 2026"],
    ca_mensuel: [12000, 13500, 14800],
    categories: { labels: ["Électronique", "Maison"], valeurs: [9000, 6000] },
    classement: {
      top_labels: ["A", "B"], top_valeurs: [500, 400],
      flop_labels: ["Z", "Y"], flop_valeurs: [10, 20],
      raison: null,
    },
    correlations: {
      paires: [{ a: "puissance", b: "vitesse", valeur: 0.74, sens: "direct", force: "forte" }],
    },
    nuage: {
      disponible: true,
      x_nom: "prix", y_nom: "quantite",
      x: [10, 20, 30, 40], y: [5, 4, 3, 2],
      r: -0.98, force: "forte",
      pente: -0.1, droite: [4.9, 1.9], x_min: 10, x_max: 40,
      total: 320, echantillon: 4,
    },
    apercu: {
      colonnes: ["date", "produit", "montant"],
      lignes: [["2026-01-04", "Vis", "12"], ["2026-01-05", "Boulon", "8"]],
      pages: 3, page: 1, total: 145,
    },
    anomalies: {
      colonnes: ["montant"], lignes: [["Ligne 42 : valeur négative"]],
      total: 1,
    },
  };
  return { ...base, ...overrides };
}

/* ------------------------------------------------------------------ */
/* Chargement du code dans un environnement simulé                      */
/* ------------------------------------------------------------------ */

/* Charge le code dans un DOM simulé.
 *
 * jsdom déclenche DOMContentLoaded de façon asynchrone, après le constructeur.
 * Plutôt que de subir ce déclenchement, on intercepte l'enregistrement de
 * l'écouteur d'amorçage : le code est chargé, mais rien ne démarre tout seul.
 * Chaque test appelle ensuite demarrer() quand il est prêt, ce qui rend la
 * séquence parfaitement déterministe.
 */
function chargerCode(options = {}) {
  const {
    html = GABARIT,
    url = "http://127.0.0.1/dashboard/1",
    sid = "",
    fetch: fetchFactice = null,
  } = options;

  const dom = new JSDOM(html, {
    url,
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;

  // jsdom n'implémente pas le rendu canvas : on fournit un contexte 2D
  // minimal, juste ce qu'il faut pour construire un dégradé, pour
  // « peindre » une toile fictive lors de l'export PNG et pour l'en-tête
  // (fillText / measureText) que cet export répète au-dessus du graphe.
  window.HTMLCanvasElement.prototype.getContext = function () {
    return {
      canvas: this,
      fillStyle: "#000000",
      strokeStyle: "#000000",
      font: "",
      textAlign: "start",
      textBaseline: "alphabetic",
      lineWidth: 1,
      createLinearGradient: () => ({ addColorStop() {} }),
      createRadialGradient: () => ({ addColorStop() {} }),
      fillRect() {},
      drawImage() {},
      beginPath() {},
      rect() {},
      roundRect() {},
      arc() {},
      stroke() {},
      fill() {},
      save() {},
      restore() {},
      fillText() {},
      // Largeur grossière mais monotone : largement suffisante pour
      // tester la coupure « … » des libellés trop longs.
      measureText: (t) => ({ width: String(t).length * 6 }),
    };
  };
  // toDataURL n'est pas non plus implémenté : on renvoie une image factice.
  window.HTMLCanvasElement.prototype.toDataURL = () => "data:image/png;base64,factice";

  ChartFactice.instances.length = 0;

  window.SID = sid;

  // Expose les globaux du navigateur attendus par le code testé.
  global.window = window;
  global.document = window.document;
  global.Chart = ChartFactice;
  global.Event = window.Event;
  global.CustomEvent = window.CustomEvent;
  global.getComputedStyle = window.getComputedStyle.bind(window);
  global.requestAnimationFrame = window.requestAnimationFrame.bind(window);
  global.cancelAnimationFrame = window.cancelAnimationFrame.bind(window);
  // Aucun accès réseau pendant les tests : par défaut la requête échoue et le
  // code doit encaisser proprement. Chaque test peut fournir son propre fetch.
  global.fetch = fetchFactice || (() => Promise.reject(new Error("réseau neutralisé")));

  // Intercepte le seul enregistrement DOMContentLoaded : le déclenchement
  // naturel de jsdom devient sans effet.
  const ecouteurs = [];
  const vraiAjouter = window.document.addEventListener.bind(window.document);
  window.document.addEventListener = function (type, ...reste) {
    if (type === "DOMContentLoaded") { ecouteurs.push(reste[0]); return; }
    return vraiAjouter(type, ...reste);
  };

  delete require.cache[CHEMIN_CODE];
  const api = require(CHEMIN_CODE);

  // Les écouteurs créés ensuite (filtres, pagination) doivent repasser par la
  // méthode d'origine.
  window.document.addEventListener = vraiAjouter;

  let demarre = false;

  return {
    dom,
    window,
    document: window.document,
    api,
    graphiques: () => [...ChartFactice.instances],
    /* Déclenche l'amorçage exactement comme le ferait le navigateur :
     * création des graphiques, montage des écouteurs, premier appel d'API. */
    demarrer: async () => {
      // 1. Laisser passer le déclenchement naturel de jsdom, qui est sans
      //    effet puisque l'écouteur n'est pas encore rattaché.
      await new Promise((resolve) => {
        if (window.document.readyState !== "loading") return resolve();
        window.document.addEventListener("DOMContentLoaded", resolve, { once: true });
      });
      // 2. Rattacher l'écouteur d'amorçage, puis le déclencher.
      if (!demarre) {
        demarre = true;
        ecouteurs.forEach((fn) => vraiAjouter("DOMContentLoaded", fn));
      }
      api.initialiser();
      // 3. Laisser l'appel d'API lancé par l'amorçage se terminer.
      await new Promise((resolve) => setTimeout(resolve, 0));
    },
  };
}

/* Lecture des vrais gabarits Django (test de contrat). */
function lireGabarits() {
  return DOSSIERS_GABARITS.map((chemin) => fs.readFileSync(chemin, "utf8")).join("\n");
}

/* Où maj_etat_vide dépose son message : le conteneur du <canvas>, qui est
 * soit l'élément portant l'id, soit son parent quand l'id est sur le canvas. */
function zoneEtatVide(document, id) {
  const zone = document.getElementById(id);
  if (!zone) return null;
  return zone.tagName === "CANVAS" ? zone.parentElement : zone;
}

/* Réponse fetch simulée : même surface que Response pour le code testé. */
function reponseFetch(donnees, { ok = true, statut = 200 } = {}) {
  return {
    ok,
    status: statut,
    json: async () => donnees,
    text: async () => JSON.stringify(donnees),
  };
}

module.exports = {
  chargerCode, reponseValide, reponseFetch, lireGabarits, zoneEtatVide,
  GABARIT, RACINE,
};
