/* Sécurité : la fonction d'échappement est la seule barrière entre un
 * fichier CSV utilisateur et le DOM. Si elle casse, un nom de colonne ou de
 * produit peut injecter du HTML/JS (XSS stocké, car les analyses sont
 * partageables). */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { chargerCode } = require("./aide");

test("échappement : neutralise les balises de script", () => {
  const { api } = chargerCode();
  assert.equal(
    api.echapper("<script>alert(1)</script>"),
    "&lt;script&gt;alert(1)&lt;/script&gt;"
  );
});

test("échappement : empêche de fermer un attribut", () => {
  const { api } = chargerCode();
  assert.equal(
    api.echapper('" onmouseover="voler(document.cookie)'),
    "&quot; onmouseover=&quot;voler(document.cookie)"
  );
});

test("échappement : couvre les cinq caractères dangereux", () => {
  const { api } = chargerCode();
  assert.equal(api.echapper(`& < > " '`), "&amp; &lt; &gt; &quot; &#39;");
});

test("échappement : ne casse pas le texte normal", () => {
  const { api } = chargerCode();
  assert.equal(api.echapper("Vis autorisé 2026"), "Vis autorisé 2026");
  assert.equal(api.echapper("Prix : 12,50 DT"), "Prix : 12,50 DT");
});

test("échappement : accepte les nombres sans les convertir en texte cassé", () => {
  const { api } = chargerCode();
  assert.equal(api.echapper(42), "42");
});

test("rendu du tableau : une colonne malveillante ne crée aucun élément", () => {
  const { api, document } = chargerCode();

  api.majTableau("table-apercu", {
    colonnes: ['<img src=x onerror="alert(1)">'],
    lignes: [["<b>gras</b>", '<svg onload="alert(1)">']],
  });

  assert.equal(document.querySelector("#table-apercu img"), null);
  assert.equal(document.querySelector("#table-apercu svg"), null);
  assert.equal(document.querySelector("#table-apercu b"), null);
  // Le texte est bien affiché, littéralement.
  assert.equal(
    document.querySelector("#table-apercu th").textContent,
    '<img src=x onerror="alert(1)">'
  );
});

test("rendu du tableau : le nombre de colonnes est respecté", () => {
  const { api, document } = chargerCode();

  api.majTableau("table-apercu", {
    colonnes: ["a", "b"],
    lignes: [["1", "2"], ["3", "4"]],
  });

  assert.equal(document.querySelectorAll("#table-apercu thead th").length, 2);
  assert.equal(document.querySelectorAll("#table-apercu tbody tr").length, 2);
  assert.equal(document.querySelectorAll("#table-apercu tbody td").length, 4);
});

test("corrélations : les noms de colonnes sont échappés", () => {
  const { api, document } = chargerCode();

  api.majCorrelations({
    paires: [{
      a: "<script>x</script>",
      b: "vitesse",
      valeur: 0.5,
      sens: "direct",
      force: "modérée",
    }],
  });

  assert.equal(document.querySelector("#table-correlations script"), null);
  assert.ok(
    document.querySelector("#table-correlations tbody td").textContent
      .includes("<script>x</script>")
  );
});

test("corrélations : la lecture et le sens sont échappés, pas seulement les noms", () => {
  const { api, document } = chargerCode();

  api.majCorrelations({
    paires: [{
      a: "puissance",
      b: "vitesse",
      valeur: 0.5,
      sens: "direct\"><script>x</script>",
      force: "<img src=x onerror=alert(1)>",
    }],
  });

  // Les tentatives d'injection restent du texte : aucune balise n'a été créée.
  assert.equal(document.querySelector("#table-correlations script"), null);
  assert.equal(document.querySelector("#table-correlations img"), null);
  const cellules = document.querySelectorAll("#table-correlations tbody td");
  assert.ok(cellules[3].textContent.includes("<img src=x onerror=alert(1)>"));
  // La jauge reste en place : le guillemet n'a pas « cassé » la classe.
  assert.equal(document.querySelectorAll(".corr-remplissage").length, 1);
});

test("tendance : les libellés produits par le serveur restent du texte", () => {
  const { api, document } = chargerCode();

  api.majTendance({
    disponible: true,
    pente: 10,
    r2: 0.9,
    unite: "<img src=x onerror=alert(1)>",
    projection_valeurs: [100],
  });

  assert.equal(document.querySelector("#tendance-grille img"), null);
  assert.ok(document.querySelector("#tendance-grille .tendance-libelle"));
});
