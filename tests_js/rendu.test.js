/* Rendu : vérifie ce que chaque fonction de mise à jour écrit réellement dans
 * le DOM, y compris les cas limites (aucune donnée, page unique, modèle de
 * régression indisponible). */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode, reponseValide, reponseFetch, zoneEtatVide } = require("./aide");

async function tableauBord() {
  const h = chargerCode();
  // Amorçage complet : graphiques + écouteurs (dont celui du thème).
  await h.demarrer();
  return h;
}

/* ---------------------------------------------------------------- KPI */

test("KPI : valeurs formatées selon leur nature", () => {
  const { api, document } = chargerCode();
  api.majKpis(reponseValide().kpis);

  assert.match(document.querySelector('[data-kpi="ca_total"]').textContent, /DT$/);
  assert.equal(document.querySelector('[data-kpi="nb_ventes"]').textContent, "320");
  assert.match(document.querySelector('[data-kpi="panier_moyen"]').textContent, /DT$/);
  // Les KPI absents du gabarit ne provoquent pas d'erreur.
  assert.equal(document.querySelector('[data-kpi="inconnu"]'), null);
});

test("KPI : valeur nulle affichée proprement", () => {
  const { api, document } = chargerCode();
  api.majKpis(reponseValide().kpis);
  // ca_total à null = aucun chiffre d'affaires pour ces filtres.
  const kpis = reponseValide().kpis;
  kpis.ca_total = null;
  api.majKpis(kpis);
  assert.equal(document.querySelector('[data-kpi="ca_total"]').textContent, "—");
});

/* --------------------------------------------------------- Synthèse */

test("synthèse : le texte du serveur est affiché et la carte visible", () => {
  const { api, document } = chargerCode();
  const carte = document.getElementById("carte-resume");

  assert.equal(carte.hidden, true);  // masquée tant qu'aucune donnée
  api.majResume("Sur 320 ventes, le CA atteint 15 000,00 DT.");
  assert.equal(carte.hidden, false);
  assert.equal(
    document.getElementById("resume-texte").textContent,
    "Sur 320 ventes, le CA atteint 15 000,00 DT.");
});

test("synthèse : texte absent → carte masquée", () => {
  const { api, document } = chargerCode();
  api.majResume("Une synthèse.");
  api.majResume("");
  assert.equal(document.getElementById("carte-resume").hidden, true);
});

test("synthèse : un nom de produit malveillant reste du texte", () => {
  // Un CSV peut contenir <script> dans un nom de produit : le résumé le
  // reprend, mais textContent empêche toute exécution ou injection.
  const { api, document } = chargerCode();
  api.majResume('Le produit star est « <img src=x onerror=alert(1)> ».');

  const zone = document.getElementById("resume-texte");
  assert.equal(zone.querySelector("img"), null);  // rien de vivant dans le DOM
  assert.ok(zone.textContent.includes("<img"));   // mais bien le texte d'origine
});

/* ------------------------------------------------------ Export PNG */

test("export PNG : un graphique existant déclenche un téléchargement", () => {
  const { api, window, document } = chargerCode();
  api.creerGraphiques();

  // jsdom ne télécharge pas : on observe l'élément créé à la place.
  const telechargements = [];
  window.HTMLAnchorElement.prototype.click = function () {
    telechargements.push({ href: this.href, download: this.download });
  };

  assert.equal(api.exporterPNG("chart-top"), true);
  assert.equal(telechargements.length, 1);
  assert.match(telechargements[0].download, /\.png$/);
  assert.match(telechargements[0].href, /^data:image\/png/);
  // Le lien éphémère est retiré du DOM après le clic.
  assert.equal(document.querySelector("a[download]"), null);
});

test("export PNG : nom de fichier lisible à partir du titre de la carte", () => {
  const { api } = chargerCode();
  api.creerGraphiques();
  // Le titre du gabarit est « Top » (gabarit de test minimal).
  assert.equal(api.nomFichierPNG("chart-top"), "datavision-top.png");
});

test("export PNG : graphique inconnu → false, sans erreur ni téléchargement", () => {
  const { api, window } = chargerCode();
  api.creerGraphiques();
  let appele = false;
  window.HTMLAnchorElement.prototype.click = () => { appele = true; };

  assert.equal(api.exporterPNG("chart-inconnu"), false);
  assert.equal(appele, false);
});

test("export PNG : graphique non créé → false (pas de canvas)", () => {
  const { api } = chargerCode();
  // Sans creerGraphiques(), aucun graphique n'existe.
  assert.equal(api.exporterPNG("chart-evolution"), false);
});

test("export PNG : le bouton du gabarit pilote le bon graphique", async () => {
  const h = await tableauBord();
  const telechargements = [];
  h.window.HTMLAnchorElement.prototype.click = function () {
    telechargements.push(this.download);
  };

  const bouton = h.document.querySelector('[data-png="chart-repartition"]');
  bouton.click();

  assert.equal(telechargements.length, 1);
  assert.equal(telechargements[0], "datavision-repartition.png");
});

/* --------------------------------------- En-tête des exports (titre/note) */

test("export PNG : les infos viennent des variables du template", () => {
  const { api, window } = chargerCode();

  assert.deepEqual(api.infosExport(), { titre: "", note: "", source: "" });

  window.PROJET_NOM = "Ventes 2026";
  window.NOTE_ANALYSTE = "Forte croissance.";
  window.SOURCE_DONNEES = "Enquete interne";
  assert.deepEqual(api.infosExport(), {
    titre: "Ventes 2026", note: "Forte croissance.", source: "Enquete interne",
  });
});

test("export PNG : la hauteur d'en-tête ne dépend que des champs présents", () => {
  const { api } = chargerCode();

  assert.equal(api.hauteurEntetePNG(null), 0);
  assert.equal(api.hauteurEntetePNG({ titre: "", note: "", source: "" }), 0);
  assert.equal(api.hauteurEntetePNG({ titre: "Ventes", note: "", source: "" }), 44);
  assert.equal(api.hauteurEntetePNG({ titre: "Ventes", note: "N", source: "" }), 60);
  assert.equal(api.hauteurEntetePNG({ titre: "Ventes", note: "N", source: "S" }), 76);
});

test("export PNG : titre, note et source dessinés dans l'ordre, puis le filet", () => {
  const { api } = chargerCode();
  const textes = [];
  const filets = [];
  const ctx = {
    measureText: (t) => ({ width: String(t).length * 6 }),
    fillText: (t) => textes.push(t),
    fillRect: (x, y, l, h) => filets.push({ x, y, l, h }),
    save() {}, restore() {}, beginPath() {}, rect() {}, roundRect() {},
    arc() {}, stroke() {}, fill() {},
    font: "", textAlign: "", textBaseline: "", lineWidth: 1,
    fillStyle: "", strokeStyle: "",
  };

  const hauteur = api.dessinerEntetePNG(ctx, 600, {
    titre: "Ventes 2026", note: "Forte croissance.", source: "Enquete interne",
  });

  assert.equal(hauteur, 76);
  assert.deepEqual(textes, [
    "Ventes 2026", "Forte croissance.", "Source : Enquete interne",
  ]);
  // Le filet ferme exactement le bas de l'en-tête.
  assert.equal(filets.length, 1);
  assert.equal(filets[0].y, 75);
  assert.equal(filets[0].l, 600 - 28);
});

test("export PNG : un libellé trop long est coupé avec des points de suspension", () => {
  const { api } = chargerCode();
  const ctx = { measureText: (t) => ({ width: String(t).length * 6 }) };

  assert.equal(api.texteCoupe(ctx, "Analyse courte", 500), "Analyse courte");

  const long = "Une note beaucoup trop longue pour tenir dans cette largeur";
  const coupe = api.texteCoupe(ctx, long, 120);
  assert.match(coupe, /…$/);
  assert.ok(coupe.length < long.length);
  assert.ok(ctx.measureText(coupe).width <= 120);
});

test("export PNG : la toile gagne la hauteur de l'en-tête", () => {
  const { api, window } = chargerCode();
  window.PROJET_NOM = "Ventes 2026";
  window.NOTE_ANALYSTE = "Forte croissance.";
  api.creerGraphiques();

  const telechargements = [];
  window.HTMLAnchorElement.prototype.click = function () {
    telechargements.push(this.download);
  };
  // On observe la toile composite créée par l'export.
  const toles = [];
  const vraiGetContext = window.HTMLCanvasElement.prototype.getContext;
  window.HTMLCanvasElement.prototype.getContext = function (...args) {
    toles.push(this);
    return vraiGetContext.call(this, ...args);
  };

  assert.equal(api.exporterPNG("chart-evolution"), true);
  assert.equal(telechargements.length, 1);

  const source = api.charts.evolution.canvas;
  const entete = api.hauteurEntetePNG(api.infosExport());
  assert.equal(entete, 60); // titre + note
  assert.equal(toles.length, 1);
  assert.equal(toles[0].height, source.height + entete);
});

test("export PNG : sans titre de projet, la toile garde sa hauteur d'origine", () => {
  const { api, window } = chargerCode();
  api.creerGraphiques();
  window.HTMLAnchorElement.prototype.click = () => {};

  const vraiGetContext = window.HTMLCanvasElement.prototype.getContext;
  let tole = null;
  window.HTMLCanvasElement.prototype.getContext = function (...args) {
    tole = this;
    return vraiGetContext.call(this, ...args);
  };

  api.exporterPNG("chart-categories");

  const source = api.charts.categories.canvas;
  assert.equal(tole.height, source.height, "aucun ajout d'en-tête");
});

/* ----------------------------------------------------------- Pagination */

test("pagination : une seule page → zone masquée", () => {
  const { api, document } = chargerCode();
  api.majPagination({ pages: 1, page: 1, total: 10 });

  const zone = document.getElementById("apercu-pagination");
  assert.equal(zone.hidden, true);
  assert.equal(zone.innerHTML, "");
});

test("pagination : aucune donnée → zone masquée", () => {
  const { api, document } = chargerCode();
  api.majPagination(null);
  assert.equal(document.getElementById("apercu-pagination").hidden, true);
  api.majPagination(undefined);
  assert.equal(document.getElementById("apercu-pagination").hidden, true);
});

test("pagination : première page → précédent désactivé", () => {
  const { api, document } = chargerCode();
  api.majPagination({ pages: 5, page: 1, total: 145 });

  const zone = document.getElementById("apercu-pagination");
  const [precedent, suivant] = zone.querySelectorAll("button");

  assert.equal(zone.hidden, false);
  assert.equal(precedent.disabled, true);
  assert.equal(suivant.disabled, false);
  assert.equal(suivant.dataset.page, "2");
  assert.ok(zone.textContent.includes("Page 1 sur 5"));
  assert.ok(zone.textContent.includes("145 lignes"));
});

test("pagination : dernière page → suivant désactivé", () => {
  const { api, document } = chargerCode();
  api.majPagination({ pages: 5, page: 5, total: 145 });

  const [precedent, suivant] = document.getElementById("apercu-pagination")
    .querySelectorAll("button");

  assert.equal(precedent.disabled, false);
  assert.equal(suivant.disabled, true);
  assert.equal(precedent.dataset.page, "4");
});

test("pagination : page du milieu → les deux boutons actifs", () => {
  const { api, document } = chargerCode();
  api.majPagination({ pages: 5, page: 3, total: 145 });

  const boutons = document.getElementById("apercu-pagination").querySelectorAll("button");
  assert.equal(boutons[0].disabled, false);
  assert.equal(boutons[1].disabled, false);
});

/* ------------------------------------------------------------- Tendance */

test("tendance : modèle indisponible → carte masquée", () => {
  const { api, document } = chargerCode();

  api.majTendance(null);
  assert.equal(document.getElementById("carte-tendance").hidden, true);

  api.majTendance({ disponible: false });
  assert.equal(document.getElementById("carte-tendance").hidden, true);
  assert.equal(document.getElementById("legende-projection").hidden, true);
});

test("tendance : modèle disponible → trois blocs rendus", () => {
  const { api, document } = chargerCode();
  api.majTendance({
    disponible: true,
    pente: 120.5,
    r2: 0.82,
    unite: "mois",
    projection_valeurs: [16000, 17200],
  });

  const carte = document.getElementById("carte-tendance");
  const blocs = document.querySelectorAll("#tendance-grille .tendance-bloc");

  assert.equal(carte.hidden, false);
  assert.equal(blocs.length, 3);
  // pente positive → classe « hausse »
  assert.ok(blocs[0].classList.contains("hausse"));
  // R² = 0,82 → modèle solide
  assert.ok(document.getElementById("tendance-grille").textContent.includes("modèle solide"));
  assert.equal(document.getElementById("legende-projection").hidden, false);
});

test("tendance : R² faible → modèle jugé peu fiable", () => {
  const { api, document } = chargerCode();
  api.majTendance({
    disponible: true,
    pente: -5,
    r2: 0.1,
    unite: "mois",
    projection_valeurs: [100],
  });

  const texte = document.getElementById("tendance-grille").textContent;
  assert.ok(texte.includes("données trop irrégulières"), texte);
  assert.ok(texte.includes("tendance à la baisse"), texte);
  assert.ok(document.querySelector("#tendance-grille .tendance-bloc").classList.contains("baisse"));
});

test("tendance : éléments absents du gabarit → aucune erreur", () => {
  const { api } = chargerCode({ html: "<!DOCTYPE html><html><body></body></html>" });
  const t = { disponible: true, pente: 1, r2: 0.5, unite: "mois", projection_valeurs: [1] };

  assert.doesNotThrow(() => api.majTendance(t));
  assert.doesNotThrow(() => api.majTendance(null));
  assert.doesNotThrow(() => api.majCorrelations({ paires: [] }));
  assert.doesNotThrow(() => api.majTableau("table-inconnu", { colonnes: ["a"], lignes: [["1"]] }));
  assert.doesNotThrow(() => api.majPagination({ pages: 3, page: 1, total: 9 }));
  assert.doesNotThrow(() => api.maj_etat_vide("chart-evolution", true, "x"));
  assert.doesNotThrow(() => api.montrer_loader(true));
});

/* --------------------------------------------------------- Corrélations */

test("corrélations : aucune paire → message d'explication", () => {
  const { api, document } = chargerCode();
  api.majCorrelations({ paires: [] });

  const table = document.getElementById("table-correlations");
  assert.equal(document.getElementById("correlations-total").textContent, "0");
  assert.ok(table.textContent.includes("Moins de deux colonnes numériques"));
  assert.equal(table.querySelector("thead"), null);
});

test("corrélations : valeur absente → pas d'erreur", () => {
  const { api, document } = chargerCode();
  assert.doesNotThrow(() => api.majCorrelations(null));
  assert.equal(document.getElementById("correlations-total").textContent, "0");
});

test("corrélations : tableau complet avec badge à jour", () => {
  const { api, document } = chargerCode();
  api.majCorrelations({
    paires: [
      { a: "puissance", b: "vitesse", valeur: 0.74, sens: "direct", force: "forte" },
      { a: "poids", b: "vitesse", valeur: -0.31, sens: "inverse", force: "faible" },
    ],
  });

  const table = document.getElementById("table-correlations");
  assert.equal(document.getElementById("correlations-total").textContent, "2");
  assert.equal(table.querySelectorAll("tbody tr").length, 2);
  assert.equal(table.querySelectorAll("thead th").length, 4);
  assert.equal(table.querySelectorAll(".corr-remplissage.direct").length, 1);
  assert.equal(table.querySelectorAll(".corr-remplissage.inverse").length, 1);
  // r = 0,74 → jauge à 74 %
  assert.ok(table.querySelector(".corr-remplissage").getAttribute("style").includes("74%"));
});

/* ---------------------------------------------------------- États vides */

test("état vide : masque le canvas et affiche le message", () => {
  const { api, document } = chargerCode();
  const canvas = document.getElementById("chart-evolution");
  const zone = zoneEtatVide(document, "chart-evolution");

  api.maj_etat_vide("chart-evolution", true, "Aucune donnée chiffrée pour ces filtres.");

  assert.equal(canvas.style.display, "none");
  assert.equal(zone.querySelector(".etat-vide").textContent,
    "Aucune donnée chiffrée pour ces filtres.");
  assert.equal(zone.querySelector(".etat-vide").hidden, false);
  // Le message est un frère du canvas : le canvas ne peut pas le contenir.
  assert.equal(canvas.querySelector(".etat-vide"), null);
});

test("état vide : donnée revenue → canvas réaffiché", () => {
  const { api, document } = chargerCode();
  const canvas = document.getElementById("chart-evolution");
  const zone = zoneEtatVide(document, "chart-evolution");

  api.maj_etat_vide("chart-evolution", true, "vide");
  api.maj_etat_vide("chart-evolution", false, "vide");

  assert.equal(canvas.style.display, "");
  assert.equal(zone.querySelector(".etat-vide").hidden, true);
});

test("état vide : pas de doublon de message à l'appel répété", () => {
  const { api, document } = chargerCode();
  const zone = zoneEtatVide(document, "chart-evolution");

  api.maj_etat_vide("chart-evolution", true, "un");
  api.maj_etat_vide("chart-evolution", true, "deux");

  assert.equal(zone.querySelectorAll(".etat-vide").length, 1);
  assert.equal(zone.querySelector(".etat-vide").textContent, "deux");
});

test("état vide : id inconnu → pas d'erreur", () => {
  const { api } = chargerCode();
  assert.doesNotThrow(() => api.maj_etat_vide("absent", true, "x"));
});

/* --------------------------------------------------------- Classement */

test("classement : raison « sans produit » affichée, graphiques vidés", () => {
  const { api, document, graphiques } = chargerCode();
  api.creerGraphiques();

  api.majClassement({
    top_labels: [], top_valeurs: [],
    flop_labels: [], flop_valeurs: [],
    raison: "sans_produit",
  });

  const messages = [
    zoneEtatVide(document, "chart-top").querySelector(".etat-vide"),
    zoneEtatVide(document, "chart-flop").querySelector(".etat-vide"),
  ];
  assert.ok(messages[0]);
  assert.ok(messages[1]);
  assert.ok(messages[0].textContent.includes("Aucune colonne"));
  assert.ok(graphiques().length >= 2);
});

test("classement : valeur absente → pas d'erreur", () => {
  const { api } = chargerCode();
  assert.doesNotThrow(() => api.majClassement(null));
});

test("classement : Top et Flop alimentent leurs graphiques", () => {
  const { api, graphiques } = chargerCode();
  api.creerGraphiques();
  const avant = graphiques().map((g) => g.maj);

  api.majClassement(reponseValide().classement);

  const [top, flop] = graphiques().filter(
    (g) => g.config.type === "bar" && g.options.indexAxis === "y"
  );
  assert.deepEqual(top.data.labels, ["A", "B"]);
  assert.deepEqual(flop.data.labels, ["Z", "Y"]);
  // update() a bien été appelé au moins une fois sur chacun.
  assert.ok(top.maj > avant[0] || top.maj >= 1);
});

/* ------------------------------------------------- Projection (courbe) */

test("projection : ancre la courbe pointillée sur le dernier point réel", () => {
  const { api, graphiques } = chargerCode();
  api.creerGraphiques();

  api.majProjection(
    { disponible: true, projection_labels: ["avr.", "mai"], projection_valeurs: [90, 95] },
    ["janv.", "févr.", "mars"],
    [10, 20, 30]
  );

  const evo = graphiques().find((g) => g.config.type === "line");
  // 3 mois réels + 2 mois projetés
  assert.equal(evo.data.labels.length, 5);
  assert.deepEqual(evo.data.datasets[1].data.slice(0, 3), [null, null, 30]);
  assert.deepEqual(evo.data.datasets[1].data.slice(3), [90, 95]);
  // La série réelle est prolongée de valeurs nulles (pas de trou dans la ligne).
  assert.deepEqual(evo.data.datasets[0].data.slice(3), [null, null]);
});

test("projection : tendance absente → courbe réelle seule", () => {
  const { api, graphiques } = chargerCode();
  api.creerGraphiques();

  api.majProjection(null, ["janv.", "févr."], [10, 20]);

  const evo = graphiques().find((g) => g.config.type === "line");
  assert.equal(evo.data.labels.length, 2);
  assert.deepEqual(evo.data.datasets[1].data, []);
  assert.deepEqual(evo.data.datasets[0].data, [10, 20]);
});

/* ------------------------------------------------------------- Loader */

test("loader : affiche puis masque", () => {
  const { api, document } = chargerCode();
  const loader = document.getElementById("loader");

  api.montrer_loader(true);
  assert.equal(loader.hidden, false);
  api.montrer_loader(false);
  assert.equal(loader.hidden, true);
});

/* -------------------------------------------------- Application globale */

test("appliquer : rend une réponse complète sans erreur", async () => {
  const h = await tableauBord();
  assert.doesNotThrow(() => h.api.appliquer(reponseValide()));

  assert.equal(
    h.document.getElementById("anomalies-total").textContent, "1");
  assert.equal(
    h.document.getElementById("apercu-pagination").hidden, false);
  // La dernière réponse est conservée (sert au changement de thème).
  assert.ok(h.api.derniereReponse());
});

test("appliquer : état vide global (aucun CA) masque la courbe", async () => {
  const h = await tableauBord();
  const d = reponseValide({
    kpis: { ...reponseValide().kpis, ca_total: null },
    categories: { labels: [], valeurs: [] },
  });
  h.api.appliquer(d);

  const evo = zoneEtatVide(h.document, "chart-evolution");
  assert.ok(evo.querySelector(".etat-vide"));
  assert.ok(evo.textContent.includes("Aucune donnée chiffrée"));
  assert.equal(
    h.document.getElementById("chart-evolution").style.display, "none");

  const cats = zoneEtatVide(h.document, "chart-categories");
  assert.ok(cats.querySelector(".etat-vide").textContent.includes("Aucune catégorie"));
});

test("appliquer : les graphiques se repeignent après un changement de thème", async () => {
  const h = await tableauBord();
  h.api.appliquer(reponseValide());

  const actifs = () => h.graphiques().filter((g) => !g.detruit);
  assert.equal(actifs().length, 6);

  h.document.dispatchEvent(new h.window.CustomEvent("datavision:theme"));

  // Toujours six graphiques : les anciens sont libérés, six neufs créés.
  assert.equal(actifs().length, 6);
  assert.equal(h.graphiques().filter((g) => g.detruit).length, 6);
  // Les données sont repeintes sans nouvelle requête réseau.
  assert.ok(h.api.derniereReponse());
  assert.ok(h.api.charts.evolution.data.labels.length > 0);
});

test("amorçage : démarrer monte les graphiques, les écouteurs et l'API", async () => {
  const appels = [];
  const h = chargerCode({
    sid: "9",
    fetch: (url) => {
      appels.push(url);
      return Promise.resolve(reponseFetch(reponseValide()));
    },
  });

  // Rien ne s'est encore passé : c'est le contrôle total du démarrage.
  assert.equal(h.graphiques().length, 0);
  assert.equal(appels.length, 0);

  await h.demarrer();

  assert.equal(h.graphiques().length, 6, "graphiques créés");
  assert.equal(appels.length, 1, "premier appel d'API");
  assert.equal(h.api.derniereReponse().kpis.ca_total, 15000);
  // Les écouteurs des filtres sont actifs.
  h.document.getElementById("filtre-debut").value = "2026-03-01";
  h.document.getElementById("filtre-debut")
    .dispatchEvent(new h.window.Event("change", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(appels.length, 2, "écouteur de filtre monté");
});

test("amorçage : un démarrage répété ne double pas les écouteurs", async () => {
  const appels = [];
  const h = chargerCode({
    fetch: (url) => {
      appels.push(url);
      return Promise.resolve(reponseFetch(reponseValide()));
    },
  });

  await h.demarrer();
  assert.equal(appels.length, 1);

  await h.demarrer();
  assert.equal(appels.length, 2, "un seul écouteur, un seul appel");
});
