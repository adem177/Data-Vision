/* Palette « marque » : variante opt-in façon Datawrapper (thème
 * personnalisé en teal → cyan), le défaut restant la palette Okabe-Ito
 * certifiée daltonisme par les tests de couleurs.
 *
 * Trois promesses : le défaut ne bouge pas, la variante ne s'active que
 * par mémorisation explicite, et ses six teintes restent rigoureusement
 * distinctes — sans jamais emprunter le vermillon réservé au Flop.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode } = require("./aide");

test("palette : sans choix mémorisé, le défaut est Okabe-Ito", () => {
  const { api } = chargerCode();

  assert.equal(api.paletteActive(), api.PALETTE);
});

test("palette : la variante marque s'active par mémorisation locale", () => {
  const h = chargerCode();

  h.window.localStorage.setItem("datavision-palette", "marque");
  assert.equal(h.api.paletteActive(), h.api.PALETTE_MARQUE);

  // Revenir au défaut : toute autre valeur que « marque » rend Okabe-Ito.
  h.window.localStorage.setItem("datavision-palette", "okabe");
  assert.equal(h.api.paletteActive(), h.api.PALETTE);
});

test("palette : la variante marque garde six teintes hexadécimales distinctes", () => {
  const { api } = chargerCode();

  assert.equal(api.PALETTE_MARQUE.length, 6);
  assert.equal(new Set(api.PALETTE_MARQUE.map((c) => c.toLowerCase())).size, 6);
  for (const teinte of api.PALETTE_MARQUE) {
    assert.match(teinte, /^#[0-9A-Fa-f]{6}$/);
  }
  // Le vermillon du Flop n'appartient jamais à la palette de marque.
  assert.ok(!api.PALETTE_MARQUE.includes("#D55E00"));
});
