/* Dispersion : nuage de points de la paire la plus corrélée.
 *
 * La carte n'apparaît que quand le serveur exploite un couple, la droite
 * suit les points renvoyés, et le libellé dit toujours ce qu'on regarde
 * (colonnes, volume, force du lien).
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode, reponseValide } = require("./aide");

function tableau() {
  const h = chargerCode();
  h.api.creerGraphiques();
  return h;
}

test("dispersion : carte affichée, points et droite posés", () => {
  const h = tableau();
  h.api.majNuage(reponseValide().nuage);

  const carte = h.document.getElementById("carte-nuage");
  assert.equal(carte.hidden, false);

  const jeux = h.api.charts.nuage.data.datasets;
  assert.equal(jeux[0].data.length, 4);
  assert.deepEqual(jeux[0].data[0], { x: 10, y: 5 });
  // La droite relie les deux bornes de x, aux valeurs annoncées.
  assert.deepEqual(jeux[1].data, [
    { x: 10, y: 4.9 },
    { x: 40, y: 1.9 },
  ]);
});

test("dispersion : la légende dit les colonnes, le volume et la force", () => {
  const h = tableau();
  h.api.majNuage(reponseValide().nuage);

  const legende = h.document.getElementById("nuage-legende").textContent;
  assert.ok(legende.includes("quantite selon prix"));
  assert.ok(legende.includes("4 points"));
  assert.ok(legende.includes("échantillon sur 320 lignes"));
  assert.ok(legende.includes("lien forte"));

  const badge = h.document.getElementById("nuage-total").textContent;
  assert.equal(badge, `r = ${h.api.formatNombre(-0.98)}`);
});

test("dispersion : les titres d'axes arrivent après coup (couple sous filtre)", () => {
  const h = tableau();
  h.api.majNuage(reponseValide().nuage);

  const echelles = h.api.charts.nuage.options.scales;
  assert.equal(echelles.x.title.display, true);
  assert.equal(echelles.x.title.text, "prix");
  assert.equal(echelles.y.title.text, "quantite");
});

test("dispersion : couple inexploitable → carte masquée, sans erreur", () => {
  const h = tableau();

  h.api.majNuage({ disponible: false });
  assert.equal(h.document.getElementById("carte-nuage").hidden, true);

  h.api.majNuage(undefined);
  assert.equal(h.document.getElementById("carte-nuage").hidden, true);
});

test("dispersion : sans droite, le graphique reste un nuage nu", () => {
  const h = tableau();
  h.api.majNuage({ ...reponseValide().nuage, droite: null, pente: null });

  const jeux = h.api.charts.nuage.data.datasets;
  assert.ok(jeux[0].data.length > 0, "les points, quand même");
  assert.deepEqual(jeux[1].data, []);
});

test("dispersion : un élément retiré du gabarit ne plante pas", () => {
  const h = tableau();
  h.document.getElementById("carte-nuage").remove();

  assert.doesNotThrow(() => h.api.majNuage(reponseValide().nuage));
});

test("dispersion : appliquer pilote la carte depuis la réponse de l'API", () => {
  const h = tableau();
  h.api.appliquer(reponseValide({ kpis: { ...reponseValide().kpis, ca_total: 1200 } }));

  assert.equal(h.document.getElementById("carte-nuage").hidden, false);
  assert.ok(h.api.charts.nuage.data.datasets[0].data.length > 0);
});

test("dispersion : réponse sans champ nuage (ancien cache) → carte masquée", () => {
  const h = tableau();
  const ancienne = reponseValide();
  delete ancienne.nuage;

  assert.doesNotThrow(() => h.api.appliquer(ancienne));
  assert.equal(h.document.getElementById("carte-nuage").hidden, true);
});
