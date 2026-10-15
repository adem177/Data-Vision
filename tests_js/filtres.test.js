/* Filtres, exports et cycle de vie : tout part de parametresRequete(), qui
 * alimente l'API, les liens d'export et le rapport PDF. Une erreur ici fausse
 * silencieusement l'ensemble des vues filtrées. */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode, reponseValide, reponseFetch } = require("./aide");

const attendre = (ms = 10) => new Promise((r) => setTimeout(r, ms));

/* --------------------------------------------------------- parametres */

test("requête : sans filtre, seul l'id du projet est envoyé", () => {
  const { api } = chargerCode({ sid: "7" });
  assert.equal(api.parametresRequete(), "id=7");
});

test("requête : chaque filtre actif est ajouté", () => {
  const { api, document } = chargerCode({ sid: "7" });
  document.getElementById("filtre-categorie").value = "Electronique";
  document.getElementById("filtre-debut").value = "2026-01-01";
  document.getElementById("filtre-fin").value = "2026-01-31";

  const p = new URLSearchParams(api.parametresRequete());
  assert.equal(p.get("id"), "7");
  assert.equal(p.get("categorie"), "Electronique");
  assert.equal(p.get("debut"), "2026-01-01");
  assert.equal(p.get("fin"), "2026-01-31");
});

test("requête : un filtre vide n'est pas envoyé", () => {
  const { api, document } = chargerCode({ sid: "7" });
  document.getElementById("filtre-debut").value = "2026-01-01";

  const p = new URLSearchParams(api.parametresRequete());
  assert.equal(p.has("debut"), true);
  assert.equal(p.has("fin"), false);
  assert.equal(p.has("categorie"), false);
});

test("requête : les caractères particuliers survivent à l'aller-retour", () => {
  const { api, document } = chargerCode({ sid: "7" });
  const nom = "Électronique & Maison + 100%";

  // Une catégorie telle que Django la rend dans la liste déroulante.
  const select = document.getElementById("filtre-categorie");
  const option = document.createElement("option");
  option.value = nom;
  option.textContent = nom;
  select.appendChild(option);
  select.value = nom;

  const p = new URLSearchParams(api.parametresRequete());
  assert.equal(p.get("categorie"), nom);
});

test("requête : l'id absent (accueil) ne casse pas la construction", () => {
  const { api } = chargerCode({ sid: "" });
  const p = new URLSearchParams(api.parametresRequete());
  assert.equal(p.get("id"), "");
  assert.equal(api.parametresRequete().includes("undefined"), false);
});

/* ------------------------------------------------------------ exports */

test("exports : CSV et Excel reçoivent les filtres courants", () => {
  const { api, document } = chargerCode({ sid: "3" });
  document.getElementById("filtre-debut").value = "2026-01-01";
  api.majExports();

  for (const format of ["csv", "xlsx"]) {
    const lien = document.querySelector(`[data-export="${format}"]`);
    const p = new URLSearchParams(lien.href.split("?")[1]);
    assert.equal(p.get("format"), format, lien.href);
    assert.equal(p.get("debut"), "2026-01-01", lien.href);
    assert.equal(p.get("id"), "3", lien.href);
  }
});

test("exports : le rapport PDF reprend les filtres sans format", () => {
  const { api, document } = chargerCode({ sid: "3" });
  document.getElementById("filtre-fin").value = "2026-01-31";
  api.majExports();

  const lien = document.querySelector("[data-rapport]");
  const p = new URLSearchParams(lien.href.split("?")[1]);
  assert.equal(p.get("fin"), "2026-01-31");
  assert.equal(p.get("format"), null);
  assert.ok(lien.href.startsWith("http://127.0.0.1/projet/1/rapport"), lien.href);
});

test("exports : aucun lien d'export → pas d'erreur", () => {
  const { api } = chargerCode({ html: "<!DOCTYPE html><html><body></body></html>" });
  assert.doesNotThrow(() => api.majExports());
});

/* ------------------------------------------------------------- charger */

test("charger : appelle l'API avec l'id et la page courante", async () => {
  const appels = [];
  const h = chargerCode({
    sid: "42",
    fetch: (url) => {
      appels.push(url);
      return Promise.resolve(reponseFetch(reponseValide()));
    },
  });
  h.api.creerGraphiques();

  await h.api.charger();

  assert.equal(appels.length, 1);
  assert.ok(appels[0].includes("/api/donnees"), appels[0]);
  const p = new URLSearchParams(appels[0].split("?")[1]);
  assert.equal(p.get("id"), "42");
  assert.equal(p.get("page"), "1");
  assert.ok(h.api.derniereReponse());
  assert.equal(h.document.getElementById("alerte-api").hidden, true);
});

test("charger : réponse 500 → alerte affichée, rien de rendu", async () => {
  const h = chargerCode({
    fetch: () => Promise.resolve(reponseFetch(null, { ok: false, statut: 500 })),
  });
  h.api.creerGraphiques();

  await h.api.charger();

  assert.equal(h.document.getElementById("alerte-api").hidden, false);
  assert.equal(h.api.derniereReponse(), null);
});

test("charger : réseau coupé → alerte affichée, pas de plantage", async () => {
  const h = chargerCode(); // fetch rejette par défaut
  h.api.creerGraphiques();

  await assert.doesNotReject(() => h.api.charger());
  assert.equal(h.document.getElementById("alerte-api").hidden, false);
  assert.equal(h.document.getElementById("loader").hidden, true);
});

test("charger : le loader est bien relâché après une erreur", async () => {
  const h = chargerCode({ fetch: () => Promise.reject(new Error("coupé")) });
  h.api.creerGraphiques();

  await h.api.charger();
  assert.equal(h.document.getElementById("loader").hidden, true);
});

/* -------------------------------------------------------- Interactions */

test("amorçage : cliquer sur « Suivant » change de page", async () => {
  const appels = [];
  const h = chargerCode({
    sid: "1",
    fetch: (url) => {
      appels.push(url);
      return Promise.resolve(reponseFetch(reponseValide()));
    },
  });

  await h.demarrer();
  assert.equal(appels.length, 1, "chargement initial");

  // Les boutons de pagination sont en place.
  const boutons = h.document.getElementById("apercu-pagination").querySelectorAll("button");
  assert.equal(boutons.length, 2);

  boutons[1].dispatchEvent(new h.window.MouseEvent("click", { bubbles: true }));
  await attendre();

  assert.equal(appels.length, 2, "second appel après le clic");
  const p = new URLSearchParams(appels[1].split("?")[1]);
  assert.equal(p.get("page"), "2");
  assert.equal(h.api.pageApercu(), 2);
});

test("amorçage : changer un filtre relance la lecture", async () => {
  const appels = [];
  const h = chargerCode({
    sid: "1",
    fetch: (url) => {
      appels.push(url);
      return Promise.resolve(reponseFetch(reponseValide()));
    },
  });

  await h.demarrer();
  assert.equal(appels.length, 1);

  h.document.getElementById("filtre-debut").value = "2026-02-01";
  h.document.getElementById("filtre-debut")
    .dispatchEvent(new h.window.Event("change", { bubbles: true }));
  await attendre();

  assert.equal(appels.length, 2);
  assert.equal(new URLSearchParams(appels[1].split("?")[1]).get("debut"), "2026-02-01");
});

test("amorçage : le bouton « réinitialiser » vide les filtres", async () => {
  const appels = [];
  const h = chargerCode({
    sid: "1",
    fetch: (url) => {
      appels.push(url);
      return Promise.resolve(reponseFetch(reponseValide()));
    },
  });

  await h.demarrer();

  h.document.getElementById("filtre-debut").value = "2026-02-01";
  h.document.getElementById("filtre-debut")
    .dispatchEvent(new h.window.Event("change", { bubbles: true }));
  await attendre();
  assert.equal(appels.length, 2);

  h.document.getElementById("btn-reset")
    .dispatchEvent(new h.window.MouseEvent("click", { bubbles: true }));
  await attendre();

  assert.equal(h.document.getElementById("filtre-debut").value, "");
  assert.equal(new URLSearchParams(appels[2].split("?")[1]).get("debut"), null);
});

/* --------------------------------------------------------- comparaison */

// Les quatre champs p1_debut / p1_fin / p2_debut / p2_fin sont absents du
// gabarit de test : c'est le cas réel d'une page amputée d'un bloc, qui
// devait jusque-là lever une TypeError au clic sur « Comparer ».

test("comparaison : des champs de période absents ne font pas planter", async () => {
  const appels = [];
  const h = chargerCode({
    sid: "5",
    fetch: (url) => {
      appels.push(url);
      return Promise.resolve(reponseFetch({
        periode_1: { debut: "", fin: "", ca: 100, ventes: 3, panier: 33.3, lignes: null },
        periode_2: { debut: "2026-02-01", fin: "2026-02-28", ca: 150, ventes: 4, panier: 37.5, lignes: 27 },
        variations: { ca: 50, ventes: 33.3, panier: 12.9 },
        comparable: true,
      }));
    },
  });

  await assert.doesNotReject(() => h.api.comparer());

  assert.equal(appels.length, 1);
  assert.ok(appels[0].includes("/api/comparaison"), appels[0]);
  const p = new URLSearchParams(appels[0].split("?")[1]);
  assert.equal(p.get("id"), "5");
  assert.equal(p.has("p1_debut"), false);

  const zone = h.document.getElementById("resultat-comparaison");
  assert.equal(zone.hidden, false);
  assert.ok(h.document.getElementById("comparaison-lignes").textContent.includes("Chiffre d'affaires"));
  assert.ok(h.document.getElementById("comparaison-lignes").textContent.includes("150"));
});

test("comparaison : réseau coupé → message d'erreur, pas de promesse rejetée", async () => {
  const h = chargerCode(); // fetch rejette par défaut

  await assert.doesNotReject(() => h.api.comparer());

  assert.equal(h.document.getElementById("resultat-comparaison").hidden, false);
  assert.ok(h.document.getElementById("comparaison-lignes").textContent.includes("Réseau"));
  assert.equal(h.document.getElementById("comparaison-avertissement").hidden, true);
});

test("comparaison : réponse 404 → « Analyse introuvable »", async () => {
  const h = chargerCode({
    fetch: () => Promise.resolve(reponseFetch(null, { ok: false, statut: 404 })),
  });

  await assert.doesNotReject(() => h.api.comparer());

  assert.equal(h.document.getElementById("resultat-comparaison").hidden, false);
  assert.ok(h.document.getElementById("comparaison-lignes").textContent.includes("Analyse introuvable"));
  assert.equal(h.document.getElementById("comparaison-avertissement").hidden, true);
});

test("comparaison : le bouton envoie bien les quatre bornes saisies", async () => {
  const appels = [];
  const h = chargerCode({
    sid: "9",
    fetch: (url) => {
      appels.push(url);
      return Promise.resolve(reponseFetch({
        periode_1: { debut: "2026-01-01", fin: "2026-01-31", ca: 10, ventes: 1, panier: 10, lignes: 30 },
        periode_2: { debut: "2026-02-01", fin: "2026-02-28", ca: 20, ventes: 2, panier: 10, lignes: 27 },
        variations: { ca: 100, ventes: 100, panier: 0 },
        comparable: false,
      }));
    },
  });
  // Les champs existent ici : on les recrée dans le gabarit.
  for (const [id, valeur] of [["p1_debut", "2026-01-01"], ["p1_fin", "2026-01-31"],
                              ["p2_debut", "2026-02-01"], ["p2_fin", "2026-02-28"]]) {
    const champ = h.document.createElement("input");
    champ.id = id;
    champ.value = valeur;
    h.document.body.appendChild(champ);
  }

  await h.api.comparer();

  const p = new URLSearchParams(appels[0].split("?")[1]);
  assert.equal(p.get("p1_debut"), "2026-01-01");
  assert.equal(p.get("p1_fin"), "2026-01-31");
  assert.equal(p.get("p2_debut"), "2026-02-01");
  assert.equal(p.get("p2_fin"), "2026-02-28");
  // Périodes non comparables : l'avertissement doit réapparaître.
  assert.equal(h.document.getElementById("comparaison-avertissement").hidden, false);
});
