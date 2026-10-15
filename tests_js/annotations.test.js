/* Annotations sur la courbe : le calcul (fonction pure) et le plugin
 * maison qui les dessine, sans aucune dépendance.
 *
 * Deux promesses sont vérifiées ici : les annotations ne racontent que
 * des choses vraies (max, min, plus forte variation) et jamais deux
 * libellés voisins — une étiquette qui en recouvre une autre ne vaut
 * pas mieux qu'aucune.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode } = require("./aide");

const MOIS = [
  "janv. 2026", "févr. 2026", "mars 2026", "avr. 2026",
  "mai 2026", "juin. 2026", "juil. 2026",
];

/* ------------------------------------------------------- Le calcul ---- */

test("annotations : le maximum et le minimum trouvés et étiquetés", () => {
  const { api } = chargerCode();
  const ann = api.calculerAnnotations(MOIS, [2000, 1500, 1520, 1900, 1510, 1520, 1500]);

  const max = ann.find((a) => a.type === "max");
  const min = ann.find((a) => a.type === "min");
  assert.equal(max.index, 0);
  assert.equal(min.index, 1);
  // Le texte passe par le même formateur que les KPI (espaces fines incluses).
  assert.equal(max.texte, `Max : ${new Intl.NumberFormat("fr-FR").format(2000)} DT`);
  assert.equal(min.texte, `Min : ${new Intl.NumberFormat("fr-FR").format(1500)} DT`);
  assert.equal(max.auDessus, true);
  assert.equal(min.auDessus, false);
});

test("annotations : la plus forte hausse, loin des extrêmes, a son étiquette", () => {
  const { api } = chargerCode();
  const ann = api.calculerAnnotations(MOIS, [2000, 1500, 1520, 1900, 1510, 1520, 1500]);

  const hausse = ann.find((a) => a.type === "hausse");
  assert.ok(hausse, "la plus forte hausse mérite son étiquette");
  assert.equal(hausse.index, 3); // 1520 → 1900 = +25 % en avril
  assert.equal(hausse.texte, "+25 % en avr.");
  assert.equal(hausse.auDessus, true);
});

test("annotations : jamais deux étiquettes à un indice d'écart", () => {
  const { api } = chargerCode();
  const ann = api.calculerAnnotations(MOIS, [2000, 1500, 1520, 1900, 1510, 1520, 1500]);

  const variations = ann.filter((a) => a.type === "hausse" || a.type === "baisse");
  for (const v of variations) {
    for (const autre of ann) {
      if (autre === v) continue;
      assert.ok(
        Math.abs(autre.index - v.index) >= 2,
        `variation ${v.type} à ${v.index} trop proche de ${autre.type} à ${autre.index}`
      );
    }
  }
});

test("annotations : série courte, constante ou invalide → rien", () => {
  const { api } = chargerCode();

  assert.deepEqual(api.calculerAnnotations(MOIS.slice(0, 2), [10, 20]), []);
  assert.deepEqual(api.calculerAnnotations(["a", "b", "c"], [5, 5, 5]), []);
  assert.deepEqual(api.calculerAnnotations(["a", "b", "c"], [100, "abc", 300]), []);
  assert.deepEqual(api.calculerAnnotations(null, null), []);
});

test("annotations : une base à zéro ne provoque pas de division par zéro", () => {
  const { api } = chargerCode();
  const ann = api.calculerAnnotations(
    ["janv.", "févr.", "mars", "avr."], [0, 100, 200, 150]
  );

  assert.deepEqual(ann.map((a) => a.type), ["max", "min"]);
});

test("annotations : la courbe d'évolution embarque le plugin", () => {
  const { api } = chargerCode();
  api.creerGraphiques();

  const config = api.charts.evolution.config;
  assert.ok(Array.isArray(config.plugins), "plugins au bon endroit de la config");
  assert.ok(config.plugins.includes(api.annotationsCourbe));
});

test("annotations : la projection les attache au graphique, données réelles seules", () => {
  const { api } = chargerCode();
  api.creerGraphiques();
  api.majProjection({ disponible: false }, MOIS.slice(0, 3), [1000, 1500, 1200]);

  const ann = api.charts.evolution.$annotations;
  assert.ok(Array.isArray(ann));
  assert.equal(ann.find((a) => a.type === "max").index, 1);
  assert.equal(ann.find((a) => a.type === "min").index, 0);
  assert.ok(ann.every((a) => a.index < 3), "seules les valeurs réelles sont annotées");
});

/* --------------------------------------------------------- Le rendu ---- */

function contexteFactice(compteur) {
  return {
    save() {}, restore() {}, beginPath() {}, rect() {}, roundRect() {},
    fill() {}, stroke() {},
    arc() { compteur.arcs += 1; },
    fillText(t) { compteur.textes.push(t); },
    fillRect() { compteur.filets += 1; },
    measureText: (t) => ({ width: String(t).length * 6 }),
    font: "", textAlign: "", textBaseline: "", lineWidth: 1,
    fillStyle: "", strokeStyle: "",
  };
}

function courbeFactice(compteur, annotations, largeur = 700) {
  // Le graphe factice doit couvrir le plus grand index annoté : c'est la
  // courbe complète qui est simulée, pas la liste des annotations.
  const dernier = annotations.reduce((max, a) => Math.max(max, a.index), 0);
  const points = Array.from({ length: dernier + 1 }, (_, i) => ({
    x: 60 + i * 70, y: 120 + i * 10,
  }));
  return {
    width: largeur,
    height: 300,
    ctx: contexteFactice(compteur),
    getDatasetMeta: () => ({ data: points }),
    $annotations: annotations,
  };
}

test("plugin : un anneau et un libellé par annotation", () => {
  const { api } = chargerCode();
  const compteur = { arcs: 0, textes: [], filets: 0 };
  const annotations = [
    { index: 0, type: "max", texte: "Max : 2 000 DT", auDessus: true },
    { index: 2, type: "hausse", texte: "+25 % en avr.", auDessus: true },
    { index: 4, type: "min", texte: "Min : 1 500 DT", auDessus: false },
  ];

  api.annotationsCourbe.afterDatasetsDraw(courbeFactice(compteur, annotations));

  assert.equal(compteur.arcs, 3, "un anneau par annotation");
  assert.deepEqual(compteur.textes, annotations.map((a) => a.texte));
});

test("plugin : sous 480 px, les anneaux restent mais le texte s'efface", () => {
  const { api } = chargerCode();
  const compteur = { arcs: 0, textes: [], filets: 0 };
  const annotations = [
    { index: 0, type: "max", texte: "Max : 2 000 DT", auDessus: true },
    { index: 2, type: "min", texte: "Min : 1 500 DT", auDessus: false },
  ];

  api.annotationsCourbe.afterDatasetsDraw(
    courbeFactice(compteur, annotations, 400)
  );

  assert.equal(compteur.arcs, 2, "le repère survit sur mobile");
  assert.deepEqual(compteur.textes, [], "le libellé, non : il gênerait");
});

test("plugin : sans annotation ou sans données, il ne dessine rien", () => {
  const { api } = chargerCode();
  const compteur = { arcs: 0, textes: [], filets: 0 };

  api.annotationsCourbe.afterDatasetsDraw(courbeFactice(compteur, []));
  api.annotationsCourbe.afterDatasetsDraw({ width: 700, height: 300, ctx: {} });
  api.annotationsCourbe.afterDatasetsDraw({});

  assert.equal(compteur.arcs, 0);
  assert.equal(compteur.textes.length, 0);
});
