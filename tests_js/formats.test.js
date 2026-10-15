/* Formats et affichage : ces fonctions produisent tout le texte visible du
 * tableau de bord. On compare à Intl plutôt qu'à des littéraux pour ne pas
 * dépendre de la version d'ICU embarquée dans Node. */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode } = require("./aide");

const fr = (v) => new Intl.NumberFormat("fr-FR").format(v);

test("formatDT : formate en dinars tunisiens", () => {
  const { api } = chargerCode();
  assert.equal(api.formatDT(15000), fr(15000) + " DT");
  assert.equal(api.formatDT(46.5), fr(46.5) + " DT");
});

test("formatDT : valeur absente → tiret, jamais NaN", () => {
  const { api } = chargerCode();
  for (const manquant of [null, undefined]) {
    assert.equal(api.formatDT(manquant), "—");
  }
});

test("formatNombre : sans unité, valeur absente → tiret", () => {
  const { api } = chargerCode();
  assert.equal(api.formatNombre(980), fr(980));
  assert.equal(api.formatNombre(null), "—");
  assert.equal(api.formatNombre(undefined), "—");
});

test("formatDT : ne renvoie jamais « NaN DT »", () => {
  const { api } = chargerCode();
  assert.notEqual(api.formatDT(NaN), "NaN DT");
  assert.notEqual(api.formatNombre(NaN), "NaN");
});

test("formaterVariation : cas limites", () => {
  const { api } = chargerCode();
  assert.equal(api.formaterVariation(null), "—");
  assert.equal(api.formaterVariation(undefined), "—");
});

test("formaterVariation : hausse, baisse et stable portent la bonne classe", () => {
  const { api } = chargerCode();

  const hausse = api.formaterVariation(12.5);
  assert.ok(hausse.includes("variation hausse"), hausse);
  assert.ok(hausse.includes("+12.5%"), hausse);
  assert.ok(hausse.includes("▲"), hausse);

  const baisse = api.formaterVariation(-3);
  assert.ok(baisse.includes("variation baisse"), baisse);
  assert.ok(baisse.includes("▼"), baisse);
  assert.ok(!baisse.includes("+"), baisse);

  const stable = api.formaterVariation(0);
  assert.ok(stable.includes("variation neutre"), stable);
  assert.ok(stable.includes("＝"), stable);
});

test("formaterVariation : renvoie du HTML balisé", () => {
  const { api } = chargerCode();
  assert.match(api.formaterVariation(4), /^<span class="variation /);
});

test("formaterPeriode : période vide → tiret", () => {
  const { api } = chargerCode();
  assert.equal(api.formaterPeriode({}), "—");
  assert.equal(api.formaterPeriode({ debut: null, fin: null }), "—");
});

test("formaterPeriode : borne manquante affichée comme inconnue", () => {
  const { api } = chargerCode();
  const texte = api.formaterPeriode({ debut: "2026-01-15", fin: null });
  assert.ok(texte.includes("→"), texte);
  assert.ok(texte.includes("?"), texte);
});

test("formaterPeriode : borne isolée affichée ?", () => {
  const { api } = chargerCode();
  const texte = api.formaterPeriode({ debut: null, fin: "2026-02-15" });
  assert.ok(texte.startsWith("?"), texte);
});

test("formaterPeriode : deux bornes affichées", () => {
  const { api } = chargerCode();
  const texte = api.formaterPeriode({ debut: "2026-01-01", fin: "2026-01-31" });
  assert.match(texte, / → /);
  assert.ok(!texte.includes("?"), texte);
});
