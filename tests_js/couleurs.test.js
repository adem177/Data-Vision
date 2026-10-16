/* Palette du tableau de bord : Okabe-Ito, vermillon réservé au Flop.
 *
 * Datawrapper vend l'accessibilité par défaut ; ici la preuve est
 * géométrique : six teintes toutes différentes, reprises à l'identique
 * par les graphiques — et le rouge du Flop n'est jamais partagé avec la
 * couleur des produits « bons ».
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode } = require("./aide");

// Référence : Okabe & Ito (2008), « Color Universal Design ».
const OKABE_ITO = [
  "#0072B2", // bleu
  "#D55E00", // vermillon
  "#009E73", // vert-bleu
  "#CC79A7", // rose-violet
  "#56B4E9", // bleu ciel
  "#E69F00", // orange
];

test("palette : les six teintes Okabe-Ito, toutes distinctes", () => {
  const { api } = chargerCode();

  assert.deepEqual(api.PALETTE, OKABE_ITO);
  assert.equal(new Set(api.PALETTE.map((c) => c.toLowerCase())).size, 6);
});

test("palette : le Top 5 s'interdit le vermillon du Flop", () => {
  const { api } = chargerCode();

  assert.equal(api.PALETTE_TOP.length, 5);
  assert.ok(!api.PALETTE_TOP.includes("#D55E00"));
  // Rien d'autre n'est retiré : cinq couleurs pour cinq barres.
  for (const teinte of api.PALETTE_TOP) {
    assert.ok(api.PALETTE.includes(teinte));
  }
});

test("palette : chaque graphique emploie la teinte prévue", () => {
  const { api } = chargerCode();
  api.creerGraphiques();

  // Courbe réelle : le bleu principal.
  assert.equal(
    api.charts.evolution.data.datasets[0].borderColor, api.PALETTE[0]);
  // Projection : le même bleu éclairci, en pointillés.
  const projection = api.charts.evolution.data.datasets[1];
  assert.equal(projection.borderColor, api.PALETTE[4]);
  assert.deepEqual(projection.borderDash, [7, 5]);
  // Catégories : bleu principal, survol assombri.
  const categories = api.charts.categories.data.datasets[0];
  assert.equal(categories.backgroundColor, api.PALETTE[0]);
  assert.equal(categories.hoverBackgroundColor, "#005A8F");
  // Flop : vermillon — la seule série « rouge », portée par la pastille ;
  // la tige, elle, reste grise (barres à puces).
  const flop = api.charts.flop.data.datasets;
  assert.equal(flop[0].backgroundColor, "#e3e6ea");
  assert.equal(flop[1].pointBackgroundColor, "#D55E00");
  assert.equal(flop[1].pointHoverBackgroundColor, "#9C4400");
  // Top : la palette privée du vermillon, portée par les pastilles.
  assert.deepEqual(api.charts.top.data.datasets[1].pointBackgroundColor, api.PALETTE_TOP);
  // Répartition : la palette entière, six parts pour six couleurs.
  assert.deepEqual(api.charts.repartition.data.datasets[0].backgroundColor, api.PALETTE);
});

test("palette : la nuage de dispersion hérite du même couple bleu", () => {
  const { api } = chargerCode();
  api.creerGraphiques();

  const points = api.charts.nuage.data.datasets[0];
  assert.ok(points.backgroundColor.startsWith(api.PALETTE[0]));
  const droite = api.charts.nuage.data.datasets[1];
  assert.equal(droite.borderColor, api.PALETTE[4]);
  assert.deepEqual(droite.borderDash, [7, 5]);
});
