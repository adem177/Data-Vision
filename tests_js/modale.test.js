/* Vue détaillée : un clic dans la zone de tracé ouvre le graphique en grand,
 * dans la fenêtre prévue par le gabarit (dashboard.html). */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode, reponseValide } = require("./aide");

// Zone de tracé factice : ChartFactice ne la calcule pas, les tests la posent.
const ZONE = { left: 10, top: 10, right: 200, bottom: 120 };

async function tableauBord() {
  const h = chargerCode();
  await h.demarrer();
  h.api.appliquer(reponseValide());
  return h;
}

// Simule le relevé d'un clic par Chart.js sur le graphique `id`.
function clicSur(h, id, x, y) {
  const chart = h.api.graphiqueDe(id);
  chart.chartArea = { ...ZONE };
  h.api.clicModale({ x, y }, [], chart);
}

/* ------------------------------------------------------------- Ouverture */

test("vue détaillée : le clic dans la zone de tracé ouvre la fenêtre", async () => {
  const h = await tableauBord();
  clicSur(h, "chart-evolution", 50, 50);

  const boite = h.document.getElementById("modale-graphique");
  assert.equal(boite.hidden, false);
  assert.ok(h.document.body.classList.contains("modale-ouverte"));
  // Titre repris de la carte, bouton et légende de projection exclus.
  assert.equal(h.document.getElementById("modale-titre").textContent, "Évolution");
  assert.equal(h.document.getElementById("modale-info-titre").textContent, "Évolution");

  const modale = h.api.charts.modale;
  assert.ok(modale, "graphique de la vue détaillée créé");
  assert.equal(modale.config.type, "line");
  // 3 mois réels + 2 mois projetés, comme la courbe d'origine.
  assert.equal(modale.data.labels.length, 5);
});

test("vue détaillée : le bouton de fermeture referme et libère", async () => {
  const h = await tableauBord();
  clicSur(h, "chart-repartition", 50, 50);
  // L'anneau garde sa mise en page : légende à droite, comme sur la carte.
  assert.equal(h.api.charts.modale.config.type, "doughnut");
  assert.equal(h.api.charts.modale.options.plugins.legend.position, "right");

  h.document.getElementById("modale-fermer").click();

  assert.equal(h.document.getElementById("modale-graphique").hidden, true);
  assert.equal(h.api.charts.modale, undefined);
  assert.ok(!h.document.body.classList.contains("modale-ouverte"));
});

/* --------------------------------------------------------------- Garde-fous */

test("vue détaillée : un clic hors zone (légende) n'ouvre rien", async () => {
  const h = await tableauBord();
  clicSur(h, "chart-evolution", 5, 400);

  assert.equal(h.document.getElementById("modale-graphique").hidden, true);
  assert.equal(h.api.charts.modale, undefined);
});

test("vue détaillée : sans fenêtre dans le gabarit, ouvrir renvoie false", async () => {
  const h = await tableauBord();
  // Gabarit dépouillé (page sans la vue détaillée) : rien ne doit lever.
  h.document.getElementById("modale-graphique").remove();

  assert.equal(h.api.ouvrirModale("chart-evolution"), false);
  assert.equal(h.api.fermerModale(), false);
  assert.doesNotThrow(() => clicSur(h, "chart-evolution", 50, 50));
  assert.equal(h.api.charts.modale, undefined);
});

test("vue détaillée : une seule fenêtre à la fois", async () => {
  const h = await tableauBord();
  clicSur(h, "chart-evolution", 50, 50);
  const premier = h.api.charts.modale;

  clicSur(h, "chart-flop", 50, 50);

  assert.notEqual(h.api.charts.modale, premier);
  assert.equal(premier.detruit, true, "le graphique précédent est libéré");
});

/* ---------------------------------------------------------------- Données */

test("vue détaillée : les données sont copiées, la source reste intacte", async () => {
  const h = await tableauBord();
  const source = h.api.graphiqueDe("chart-categories");
  clicSur(h, "chart-categories", 50, 50);

  const modale = h.api.charts.modale;
  assert.notEqual(modale.data, source.data, "aucun objet de données partagé");
  assert.deepEqual(modale.data.labels, source.data.labels);
  assert.deepEqual(modale.data.datasets[0].data, source.data.datasets[0].data);

  // Modifier la vue détaillée ne retouche pas au graphique d'origine.
  modale.data.datasets[0].data[0] = -1;
  assert.equal(source.data.datasets[0].data[0], 9000);
});

test("vue détaillée : le Top 5 garde ses barres horizontales", async () => {
  const h = await tableauBord();
  clicSur(h, "chart-top", 50, 50);

  const modale = h.api.charts.modale;
  assert.equal(modale.options.indexAxis, "y");
  // Pas de légende : les libellés sont déjà sur l'axe.
  assert.equal(modale.options.plugins.legend.display, false);
});

test("vue détaillée : un changement de thème referme la fenêtre", async () => {
  const h = await tableauBord();
  clicSur(h, "chart-evolution", 50, 50);
  assert.equal(h.document.getElementById("modale-graphique").hidden, false);

  h.document.dispatchEvent(new h.window.CustomEvent("datavision:theme"));

  assert.equal(h.document.getElementById("modale-graphique").hidden, true);
  assert.equal(h.api.charts.modale, undefined);
  // Toujours six graphiques vivants : la vue détaillée n'en est pas un de plus.
  assert.equal(h.graphiques().filter((g) => !g.detruit).length, 6);
});
