/* DataVision — rendu des graphiques Chart.js et gestion des filtres */
"use strict";

const SID = window.SID || "";
const API_URL = window.API_URL || "/api/donnees";
const EXPORT_URL = window.EXPORT_URL || "/export";
const COMPARISON_URL = window.COMPARISON_URL || "/api/comparaison";
/* Palette Okabe-Ito (Okabe & Ito, 2008) : six teintes conçues pour rester
 * distinguables sous les formes les plus courantes de daltonisme
 * (deutéranopie, protanopie, tritanopie), sur fond clair comme sur fond
 * sombre. L'ordre place en tête le bleu de la courbe réelle ; le Top 5
 * s'en tient à une palette sans vermillon pour que le Flop, juste à côté,
 * reste la seule série « rouge » — le sens négatif ne dépend alors jamais
 * de la seule nuance. */
const PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9", "#E69F00"];
const PALETTE_TOP = PALETTE.filter((c) => c !== "#D55E00");
/* Variante « marque » (thème personnalisé façon Datawrapper) : une famille
 * teal → cyan, activable au choix depuis le tableau de bord. Le défaut
 * reste Okabe-Ito, seule palette certifiée daltonisme par les tests. */
const PALETTE_MARQUE = ["#0B6E7F", "#0D8798", "#0FA3B0", "#17BCC4", "#3BCFD0", "#67DED6"];

// Palette effective : variante marque si elle est mémorisée, sinon Okabe-Ito.
function paletteActive() {
  try {
    return window.localStorage.getItem("datavision-palette") === "marque"
      ? PALETTE_MARQUE
      : PALETTE;
  } catch (e) {
    return PALETTE;
  }
}

function enModeMarque() {
  return paletteActive() === PALETTE_MARQUE;
}

function majLibellePalette() {
  const el = document.getElementById("btn-palette-libelle");
  if (el) el.textContent = enModeMarque() ? "Palette : teal" : "Palette : Okabe-Ito";
}

/* Dégradé de marque horizontal : il s'étale sur toute la largeur du
 * graphique et chaque barre (ou pastille) en prélève sa portion — les
 * valeurs courtes restent teal, les longues atteignent le cyan. */
function degradeBarres(chart, debut, fin) {
  if (!chart || !chart.chartArea || !chart.ctx) return debut;
  const g = chart.ctx.createLinearGradient(chart.chartArea.left, 0, chart.chartArea.right, 0);
  g.addColorStop(0, debut);
  g.addColorStop(1, fin);
  return g;
}
const charts = {};
// Page courante de l'aperçu : réinitialisée à chaque changement de filtre.
let pageApercu = 1;

// Mouvement réduit demandé au système : aucune animation des graphiques.
function animationsReduites() {
  return typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

// Apparitions subtiles façon Flourish : ~650 ms, tracé progressif des
// courbes et cascade légère des barres. Désactivées si le système le demande.
function animations() {
  if (animationsReduites()) return false;
  return {
    duration: 650,
    easing: "easeOutQuart",
    delay: (ctx) =>
      ctx.type === "data" && ctx.mode === "default"
        ? Math.min(ctx.dataIndex * 35, 280)
        : 0,
  };
}

/* Effet « focus » au survol d'une barre : les autres s'atténuent sous un
 * voile à la couleur de fond, la donnée visée reste seule en couleur. */
const voileBarres = {
  id: "voileBarres",
  afterDatasetsDraw(graphe, args, opts) {
    if (!opts || !opts.actif) return;
    const actifs = graphe.tooltip ? graphe.tooltip.getActiveElements() : [];
    if (!actifs.length || !actifs[0].element || actifs[0].element.base === undefined) return;
    const el = actifs[0].element;
    const { ctx, chartArea } = graphe;
    const teinte = getComputedStyle(document.body).getPropertyValue("--carte").trim();
    ctx.save();
    ctx.fillStyle = /^#[0-9a-f]{6}$/i.test(teinte) ? teinte + "9e" : "rgba(255, 255, 255, 0.62)";
    const vertical = opts.axe !== "x";
    const largeur = Math.max(el.width || 0, 1);
    const hauteur = Math.max(el.height || 0, 1);
    const bx1 = vertical ? el.x - largeur / 2 : Math.min(el.x, el.base);
    const bx2 = vertical ? el.x + largeur / 2 : Math.max(el.x, el.base);
    const by1 = vertical ? Math.min(el.y, el.base) : el.y - hauteur / 2;
    const by2 = vertical ? Math.max(el.y, el.base) : el.y + hauteur / 2;
    // Marge utile sur les barres à puces : la pastille dépasse la tige.
    const garde = opts.garde || 0;
    const gx1 = bx1 - garde;
    const gx2 = bx2 + garde;
    const gy1 = by1 - garde;
    const gy2 = by2 + garde;
    const { left, top, right, bottom } = chartArea;
    ctx.fillRect(left, top, right - left, Math.max(gy1 - top, 0));
    ctx.fillRect(left, gy2, right - left, Math.max(bottom - gy2, 0));
    ctx.fillRect(left, gy1, Math.max(gx1 - left, 0), Math.max(gy2 - gy1, 0));
    ctx.fillRect(gx2, gy1, Math.max(right - gx2, 0), Math.max(gy2 - gy1, 0));
    ctx.restore();
  },
};

// Chart.js n'existe pas sous Node (tests) : l'amorçage des styles est optionnel.
if (typeof Chart !== "undefined" && Chart.defaults) {
  Chart.defaults.font.family = '"Inter", "Segoe UI", system-ui, sans-serif';
  Chart.defaults.color = "#69707a";
  if (Chart.register) Chart.register(voileBarres);
}

// ---------- Formats ----------

// NaN peut remonter d'une division par zéro côté serveur (panier moyen sur
// un mois sans vente) : on l'affiche comme une donnée absente.
const formatDT = (v) => (v == null || Number.isNaN(v) ? "—" : new Intl.NumberFormat("fr-FR").format(v) + " DT");
const formatNombre = (v) => (v == null || Number.isNaN(v) ? "—" : new Intl.NumberFormat("fr-FR").format(v));

function echapper(valeur) {
  return String(valeur).replace(/[&<>"']/g, (m) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

// ---------- Requête avec filtres ----------

function parametresRequete() {
  const p = new URLSearchParams({ id: SID });
  const cat = document.getElementById("filtre-categorie").value;
  const debut = document.getElementById("filtre-debut").value;
  const fin = document.getElementById("filtre-fin").value;
  if (cat) p.set("categorie", cat);
  if (debut) p.set("debut", debut);
  if (fin) p.set("fin", fin);
  return p.toString();
}

// ---------- Graphiques ----------

// ---------- Styles des graphiques ----------

// Lit une variable CSS réelle : les graphiques suivent donc le thème actif.
function couleur(nom, defaut) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(nom);
  return (v && v.trim()) || defaut;
}

// Aire dégradée sous une courbe, du plus opaque au transparent.
function aire(canvas, hex) {
  const ctx = canvas.getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 0, (canvas.clientHeight || 300));
  grad.addColorStop(0, hex + "59"); // ~35 % d'opacité
  grad.addColorStop(1, hex + "00");
  return grad;
}

// Infobulle aux coins arrondis, aux couleurs du thème courant.
function infobulle(formatage) {
  return {
    backgroundColor: couleur("--carte", "#ffffff"),
    titleColor: couleur("--texte", "#16181d"),
    bodyColor: couleur("--texte-doux", "#69707a"),
    borderColor: couleur("--bordure", "#e3e6ea"),
    borderWidth: 1,
    padding: 12,
    cornerRadius: 12,
    boxPadding: 6,
    caretSize: 6,
    usePointStyle: true,
    titleFont: { weight: "700", size: 12 },
    bodyFont: { size: 12.5 },
    displayColors: true,
    callbacks: { label: formatage },
  };
}

// Légende cliquable : le clic masque ou réaffiche une série. Puces rondes
// sous le graphique, dans le gris du texte courant.
function legendeCliquable() {
  return {
    usePointStyle: true,
    pointStyle: "circle",
    boxWidth: 8,
    boxHeight: 8,
    padding: 16,
    color: couleur("--texte-doux", "#69707a"),
    font: { size: 11.5, weight: "600" },
  };
}

function axeX(extra = {}) {
  return {
    grid: { display: false },
    border: { display: false },
    ticks: { color: couleur("--texte-doux", "#69707a"), font: { size: 11 }, maxRotation: 0 },
    ...extra,
  };
}

function axeY(extra = {}) {
  return {
    // Filets pleins et très clairs : la grille structure sans casser la lecture.
    grid: { color: couleur("--bordure-fine", "#edeff2"), drawTicks: false },
    border: { display: false },
    ticks: {
      color: couleur("--texte-doux", "#69707a"),
      padding: 8,
      font: { size: 11 },
      callback: (v) => formatNombre(v),
    },
    ...extra,
  };
}

// Axes pour les barres horizontales (Top / Flop) : valeur en x, libellé en y.
// Mise en page façon Datawrapper : graduations en haut, libellés de
// catégories en gras à gauche, collés aux pastilles.
function axesBarreH() {
  return {
    x: axeY({
      position: "top",
      ticks: { color: couleur("--texte-doux", "#69707a"), font: { size: 11 }, callback: (v) => formatNombre(v) },
    }),
    y: axeX({
      ticks: { color: couleur("--texte", "#16181d"), font: { size: 12.5, weight: "700" }, padding: 10 },
    }),
  };
}

function commun(plugins, scales) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    animation: animations(),
    // Clic dans la zone de tracé : la vue détaillée s'ouvre (voir plus bas).
    onClick: clicModale,
    plugins,
    scales,
  };
}

function creerGraphiques() {
  // Une vue détaillée ouverte porte sur des graphiques qui vont disparaître :
  // on la referme avant de reconstruire (changement de thème ou de palette).
  fermerModale();
  // Permet de reconstruire les graphiques (changement de thème) sans doublon.
  Object.values(charts).forEach((c) => c && c.destroy());
  Object.keys(charts).forEach((k) => delete charts[k]);

  // Palette courante : Okabe-Ito par défaut, variante « marque » au choix.
  const palette = paletteActive();
  const marque = palette !== PALETTE;
  const paletteTop = marque ? palette.slice(0, 5) : PALETTE_TOP;

  const canvasEvolution = document.getElementById("chart-evolution");

  charts.evolution = new Chart(canvasEvolution, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Chiffre d'affaires (DT)",
          data: [],
          borderColor: palette[0],
          backgroundColor: aire(canvasEvolution, palette[0]),
          fill: true,
          tension: 0.4,
          borderWidth: 2.5,
          pointRadius: 3,
          pointHoverRadius: 7,
          pointBackgroundColor: palette[0],
          pointHoverBackgroundColor: palette[0],
          pointHoverBorderColor: "#fff",
          pointHoverBorderWidth: 2,
        },
        {
          // Projection par régression linéaire : en pointillés pour bien
          // distinguer une extrapolation d'une mesure réelle. C'est le même
          // bleu que la courbe réelle, éclairci — la nuance dit « version
          // affaiblie », le pointillé dit « pas encore mesurée ».
          label: "Projection",
          data: [],
          borderColor: palette[4],
          borderDash: [7, 5],
          fill: false,
          tension: 0.4,
          borderWidth: 2.5,
          pointRadius: 0,
          pointHoverRadius: 6,
        },
      ],
    },
    // Plugin maison : anneau + étiquettes sur max / min / variations.
    plugins: [annotationsCourbe],
    options: commun(
      {
        legend: { display: true, position: "bottom", labels: legendeCliquable() },
        tooltip: infobulle((c) => " " + formatDT(c.parsed.y)),
      },
      { x: axeX(), y: axeY() }
    ),
  });

  charts.categories = new Chart(document.getElementById("chart-categories"), {
    type: "bar",
    data: {
      labels: [],
      datasets: [{
        label: "Chiffre d'affaires (DT)",
        data: [],
        // En mode marque, la barre prélève sa portion du dégradé horizontal
        // de la marque ; en défaut, le bleu Okabe-Ito, plat et certifié.
        backgroundColor: marque
          ? (ctx) => degradeBarres(ctx.chart, palette[0], palette[3])
          : PALETTE[0],
        hoverBackgroundColor: marque ? palette[0] : "#005A8F", // le bleu principal assombri
        borderRadius: 8,
        borderSkipped: false,
        maxBarThickness: 48,
      }],
    },
    options: commun(
      {
        legend: { display: false },
        tooltip: infobulle((c) => " " + formatDT(c.parsed.y)),
        voileBarres: { actif: true, axe: "y" },
      },
      { x: axeX(), y: axeY() }
    ),
  });

  charts.repartition = new Chart(document.getElementById("chart-repartition"), {
    type: "doughnut",
    data: {
      labels: [],
      datasets: [{
        data: [],
        backgroundColor: palette,
        borderColor: couleur("--carte", "#ffffff"),
        borderWidth: 3,
        hoverOffset: 14,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: animations(),
      cutout: "68%",
      onClick: clicModale,
      plugins: {
        legend: {
          position: "right",
          labels: {
            usePointStyle: true,
            pointStyle: "circle",
            boxWidth: 9,
            boxHeight: 9,
            padding: 14,
            color: couleur("--texte-doux", "#64748b"),
            font: { size: 12 },
          },
        },
        tooltip: infobulle((c) => " " + c.label + " : " + formatDT(c.parsed)),
      },
    },
  });

  const optionsBarres = (axe) => commun(
    {
      legend: { display: false },
      tooltip: {
        ...infobulle((c) => " " + formatDT(c.parsed.x)),
        // La tige et sa pastille portent la même valeur : une seule ligne.
        filter: (item) => item.datasetIndex === 1,
      },
      voileBarres: { actif: true, axe: "x", garde: 9 },
    },
    axe
  );

  // Dispersion : la paire de colonnes la plus corrélée, avec sa droite de
  // régression. La carte est masquée tant que le serveur ne renvoie rien
  // d'exploitable — le graphique, lui, est créé d'emblée pour que le
  // premier affichage ne ait pas à le construire à chaud.
  charts.nuage = new Chart(document.getElementById("chart-nuage"), {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Observations",
          data: [],
          // 70 % d'opacité : quand les points se superposent, leur densité
          // reste lisible au lieu de former une seule tache opaque.
          backgroundColor: palette[0] + "B3",
          hoverBackgroundColor: palette[0],
          pointRadius: 3,
          pointHoverRadius: 6,
        },
        {
          // Une régression linéaire est toujours bleu éclairci en pointillés,
          // comme la projection de la courbe d'évolution.
          label: "Droite de régression",
          data: [],
          type: "line",
          borderColor: palette[4],
          borderDash: [7, 5],
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: commun(
      {
        legend: { display: true, position: "bottom", labels: legendeCliquable() },
        tooltip: infobulle((c) => ` ${formatNombre(c.parsed.x)} × ${formatNombre(c.parsed.y)}`),
      },
      {
        x: axeX({ title: { display: false } }),
        y: axeY({ title: { display: false } }),
      }
    ),
  });

  // Barres à puces (lollipop) : une tige fine grise, une pastille colorée —
  // l'allure « prête publication » de Datawrapper, mêmes données qu'avant.
  charts.top = new Chart(document.getElementById("chart-top"), {
    type: "bar",
    data: {
      labels: [],
      datasets: [
        {
          label: "Tige",
          data: [],
          backgroundColor: couleur("--bordure", "#e3e6ea"),
          barThickness: 3,
          maxBarThickness: 3,
          borderRadius: 0,
          borderSkipped: false,
        },
        {
          label: "Chiffre d'affaires (DT)",
          type: "scatter",
          data: [],
          pointRadius: 7,
          pointHoverRadius: 9,
          pointHitRadius: 12,
          // En mode marque, chaque pastille prélève le dégradé à sa position ;
          // en défaut, une teinte Okabe-Ito par barre.
          pointBackgroundColor: marque
            ? (ctx) => degradeBarres(ctx.chart, palette[0], palette[3])
            : paletteTop,
          pointHoverBackgroundColor: marque ? palette[0] : paletteTop,
        },
      ],
    },
    options: { ...optionsBarres(axesBarreH()), indexAxis: "y" },
  });

  charts.flop = new Chart(document.getElementById("chart-flop"), {
    type: "bar",
    data: {
      labels: [],
      datasets: [
        {
          label: "Tige",
          data: [],
          backgroundColor: couleur("--bordure", "#e3e6ea"),
          barThickness: 3,
          maxBarThickness: 3,
          borderRadius: 0,
          borderSkipped: false,
        },
        {
          // Vermillon d'Okabe-Ito : accessible sur les deux thèmes et porteur
          // du sens « négatif ». Il est conservé tel quel aussi en mode
          // marque — le rouge du Flop ne dépend jamais de la teinte de marque.
          label: "Chiffre d'affaires (DT)",
          type: "scatter",
          data: [],
          pointRadius: 7,
          pointHoverRadius: 9,
          pointHitRadius: 12,
          pointBackgroundColor: "#D55E00",
          pointHoverBackgroundColor: "#9C4400",
        },
      ],
    },
    options: { ...optionsBarres(axesBarreH()), indexAxis: "y" },
  });
}

// ---------- Mises à jour ----------

function majKpis(k) {
  const formats = {
    ca_total: formatDT,
    nb_ventes: formatNombre,
    panier_moyen: formatDT,
    produits_vendus: formatNombre,
    nb_categories: formatNombre,
    valeurs_manquantes: formatNombre,
  };
  for (const [nom, formater] of Object.entries(formats)) {
    const el = document.querySelector(`[data-kpi="${nom}"]`);
    if (el) el.textContent = formater(k[nom]);
  }
}

// Synthèse en langage naturel : le serveur écrit les phrases, on se
// contente de les poser. textContent (et non innerHTML) garantit qu'un
// nom de produit ne peut pas injecter de HTML.
function majResume(texte) {
  const carte = document.getElementById("carte-resume");
  const zone = document.getElementById("resume-texte");
  if (!carte || !zone) return;
  if (!texte) {
    carte.hidden = true;
    return;
  }
  zone.textContent = texte;
  carte.hidden = false;
}

function majTableau(id, donnees) {
  const table = document.getElementById(id);
  if (!table || !donnees) return;
  const entetes = donnees.colonnes.map((c) => `<th>${echapper(c)}</th>`).join("");
  const lignes = donnees.lignes
    .map((ligne) => `<tr>${ligne.map((v) => `<td>${echapper(v)}</td>`).join("")}</tr>`)
    .join("");
  const vide = `<tr><td colspan="${donnees.colonnes.length || 1}">Aucune ligne pour ces filtres.</td></tr>`;
  table.innerHTML = `<thead><tr>${entetes}</tr></thead><tbody>${lignes || vide}</tbody>`;
}

function majPagination(apercu) {
  const zone = document.getElementById("apercu-pagination");
  if (!zone) return;

  if (!apercu || apercu.pages <= 1) {
    zone.hidden = true;
    zone.innerHTML = "";
    return;
  }

  zone.hidden = false;
  zone.innerHTML = `
    <button type="button" class="btn btn-fantome" data-page="${apercu.page - 1}"
            ${apercu.page <= 1 ? "disabled" : ""}>← Précédent</button>
    <span class="pagination-info">Page ${apercu.page} sur ${apercu.pages} · ${apercu.total} lignes</span>
    <button type="button" class="btn btn-fantome" data-page="${apercu.page + 1}"
            ${apercu.page >= apercu.pages ? "disabled" : ""}>Suivant →</button>`;
}

function majExports() {
  document.querySelectorAll("[data-export]").forEach((lien) => {
    lien.href = EXPORT_URL + "?" + parametresRequete() + "&format=" + lien.dataset.export;
  });
  document.querySelectorAll("[data-rapport]").forEach((lien) => {
    lien.href = lien.getAttribute("data-base") + "?" + parametresRequete();
  });
}

// ---------- Export PNG d'un graphique ----------

// Retrouve le graphique Chart.js à partir de l'id de son canvas.
function graphiqueDe(idCanvas) {
  return Object.values(charts).find((c) => c && c.canvas && c.canvas.id === idCanvas) || null;
}

// Nom de fichier lisible : le titre de la carte, sans accents ni symboles.
// Le clone perd le bouton et la légende de projection, qui ne sont pas le sujet.
function nomFichierPNG(idCanvas) {
  const chart = graphiqueDe(idCanvas);
  const carte = chart && chart.canvas.closest ? chart.canvas.closest(".carte") : null;
  const titre = carte ? carte.querySelector("h3") : null;
  let brut = idCanvas;
  if (titre) {
    const clone = titre.cloneNode(true);
    clone.querySelectorAll("button, .legende-projection").forEach((n) => n.remove());
    brut = clone.textContent;
  }
  const propre = brut
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  return `datavision-${propre || "graphique"}.png`;
}

// ---------- En-tête des exports PNG ----------
//
// Un export Datawrapper porte toujours son contexte avec lui (titre, note,
// source). On repeint la même hiérarchie au-dessus de la toile avant le
// téléchargement : une image montrée ailleurs reste lisible et citable.

// Ce que l'en-tête peut contenir : le titre vient du template (window),
// la note et la source de l'analyste lui-même.
function infosExport() {
  return {
    titre: String(window.PROJET_NOM || ""),
    note: String(window.NOTE_ANALYSTE || ""),
    source: String(window.SOURCE_DONNEES || ""),
  };
}

// Hauteur réservée à l'en-tête. Ne dépend que des champs présents — pas
// du canvas — ce qui rend le calcul vérifiable sans dessiner.
function hauteurEntetePNG(infos) {
  if (!infos || !infos.titre) return 0;
  let hauteur = 14 + 20 + 10; // marge haute, ligne de titre, respiration
  if (infos.note) hauteur += 16;
  if (infos.source) hauteur += 16;
  return hauteur;
}

// Coupe un texte avec « … » pour qu'il tienne dans `max` pixels.
function texteCoupe(ctx, texte, max) {
  if (typeof ctx.measureText !== "function") return texte;
  if (ctx.measureText(texte).width <= max) return texte;
  let coupe = texte;
  while (coupe.length > 1 && ctx.measureText(coupe + "…").width > max) {
    coupe = coupe.slice(0, -1);
  }
  return coupe + "…";
}

// Repeint titre, note et source au-dessus du graphique, puis trace un
// filet de séparation. Renvoie la hauteur dessinée.
function dessinerEntetePNG(ctx, largeur, infos) {
  const hauteur = hauteurEntetePNG(infos);
  if (!hauteur || typeof ctx.fillText !== "function") return 0;
  const marge = 14;
  let y = marge + 14; // ligne de base du titre

  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.font = '700 15px "Segoe UI", system-ui, sans-serif';
  ctx.fillStyle = couleur("--texte", "#16203a");
  ctx.fillText(texteCoupe(ctx, infos.titre, largeur - 2 * marge), marge, y);

  if (infos.note) {
    y += 16;
    ctx.font = '400 11.5px "Segoe UI", system-ui, sans-serif';
    ctx.fillStyle = couleur("--texte-doux", "#64748b");
    ctx.fillText(texteCoupe(ctx, infos.note, largeur - 2 * marge), marge, y);
  }
  if (infos.source) {
    y += 16;
    ctx.font = 'italic 400 11px "Segoe UI", system-ui, sans-serif';
    ctx.fillStyle = couleur("--texte-doux", "#64748b");
    ctx.fillText(
      texteCoupe(ctx, `Source : ${infos.source}`, largeur - 2 * marge),
      marge, y
    );
  }
  // Filet discret entre le contexte et le graphique.
  ctx.fillStyle = couleur("--bordure", "#e5e9f2");
  ctx.fillRect(marge, hauteur - 1, largeur - 2 * marge, 1);
  return hauteur;
}

// Télécharge un graphique au format PNG.
//
// Le canvas de Chart.js est transparent : l'exporter tel quel produirait,
// en thème sombre, du texte clair sur fond transparent — illisible dans la
// plupart des visionneuses. On redessine donc l'image sur une toile opaque
// peinte avec la couleur de carte du thème courant, précédée de l'en-tête.
function exporterPNG(idCanvas, nomFichier) {
  const chart = graphiqueDe(idCanvas);
  if (!chart || typeof chart.toBase64Image !== "function") return false;

  const infos = infosExport();
  const hauteur = hauteurEntetePNG(infos);
  const source = chart.canvas;
  const cible = document.createElement("canvas");
  cible.width = source.width || 800;
  cible.height = (source.height || 300) + hauteur;

  const ctx = cible.getContext("2d");
  ctx.fillStyle = couleur("--carte", "#ffffff");
  ctx.fillRect(0, 0, cible.width, cible.height);
  if (hauteur) dessinerEntetePNG(ctx, cible.width, infos);
  ctx.drawImage(source, 0, hauteur);

  const lien = document.createElement("a");
  lien.href = cible.toDataURL("image/png");
  lien.download = nomFichier || nomFichierPNG(idCanvas);
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  return true;
}

// ---------- Vue détaillée d'un graphique (modale) ----------
//
// Un clic dans la zone de tracé ouvre la version en grand : mêmes données,
// mêmes couleurs, plus d'espace pour lire et pour infobuler. La fenêtre vit
// dans le gabarit (dashboard.html) ; le code ne fait que la remplir et la
// refermer. Sans gabarit (tests), tout ceci est simplement sans effet.

const CANVAS_MODALE = "canvas-modale";

// Info-bulle par graphique : la vue détaillée formate comme l'original.
const formatModale = {
  "chart-evolution": (c) => " " + formatDT(c.parsed.y),
  "chart-categories": (c) => " " + formatDT(c.parsed.y),
  "chart-repartition": (c) => " " + c.label + " : " + formatDT(c.parsed),
  "chart-top": (c) => " " + formatDT(c.parsed.x),
  "chart-flop": (c) => " " + formatDT(c.parsed.x),
  "chart-nuage": (c) => ` ${formatNombre(c.parsed.x)} × ${formatNombre(c.parsed.y)}`,
};

// Titre repris de la carte d'origine : le clone perd le bouton d'export, le
// badge et la légende de projection, qui ne sont pas le sujet du titre.
function titreGraphique(idCanvas) {
  const chart = graphiqueDe(idCanvas);
  const carte = chart && chart.canvas.closest ? chart.canvas.closest(".carte") : null;
  const titre = carte ? carte.querySelector("h3") : null;
  if (!titre) return "Graphique";
  const clone = titre.cloneNode(true);
  clone.querySelectorAll("button, .badge, .legende-projection").forEach((n) => n.remove());
  return clone.textContent.replace(/\s+/g, " ").trim();
}

// Copie des valeurs d'un graphique : la vue détaillée est peinte sans que la
// source bouge, ni l'inverse. Dégradés et couleurs scriptables (fonctions)
// sont partagés tels quels — seules les données sont dupliquées.
function clonerValeurs(v) {
  if (Array.isArray(v)) return v.map(clonerValeurs);
  if (v && typeof v === "object") {
    if (typeof v.addColorStop === "function") return v; // dégradé Canvas
    const copie = {};
    Object.keys(v).forEach((cle) => { copie[cle] = clonerValeurs(v[cle]); });
    return copie;
  }
  return v;
}

function clonerDonnees(d) {
  if (!d) return { labels: [], datasets: [] };
  return {
    labels: Array.isArray(d.labels) ? [...d.labels] : [],
    datasets: (d.datasets || []).map((jeu) => ({ ...jeu, data: clonerValeurs(jeu.data) })),
  };
}

// Options de la vue détaillée : la mise en page d'origine (barres
// horizontales, anneau, légende) est reconstruite à la taille de la fenêtre.
function optionsModale(idCanvas, source) {
  const infobulleModale = infobulle(formatModale[idCanvas] || ((c) => " " + formatNombre(c.parsed.y)));

  if (source.config.type === "doughnut") {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: animations(),
      cutout: "68%",
      onClick: clicModale,
      plugins: {
        legend: {
          position: "right",
          labels: {
            usePointStyle: true,
            pointStyle: "circle",
            boxWidth: 9,
            boxHeight: 9,
            padding: 14,
            color: couleur("--texte-doux", "#64748b"),
            font: { size: 12 },
          },
        },
        tooltip: infobulleModale,
      },
    };
  }

  const horizontal = !!(source.config.options && source.config.options.indexAxis === "y");
  const options = commun(
    {
      legend: {
        // Seules les séries multiples portent une légende, comme sur la carte.
        display: source.config.type === "line" || source.config.type === "scatter",
        position: "bottom",
        labels: legendeCliquable(),
      },
      tooltip: infobulleModale,
      voileBarres: horizontal ? { actif: true, axe: "x", garde: 9 } : { actif: true, axe: "y" },
    },
    horizontal ? axesBarreH() : { x: axeX(), y: axeY() }
  );
  if (horizontal) options.indexAxis = "y";
  return options;
}

// Ouvre la vue détaillée d'un graphique du tableau de bord.
// Renvoie false quand rien n'est ouvrable (gabarit absent ou id inconnu).
function ouvrirModale(idCanvas) {
  const source = graphiqueDe(idCanvas);
  const boite = document.getElementById("modale-graphique");
  const canvas = document.getElementById(CANVAS_MODALE);
  if (!source || !boite || !canvas) return false;

  const titre = titreGraphique(idCanvas);
  const elTitre = document.getElementById("modale-titre");
  if (elTitre) elTitre.textContent = titre;
  const elInfo = document.getElementById("modale-info-titre");
  if (elInfo) elInfo.textContent = titre;

  // Une seule vue à la fois : un éventuel graphique déjà ouvert est libéré.
  fermerModale();

  // L'aire dégradée de la courbe était calculée pour la hauteur de sa carte :
  // on la retisse pour la hauteur de la fenêtre.
  const donnees = clonerDonnees(source.data);
  donnees.datasets.forEach((jeu) => {
    if (jeu.fill && jeu.borderColor) jeu.backgroundColor = aire(canvas, jeu.borderColor);
  });

  charts.modale = new Chart(canvas, {
    type: source.config.type,
    data: donnees,
    plugins: Array.isArray(source.config.plugins) ? [...source.config.plugins] : undefined,
    options: optionsModale(idCanvas, source),
  });
  // Les annotations de la courbe (max, min, variations) suivent l'ouverture.
  if (source.$annotations) charts.modale.$annotations = source.$annotations;

  boite.hidden = false;
  document.body.classList.add("modale-ouverte");
  const fermeture = document.getElementById("modale-fermer");
  if (fermeture && typeof fermeture.focus === "function") fermeture.focus();
  return true;
}

// Referme la vue détaillée et libère son graphique.
function fermerModale() {
  if (charts.modale) {
    charts.modale.destroy();
    delete charts.modale;
  }
  const boite = document.getElementById("modale-graphique");
  if (!boite) return false;
  boite.hidden = true;
  document.body.classList.remove("modale-ouverte");
  return true;
}

// Clic relevé par Chart.js : il n'ouvre la vue détaillée que depuis la zone
// de tracé. La légende est dessinée en dehors — elle garde son rôle (masquer
// ou réafficher une série) sans ouvrir de fenêtre.
function clicModale(evenement, elements, chart) {
  const id = chart && chart.canvas ? chart.canvas.id : "";
  if (!id || id === CANVAS_MODALE) return;
  const zone = chart.chartArea;
  if (!zone || !evenement || typeof evenement.x !== "number" || typeof evenement.y !== "number") return;
  const dedans = evenement.x >= zone.left && evenement.x <= zone.right
    && evenement.y >= zone.top && evenement.y <= zone.bottom;
  if (dedans) ouvrirModale(id);
}

// ---------- Phase E : tendance, Flop et corrélations ----------

function majProjection(t, mois, ca) {
  const labels = [...mois];
  const reel = [...ca];
  const projete = [];

  if (t && t.disponible && t.projection_valeurs.length) {
    // Le trait pointillé s'ancre sur le dernier point réel pour être lisible.
    for (let i = 0; i < Math.max(0, mois.length - 1); i++) projete.push(null);
    projete.push(ca[ca.length - 1]);
    projete.push(...t.projection_valeurs);
    labels.push(...t.projection_labels);
    reel.push(...t.projection_valeurs.map(() => null));
  }

  charts.evolution.data.labels = labels;
  charts.evolution.data.datasets[0].data = reel;
  charts.evolution.data.datasets[1].data = projete;
  // Les annotations ne portent que sur les mois réels (l'index de `mois`
  // correspond aux `mois.length` premiers points de la courbe).
  charts.evolution.$annotations = calculerAnnotations(mois, ca);
  charts.evolution.update();
}

// ---------- Annotations sur la courbe (inspiré de Datawrapper) ----------
//
// Datawrapper pose ses annotations « de façon à ce qu'elles s'effacent
// quand elles gênent ». On garde ici quatre points remarquables au plus :
// le maximum, le minimum, la plus forte baisse et la plus forte hausse —
// et jamais deux libellés voisins, puisqu'une étiquette qui en recouvre
// une autre ne vaut pas mieux qu'aucune.

// Calcule les annotations à dessiner sur la courbe d'évolution.
// Renvoie une liste de { index, type, texte, auDessus } ; liste vide si la
// série est trop courte, constante ou incomplète (rien à raconter).
function calculerAnnotations(mois, ca) {
  if (!Array.isArray(mois) || !Array.isArray(ca)) return [];
  const n = Math.min(mois.length, ca.length);
  if (n < 3) return [];
  const valeurs = ca.slice(0, n).map(Number);
  if (!valeurs.every((v) => Number.isFinite(v))) return [];
  const maximum = Math.max(...valeurs);
  const minimum = Math.min(...valeurs);
  if (maximum === minimum) return []; // ligne plate : aucune originalité

  const iMax = valeurs.indexOf(maximum);
  const iMin = valeurs.indexOf(minimum);
  // « mars 2026 » → « mars » : l'étiquette doit tenir sur la courbe.
  const moisCourt = (i) => String(mois[i] || "").split(" ")[0];

  const annotations = [
    { index: iMax, type: "max", texte: `Max : ${formatDT(maximum)}`, auDessus: true },
    { index: iMin, type: "min", texte: `Min : ${formatDT(minimum)}`, auDessus: false },
  ];

  if (n >= 4) {
    let pire = null;   // plus forte baisse (strictement négative)
    let meilleur = null; // plus forte hausse (strictement positive)
    for (let i = 1; i < n; i++) {
      if (!valeurs[i - 1]) continue; // division par zéro ignorée
      const pct = ((valeurs[i] - valeurs[i - 1]) / valeurs[i - 1]) * 100;
      if (pct < 0 && (!pire || pct < pire.pct)) pire = { index: i, pct };
      if (pct > 0 && (!meilleur || pct > meilleur.pct)) meilleur = { index: i, pct };
    }
    const signe = (v) =>
      `${v > 0 ? "+" : "−"}${Math.round(Math.abs(v))} %`;

    for (const [candidat, type] of [[pire, "baisse"], [meilleur, "hausse"]]) {
      if (!candidat || !Number.isFinite(candidat.pct)) continue;
      if (Math.round(Math.abs(candidat.pct)) === 0) continue; // « 0 % » : rien à dire
      // Ni sur un point déjà annoté, ni juste à côté d'un autre libellé :
      // les étiquettes se remplacent, elles ne se bousculent pas.
      const tropProche = annotations.some(
        (a) => Math.abs(a.index - candidat.index) <= 1
      );
      if (tropProche) continue;
      annotations.push({
        index: candidat.index,
        type,
        texte: `${signe(candidat.pct)} en ${moisCourt(candidat.index)}`,
        auDessus: candidat.pct > 0,
      });
    }
  }
  return annotations;
}

// Teinte d'anneau par type, dans la palette courante : teinte principale
// pour les extrêmes, troisième pour la hausse, deuxième pour la baisse.
function teintesAnnotation() {
  const p = paletteActive();
  return { max: p[0], min: p[0], hausse: p[2], baisse: p[1] };
}

// Plugin maison (aucune dépendance) : repère les points remarquables de
// la courbe. Un anneau cerne le point ; le libellé n'apparaît qu'au-delà
// de 480 px de large — sur mobile, l'annotation dérange plus qu'elle
// n'éclaire.
const annotationsCourbe = {
  id: "annotations-courbe",
  afterDatasetsDraw(chart) {
    const liste = chart.$annotations;
    if (!Array.isArray(liste) || !liste.length) return;
    const meta = typeof chart.getDatasetMeta === "function"
      ? chart.getDatasetMeta(0) : null;
    if (!meta || !Array.isArray(meta.data) || !meta.data.length) return;

    const ctx = chart.ctx;
    if (!ctx || typeof ctx.arc !== "function") return;
    const etroit = (chart.width || 0) < 480;
    const fond = couleur("--carte", "#ffffff");
    const texte = couleur("--texte-doux", "#64748b");
    const contour = couleur("--bordure", "#e5e9f2");
    const hauteur = 20;

    for (const ann of liste) {
      const point = meta.data[ann.index];
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) continue;

      ctx.save();
      ctx.beginPath();
      ctx.arc(point.x, point.y, 6, 0, Math.PI * 2);
      ctx.lineWidth = 2;
      ctx.strokeStyle = teintesAnnotation()[ann.type] || paletteActive()[0];
      ctx.stroke();
      ctx.restore();
      if (etroit) continue; // mobile : le repère suffit

      ctx.save();
      ctx.font = '600 11px "Segoe UI", system-ui, sans-serif';
      const largeur = ctx.measureText(ann.texte).width + 16;
      // Centré sur le point, mais jamais contre un bord du graphique.
      let x = Math.max(4, Math.min(point.x - largeur / 2, chart.width - largeur - 4));
      let y = ann.auDessus ? point.y - 10 - hauteur : point.y + 10;
      y = Math.max(4, Math.min(y, chart.height - hauteur - 4));

      ctx.beginPath();
      if (typeof ctx.roundRect === "function") ctx.roundRect(x, y, largeur, hauteur, 6);
      else ctx.rect(x, y, largeur, hauteur);
      ctx.fillStyle = fond;
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = contour;
      ctx.stroke();
      ctx.fillStyle = texte;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(ann.texte, x + largeur / 2, y + hauteur / 2 + 0.5);
      ctx.restore();
    }
  },
};

function majTendance(t) {
  const carte = document.getElementById("carte-tendance");
  const grille = document.getElementById("tendance-grille");
  const legende = document.getElementById("legende-projection");
  if (!carte || !grille) return;

  if (!t || !t.disponible) {
    carte.hidden = true;
    if (legende) legende.hidden = true;
    return;
  }

  const confiance = t.r2 >= 0.7 ? "modèle solide" : t.r2 >= 0.4 ? "modèle indicatif" : "données trop irrégulières";
  const dernier = t.projection_valeurs[t.projection_valeurs.length - 1];
  const signe = t.pente > 0 ? "+" : "";

  const blocs = [
    {
      libelle: `Pente par ${t.unite}`,
      valeur: `${signe}${formatNombre(t.pente)} DT`,
      detail: t.pente > 0 ? "▲ tendance à la hausse" : t.pente < 0 ? "▼ tendance à la baisse" : "＝ stable",
      classe: t.pente > 0 ? "hausse" : t.pente < 0 ? "baisse" : "neutre",
    },
    {
      libelle: "Fiabilité (R²)",
      valeur: new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(t.r2),
      detail: confiance,
      classe: t.r2 >= 0.7 ? "hausse" : t.r2 >= 0.4 ? "neutre" : "baisse",
    },
    {
      libelle: `Projection sur ${t.projection_valeurs.length} ${t.unite}`,
      valeur: formatDT(dernier),
      detail: "si la tendance actuelle se poursuit",
      classe: "",
    },
  ];

  // Tout est injecté en innerHTML : on échappe libellé et détail pour ne
  // pas laisser une valeur servie par le serveur créer du HTML.
  grille.innerHTML = blocs.map((b) => `
    <div class="tendance-bloc ${b.classe}">
      <span class="tendance-valeur">${echapper(b.valeur)}</span>
      <span class="tendance-libelle">${echapper(b.libelle)}</span>
      <span class="tendance-detail">${echapper(b.detail)}</span>
    </div>`).join("");

  carte.hidden = false;
  if (legende) {
    legende.textContent = "⋯ projection";
    legende.hidden = false;
  }
}

function majClassement(c) {
  if (!c) return;

  // Tige et pastille portent la même valeur : la pastille est un nuage de
  // points posé sur { valeur, index de catégorie }.
  const enPuces = (valeurs) => valeurs.map((v, i) => ({ x: v, y: i }));

  charts.top.data.labels = c.top_labels;
  charts.top.data.datasets[0].data = c.top_valeurs;
  charts.top.data.datasets[1].data = enPuces(c.top_valeurs);
  charts.top.update();

  charts.flop.data.labels = c.flop_labels;
  charts.flop.data.datasets[0].data = c.flop_valeurs;
  charts.flop.data.datasets[1].data = enPuces(c.flop_valeurs);
  charts.flop.update();

  const message = {
    sans_produit: "Aucune colonne « produit » détectée.",
    un_seul_produit: "Un seul produit détecté : aucun classement possible.",
    scores_identiques: "Tous les produits ont le même score : classement sans objet.",
  }[c.raison] || "Pas assez de données pour un classement.";
  maj_etat_vide("chart-top", !c.top_labels.length, message);
  maj_etat_vide("chart-flop", !c.flop_labels.length, message);
}

function majCorrelations(c) {
  const table = document.getElementById("table-correlations");
  const badge = document.getElementById("correlations-total");
  if (!table) return;

  const paires = (c && c.paires) || [];
  if (badge) badge.textContent = paires.length;

  if (!paires.length) {
    table.innerHTML =
      "<tbody><tr><td>Moins de deux colonnes numériques dans ce fichier.</td></tr></tbody>";
    return;
  }

  const lignes = paires.map((p) => {
    const pct = Math.round(Math.abs(p.valeur) * 100);
    const fleche = p.sens === "direct" ? "↗" : "↘";
    return `<tr>
      <td>${echapper(p.a)} <span class="corr-lien">${fleche}</span> ${echapper(p.b)}</td>
      <td><span class="corr-jauge"><span class="corr-remplissage ${echapper(p.sens)}" style="width:${pct}%"></span></span></td>
      <td>${echapper(p.valeur)}</td>
      <td>${echapper(p.force)}</td>
    </tr>`;
  }).join("");

  table.innerHTML =
    "<thead><tr><th>Colonnes</th><th>Intensité</th><th>r</th><th>Lecture</th></tr></thead>" +
    `<tbody>${lignes}</tbody>`;
}

// Nuage de points de la paire la plus corrélée (dispersion).
function majNuage(n) {
  const carte = document.getElementById("carte-nuage");
  if (!carte || !charts.nuage) return;
  if (!n || !n.disponible) {
    carte.hidden = true;
    return;
  }
  carte.hidden = false;

  charts.nuage.data.datasets[0].data = n.x.map((v, i) => ({ x: v, y: n.y[i] }));
  charts.nuage.data.datasets[1].data =
    Array.isArray(n.droite) && n.droite.length === 2
      ? [{ x: n.x_min, y: n.droite[0] }, { x: n.x_max, y: n.droite[1] }]
      : [];

  // Titres d'axes : connus seulement après coup, le couple retenu dépendant
  // des filtres appliqués.
  const titre = (texte) => ({
    display: true, text: texte,
    color: couleur("--texte-doux", "#64748b"), font: { size: 11, weight: "600" },
  });
  if (charts.nuage.options.scales.x) charts.nuage.options.scales.x.title = titre(n.x_nom);
  if (charts.nuage.options.scales.y) charts.nuage.options.scales.y.title = titre(n.y_nom);

  charts.nuage.update();
  // La carte était peut-être cachée au montage : la toile doit reprendre
  // sa taille réelle dès qu'elle apparaît.
  if (typeof charts.nuage.resize === "function") charts.nuage.resize();

  const badge = document.getElementById("nuage-total");
  if (badge) badge.textContent = n.r == null ? "—" : `r = ${formatNombre(n.r)}`;
  const legende = document.getElementById("nuage-legende");
  if (legende) {
    const volume = n.total > n.echantillon
      ? ` (échantillon sur ${formatNombre(n.total)} lignes)` : "";
    legende.textContent =
      `${n.y_nom} selon ${n.x_nom} · ${formatNombre(n.echantillon)} points`
      + `${volume} · lien ${n.force}`;
  }
}

// ---------- Loader et états vides ----------

function montrer_loader(etat) {
  const loader = document.getElementById("loader");
  if (loader) loader.hidden = !etat;
}

function maj_etat_vide(id, est_vide, message) {
  const zone = document.getElementById(id);
  if (!zone) return;

  // L'id est posé tantôt sur le <canvas>, tantôt sur son conteneur : on
  // retrouve dans les deux cas où afficher le message et quoi masquer.
  const surCanvas = zone.tagName === "CANVAS";
  const canvas = surCanvas ? zone : zone.querySelector("canvas");
  const conteneur = surCanvas ? zone.parentElement : zone;
  if (!conteneur) return;

  let vide = conteneur.querySelector(".etat-vide");

  if (est_vide) {
    if (!vide) {
      vide = document.createElement("p");
      vide.className = "etat-vide";
      conteneur.appendChild(vide);
    }
    vide.textContent = message;
    vide.hidden = false;
    if (canvas) canvas.style.display = "none";
  } else if (vide) {
    vide.hidden = true;
    if (canvas) canvas.style.display = "";
  }
}

// Dernière réponse appliquée : permet de repeindre les graphiques après un
// changement de thème sans re-appeler l'API.
let derniereReponse = null;

async function charger() {
  montrer_loader(true);
  let reponse;
  try {
    reponse = await fetch(`${API_URL}?${parametresRequete()}&page=${pageApercu}`);
  } catch (erreur) {
    montrer_loader(false);
    document.getElementById("alerte-api").hidden = false;
    return;
  }
  montrer_loader(false);

  if (!reponse.ok) {
    document.getElementById("alerte-api").hidden = false;
    return;
  }
  appliquer(await reponse.json());
}

// Rendu pur : aucune requête. Séparé de charger() pour être testable tel quel.
function appliquer(d) {
  derniereReponse = d;

  majKpis(d.kpis);
  majResume(d.resume);

  majProjection(d.tendance, d.mois, d.ca_mensuel);
  majTendance(d.tendance);

  charts.categories.data.labels = d.categories.labels;
  charts.categories.data.datasets[0].data = d.categories.valeurs;
  charts.categories.update();

  charts.repartition.data.labels = d.categories.labels;
  charts.repartition.data.datasets[0].data = d.categories.valeurs;
  charts.repartition.update();

  majClassement(d.classement);
  majCorrelations(d.correlations);
  majNuage(d.nuage);

  // États vides : aucun chiffre d'affaires exploitable pour ces filtres.
  const sans_ca = d.kpis.ca_total == null;
  maj_etat_vide("chart-evolution", sans_ca, "Aucune donnée chiffrée pour ces filtres.");
  maj_etat_vide("chart-categories", !d.categories.labels.length,
    "Aucune catégorie détectée dans ce fichier.");
  maj_etat_vide("chart-repartition", !d.categories.labels.length,
    "Aucune catégorie détectée dans ce fichier.");

  majTableau("table-apercu", d.apercu);
  majPagination(d.apercu);
  majTableau("table-anomalies", d.anomalies);

  const badge = document.getElementById("anomalies-total");
  if (badge) badge.textContent = d.anomalies.total || 0;

  majExports();
}

// ---------- Comparaison de périodes ----------

function formaterVariation(v) {
  if (v == null) return "—";
  const signe = v > 0 ? "▲" : v < 0 ? "▼" : "＝";
  const classe = v > 0 ? "hausse" : v < 0 ? "baisse" : "neutre";
  const texte = v > 0 ? "+" : "";
  return `<span class="variation ${classe}">${signe} ${texte}${v}%</span>`;
}

function formaterPeriode(d) {
  if (!d.debut && !d.fin) return "—";
  const dbt = d.debut ? new Date(d.debut).toLocaleDateString("fr-FR") : "?";
  const f = d.fin ? new Date(d.fin).toLocaleDateString("fr-FR") : "?";
  return `${dbt} → ${f}`;
}

async function comparer() {
  const p = new URLSearchParams({ id: SID });
  const champCat = document.getElementById("filtre-categorie");
  if (champCat && champCat.value) p.set("categorie", champCat.value);
  // Un champ retiré du gabarit ne doit pas faire planter la comparaison.
  ["p1_debut", "p1_fin", "p2_debut", "p2_fin"].forEach((id) => {
    const champ = document.getElementById(id);
    if (champ && champ.value) p.set(id, champ.value);
  });

  const zone = document.getElementById("resultat-comparaison");
  const lignes = document.getElementById("comparaison-lignes");
  const avertissement = document.getElementById("comparaison-avertissement");
  if (!lignes || !zone) return;

  let reponse;
  try {
    reponse = await fetch(COMPARISON_URL + "?" + p.toString());
  } catch (erreur) {
    lignes.innerHTML = "<p class='etat-vide'>Réseau indisponible, réessaie plus tard.</p>";
    if (avertissement) avertissement.hidden = true;
    zone.hidden = false;
    return;
  }
  if (!reponse.ok) {
    lignes.innerHTML = "<p class='etat-vide'>Analyse introuvable.</p>";
    if (avertissement) avertissement.hidden = true;
    zone.hidden = false;
    return;
  }
  const d = await reponse.json();

  const lignesHtml = [
    ["Chiffre d'affaires", d.periode_1.ca, d.periode_2.ca, d.variations.ca, formatDT],
    ["Nombre de ventes", d.periode_1.ventes, d.periode_2.ventes, d.variations.ventes, formatNombre],
    ["Panier moyen", d.periode_1.panier, d.periode_2.panier, d.variations.panier, formatDT],
  ].map(([libelle, v1, v2, varia, formater]) => `
    <div class="comparaison-ligne">
      <span class="comparaison-libelle">${libelle}</span>
      <span class="comparaison-valeur">${formater(v1)}</span>
      <span class="comparaison-fleche">→</span>
      <span class="comparaison-valeur">${formater(v2)}</span>
      <span class="comparaison-var">${formaterVariation(varia)}</span>
    </div>`).join("");

  lignes.innerHTML = `
    <div class="comparaison-entetes">
      <span></span>
      <span>Période 1<br><small>${formaterPeriode(d.periode_1)}</small></span>
      <span></span>
      <span>Période 2<br><small>${formaterPeriode(d.periode_2)}</small></span>
      <span>Variation</span>
    </div>${lignesHtml}`;

  avertissement.hidden = d.comparable;
  zone.hidden = false;
}

// ---------- Événements ----------

document.addEventListener("DOMContentLoaded", () => {
  creerGraphiques();
  charger();

  ["filtre-categorie", "filtre-debut", "filtre-fin"].forEach((id) =>
    document.getElementById(id).addEventListener("change", () => {
      pageApercu = 1;
      charger();
    }));

  document.getElementById("btn-reset").addEventListener("click", () => {
    document.getElementById("filtre-categorie").value = "";
    document.getElementById("filtre-debut").value = "";
    document.getElementById("filtre-fin").value = "";
    pageApercu = 1;
    charger();
  });

  // Pagination de l'aperçu (délégation : les boutons sont recréés à chaque rendu).
  const zonePagination = document.getElementById("apercu-pagination");
  if (zonePagination) {
    zonePagination.addEventListener("click", (evenement) => {
      const bouton = evenement.target.closest("button[data-page]");
      if (!bouton || bouton.disabled) return;
      pageApercu = Number(bouton.dataset.page);
      charger();
    });
  }

  const btnComparer = document.getElementById("btn-comparer");
  if (btnComparer) btnComparer.addEventListener("click", comparer);

  // Bascule de palette des graphiques : Okabe-Ito (défaut) ou variante
  // « marque » teal — choix mémorisé, repeint sans nouvelle requête.
  const btnPalette = document.getElementById("btn-palette");
  if (btnPalette) {
    majLibellePalette();
    btnPalette.addEventListener("click", () => {
      try {
        window.localStorage.setItem(
          "datavision-palette", enModeMarque() ? "okabe" : "marque");
      } catch (e) { /* stockage indisponible : la palette reste par défaut */ }
      majLibellePalette();
      creerGraphiques();
      if (derniereReponse) appliquer(derniereReponse);
    });
  }

  // Export PNG des graphiques (délégation : un seul écouteur pour les cinq).
  document.addEventListener("click", (evenement) => {
    const bouton = evenement.target.closest("[data-png]");
    if (!bouton) return;
    exporterPNG(bouton.dataset.png);
  });

  // Vue détaillée : fermeture par le bouton, par le fond flouté ou par Échap.
  const btnFermer = document.getElementById("modale-fermer");
  if (btnFermer) btnFermer.addEventListener("click", fermerModale);

  const fondModale = document.getElementById("modale-graphique");
  if (fondModale) {
    fondModale.addEventListener("click", (evenement) => {
      if (evenement.target === fondModale) fermerModale();
    });
  }

  document.addEventListener("keydown", (evenement) => {
    if (evenement.key === "Escape") fermerModale();
  });

  // Le bouton de thème émet cet événement : on repeint les graphiques avec
  // les couleurs du nouveau thème (sans re-charger les données).
  document.addEventListener("datavision:theme", () => {
    if (!derniereReponse) return;
    creerGraphiques();
    appliquer(derniereReponse);
  });
});

// ---------- Exports ----------
// Surface testable : module.exports sous Node, window.DataVision dans le
// navigateur (pratique pour déboguer dans la console).
const api = {
  // Formats
  formatDT, formatNombre, echapper, formaterVariation, formaterPeriode,
  // Requêtes
  parametresRequete, majExports,
  // Graphiques
  creerGraphiques, couleur, aire,
  graphiqueDe, nomFichierPNG, exporterPNG,
  infosExport, hauteurEntetePNG, texteCoupe, dessinerEntetePNG,
  // Vue détaillée
  ouvrirModale, fermerModale, clicModale, optionsModale,
  titreGraphique, clonerDonnees, CANVAS_MODALE,
  charts, PALETTE, PALETTE_TOP, PALETTE_MARQUE, paletteActive,
  calculerAnnotations, annotationsCourbe,
  // Rendu
  majKpis, majResume, majTableau, majPagination, majTendance, majProjection,
  majClassement, majCorrelations, majNuage, montrer_loader, maj_etat_vide, appliquer,
  // Cycle de vie
  charger, comparer, initialiser: () => document.dispatchEvent(new Event("DOMContentLoaded")),
  // État interne
  pageApercu: () => pageApercu,
  derniereReponse: () => derniereReponse,
};

if (typeof window !== "undefined") window.DataVision = api;
if (typeof module !== "undefined" && module.exports) module.exports = api;
