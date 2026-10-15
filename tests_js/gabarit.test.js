/* Contrat gabarit ↔ JavaScript.
 *
 * dashboard.js va chercher des id par leur nom : si quelqu'un renomme un id
 * dans dashboard.html, le JS se contente de renvoyer null et l'interface cesse
 * de fonctionner sans jamais lever d'erreur. Ce test compare les deux listes.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { lireGabarits, RACINE } = require("./aide");

const CODE = fs.readFileSync(
  path.join(RACINE, "static", "js", "dashboard.js"), "utf8"
);
const GABARITS = lireGabarits();

const idsDuGabarit = new Set(
  [...GABARITS.matchAll(/\bid\s*=\s*["']([^"']+)["']/g)].map((m) => m[1])
);

const idsDuCode = new Set(
  [...CODE.matchAll(/getElementById\(\s*["']([^"']+)["']\s*\)/g)].map((m) => m[1])
);

test("contrat : les gabarits déclarent bien tous les id utilisés par le JS", () => {
  const manquants = [...idsDuCode].filter((id) => !idsDuGabarit.has(id)).sort();
  assert.deepEqual(
    manquants, [],
    "Ces id sont cherchés par dashboard.js mais absents des gabarits :\n  "
      + manquants.join("\n  ")
  );
});

test("contrat : au moins un id est effectivement cherché", () => {
  // Garde-fou : si le regex casse, on ne veut pas d'un test vert vide.
  assert.ok(idsDuCode.size >= 15, `seulement ${idsDuCode.size} id détectés`);
});

test("contrat : les sélecteurs data-kpi existent dans le gabarit", () => {
  // majKpis construit les sélecteurs à partir de ses clés : c'est cette table
  // qui doit correspondre aux balises du gabarit.
  const bloc = CODE.match(/const formats = \{([\s\S]*?)\};/);
  assert.ok(bloc, "table des formats KPI introuvable dans dashboard.js");
  const cles = [...bloc[1].matchAll(/(\w+)\s*:\s*format/g)].map((m) => m[1]);
  assert.ok(cles.length >= 5, `seulement ${cles.length} KPI décrits`);

  const manquants = cles.filter(
    (c) => !new RegExp(`data-kpi\\s*=\\s*["']${c}["']`).test(GABARITS)
  );
  assert.deepEqual(manquants, [], "data-kpi absents du gabarit : " + manquants.join(", "));
});

test("contrat : les sélecteurs d'export existent dans le gabarit", () => {
  const formats = [...GABARITS.matchAll(/data-export\s*=\s*["']([^"']+)["']/g)]
    .map((m) => m[1]);
  assert.ok(formats.length >= 2, `seulement ${formats.length} lien(s) d'export`);
  assert.ok(formats.includes("csv"), "lien d'export CSV absent");

  // Le code doit lire ces deux attributs pour construire les URL.
  for (const attribut of ["data-export", "data-rapport", "data-base"]) {
    assert.ok(new RegExp(`\\b${attribut}\\b`).test(CODE),
      `dashboard.js ne lit pas ${attribut}`);
    assert.ok(new RegExp(`\\b${attribut}\\b`).test(GABARITS),
      `les gabarits n'exposent pas ${attribut}`);
  }
});

test("contrat : les boutons d'export PNG pointent vers de vrais graphiques", () => {
  // exporterPNG() cherche le graphique par l'id du canvas : si le data-png
  // d'un bouton vise un canvas inexistant, le clic ne fait rien, sans erreur.
  const cibles = [...GABARITS.matchAll(/data-png\s*=\s*["']([^"']+)["']/g)]
    .map((m) => m[1]);
  assert.ok(cibles.length >= 5, `seulement ${cibles.length} bouton(s) PNG`);

  const manquants = cibles.filter((id) => !idsDuGabarit.has(id));
  assert.deepEqual(manquants, [],
    "data-png sans canvas correspondant : " + manquants.join(", "));

  // Chaque canvas de graphique doit pouvoir être exporté.
  const canvasGraphiques = [...GABARITS.matchAll(/<canvas[^>]*\bid="(chart-[^"]+)"/g)]
    .map((m) => m[1]);
  const sansBouton = canvasGraphiques.filter((id) => !cibles.includes(id));
  assert.deepEqual(sansBouton, [],
    "canvas sans bouton d'export PNG : " + sansBouton.join(", "));
});

test("contrat : la coquille base.html déclare lang=\"fr\"", () => {
  const base = fs.readFileSync(
    path.join(RACINE, "core", "templates", "core", "base.html"), "utf8"
  );
  assert.match(base, /<html[^>]*\blang="fr"/);
  // Les pages enfants étendent la coquille : elles ne doivent pas redéclarer html.
  const dashboard = fs.readFileSync(
    path.join(RACINE, "core", "templates", "core", "dashboard.html"), "utf8"
  );
  assert.ok(!/<html/.test(dashboard), "dashboard.html ne doit pas étendre <html>");
});

test("contrat : le lien d'évitement et l'ancre de contenu principal existent", () => {
  // Accessibilité : sans eux, la navigation au clavier est impossible.
  assert.ok(/class="lien-evitement"/.test(GABARITS), "lien d'évitement absent");
  assert.ok(/id="contenu-principal"/.test(GABARITS), "ancre principale absente");
  assert.ok(/href="#contenu-principal"/.test(GABARITS), "cible du lien absente");
});
