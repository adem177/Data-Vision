"""
Génération de rapports PDF pour DataVision.

Utilise reportlab (pur Python) : pas de dépendance système, fonctionne
sur Windows, macOS et Linux sans installation supplémentaire.
"""

from io import BytesIO
from xml.sax.saxutils import escape as echapper_xml

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Bleu principal de la palette Okabe-Ito : les barres du PDF reprennent la
# couleur des graphiques du site (teintes conçues pour le daltonisme).
ACCENT = colors.HexColor("#0072B2")
TEXTE = colors.HexColor("#1e293b")
DOUX = colors.HexColor("#64748b")
FOND = colors.HexColor("#f4f5fb")
HAUSSE = colors.HexColor("#15803d")
BAISSE = colors.HexColor("#b91c1c")


def _francais(valeur, suffixe=""):
    """Formate un nombre à la française : 1 234,56"""
    if valeur is None:
        return "—"
    texte = f"{float(valeur):,.2f}".replace(",", " ").replace(".", ",")
    return f"{texte}{suffixe}"


def _styles():
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle(
            "TitreDV", parent=base["Title"], textColor=ACCENT, spaceAfter=4
        ),
        "sous_titre": ParagraphStyle(
            "SousTitreDV", parent=base["Normal"], textColor=DOUX,
            alignment=TA_CENTER, fontSize=9, spaceAfter=14,
        ),
        "note": ParagraphStyle(
            "NoteDV", parent=base["Normal"], textColor=TEXTE,
            fontSize=9.5, leading=13, spaceBefore=4, spaceAfter=2,
        ),
        "source": ParagraphStyle(
            "SourceDV", parent=base["Normal"], textColor=DOUX,
            fontSize=8.5, leading=11, spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "SectionDV", parent=base["Heading2"], textColor=TEXTE,
            fontSize=13, spaceBefore=14, spaceAfter=6,
        ),
        "cellule": ParagraphStyle(
            "CelluleDV", parent=base["Normal"], textColor=TEXTE, fontSize=9
        ),
    }


def _tableau_kpis(kpis, styles):
    """Grille des indicateurs principaux."""
    cartes = [
        ("Chiffre d'affaires", _francais(kpis.get("ca_total"), " DT")),
        ("Nombre de ventes", _francais(kpis.get("nb_ventes"))),
        ("Panier moyen", _francais(kpis.get("panier_moyen"), " DT")),
        ("Produits vendus", _francais(kpis.get("produits_vendus"))),
        ("Catégories", _francais(kpis.get("nb_categories"))),
        ("Valeurs manquantes", _francais(kpis.get("valeurs_manquantes"))),
    ]
    data = [[Paragraph(f"<b>{libelle}</b>", styles["cellule"]) for libelle, _ in cartes],
            [Paragraph(f"<b>{valeur}</b>", styles["cellule"]) for _, valeur in cartes]]
    table = Table(data, colWidths=[2.8 * cm] * 6)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FOND),
        ("TEXTCOLOR", (0, 0), (-1, 0), DOUX),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    return table


def _tableau_simple(entete, lignes, styles, largeurs=None):
    """Tableau générique à deux colonnes (libellé / valeur)."""
    data = [[Paragraph(f"<b>{entete[0]}</b>", styles["cellule"]),
             Paragraph(f"<b>{entete[1]}</b>", styles["cellule"])]]
    for libelle, valeur in lignes:
        data.append([
            Paragraph(str(libelle), styles["cellule"]),
            Paragraph(str(valeur), styles["cellule"]),
        ])
    table = Table(data, colWidths=largeurs or [11 * cm, 5 * cm])
    table.setStyle(TableStyle([
        ("TEXTCOLOR", (0, 0), (-1, 0), DOUX),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FOND]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    return table


# ----------------------------------------------------------------------
# Graphiques — reportlab.graphics (vectoriels, imprimables sans perte)
# ----------------------------------------------------------------------

LARGEUR_GRAPHE = 16 * cm   # lisible dans les marges d'une A4
HAUTEUR_GRAPHE = 7 * cm

# Au-delà, les barres deviennent trop fines ou les libellés se chevauchent :
# le tableau reste alors préférable au dessin.
LIMITE_BARRES = 36
LIMITE_CATEGORIES = 12


def _axes_lisibles(barres, taille: float = 7) -> None:
    """Axes sobres : police réduite, échelle des valeurs à partir de zéro."""
    for axe in (barres.categoryAxis, barres.valueAxis):
        axe.labels.fontName = "Helvetica"
        axe.labels.fontSize = taille
        axe.strokeColor = DOUX
    barres.valueAxis.valueMin = 0


def _libelles_compacts(noms: list, maximum: int = 14) -> list:
    """Éclaircit un axe : un libellé sur `pas` pour éviter le chevauchement."""
    pas = -(-len(noms) // maximum)  # division entière arrondie au-dessus
    if pas <= 1:
        return list(noms)
    return [nom if i % pas == 0 else "" for i, nom in enumerate(noms)]


def _libelle_mois(periode: str) -> str:
    """`2026-01` → `01/26` : libellé compact qui tient sur l'axe des mois."""
    if len(periode) >= 7 and periode[4] == "-":
        return f"{periode[5:7]}/{periode[2:4]}"
    return periode[:7]


def _graphe_evolution(evolution):
    """Histogramme du chiffre d'affaires mois par mois, ou None si illisible."""
    if evolution.empty or len(evolution) > LIMITE_BARRES:
        return None
    noms = _libelles_compacts(
        [_libelle_mois(str(p)) for p in evolution.index]
    )

    dessin = Drawing(LARGEUR_GRAPHE, HAUTEUR_GRAPHE)
    barres = VerticalBarChart()
    barres.x = 52
    barres.y = 20
    barres.width = LARGEUR_GRAPHE - 70
    barres.height = HAUTEUR_GRAPHE - 44
    barres.data = [[float(v) for v in evolution.values]]
    barres.categoryAxis.categoryNames = noms
    _axes_lisibles(barres)
    barres.bars[0].fillColor = ACCENT
    barres.bars[0].strokeColor = ACCENT
    dessin.add(barres)
    return dessin


def _graphe_categories(categories):
    """Barres horizontales : chiffre d'affaires par catégorie (ordre décroissant)."""
    if categories.empty or len(categories) > LIMITE_CATEGORIES:
        return None

    dessin = Drawing(LARGEUR_GRAPHE, HAUTEUR_GRAPHE)
    barres = HorizontalBarChart()
    barres.x = 100
    barres.y = 24
    barres.width = LARGEUR_GRAPHE - 112
    barres.height = HAUTEUR_GRAPHE - 48
    # L'axe vertical part du bas : on inverse pour garder l'ordre décroissant.
    barres.data = [[float(v) for v in categories.values][::-1]]
    barres.categoryAxis.categoryNames = [
        str(c)[:22] for c in categories.index
    ][::-1]
    _axes_lisibles(barres, taille=7.5)
    barres.bars[0].fillColor = ACCENT
    barres.bars[0].strokeColor = ACCENT
    dessin.add(barres)
    return dessin


def generer_rapport(
    analyseur, df, nom_projet, nom_fichier, note=None, source=None
) -> BytesIO:
    """Construit le PDF du rapport et renvoie son contenu en mémoire.

    `note` et `source` portent la note de l'analyste et la provenance des
    données : posés sous le titre, ils donnent au document la rigueur
    d'un article — le chiffre sans son contexte reste une devinette.
    """
    styles = _styles()
    tampon = BytesIO()
    document = SimpleDocTemplate(
        tampon, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Rapport — {nom_projet}", author="DataVision",
    )

    kpis = analyseur.kpis(df)
    elements = [
        Paragraph("Rapport d'analyse", styles["titre"]),
        Paragraph(f"{nom_projet} · fichier {nom_fichier}", styles["sous_titre"]),
    ]
    if note:
        # Le texte vient de l'utilisateur : échappé (le PDF accepte des
        # balises) et retours à la ligne conservés.
        elements.append(Paragraph(
            f"<b>Note de l'analyste.</b> {echapper_xml(note).replace(chr(10), '<br/>')}",
            styles["note"],
        ))
    if source:
        elements.append(Paragraph(f"Source : {echapper_xml(source)}", styles["source"]))
    elements.append(_tableau_kpis(kpis, styles))

    categories = analyseur.par_categorie(df)
    if not categories.empty:
        elements.append(Paragraph("Chiffre d'affaires par catégorie", styles["section"]))
        elements.append(_tableau_simple(
            ("Catégorie", "Chiffre d'affaires"),
            [(c, _francais(v, " DT")) for c, v in categories.items()],
            styles,
        ))
        graphe = _graphe_categories(categories)
        if graphe is not None:
            elements.append(Spacer(1, 8))
            elements.append(graphe)

    top = analyseur.top_produits(5, df)
    classement = analyseur.classement_produits(5, df)
    if classement.get("metrique"):
        unite = " DT" if classement["metrique"] == "CA" else ""
        elements.append(Paragraph("Top 5 des produits", styles["section"]))
        elements.append(_tableau_simple(
            ("Produit", classement["metrique"]),
            [(p, _francais(v, unite)) for p, v in
             zip(classement["top_labels"], classement["top_valeurs"])],
            styles,
        ))
        elements.append(Paragraph("Flop 5 des produits", styles["section"]))
        elements.append(_tableau_simple(
            ("Produit", classement["metrique"]),
            [(p, _francais(v, unite)) for p, v in
             zip(classement["flop_labels"], classement["flop_valeurs"])],
            styles,
        ))
    elif not top.empty:
        elements.append(Paragraph("Top 5 des produits", styles["section"]))
        elements.append(_tableau_simple(
            ("Produit", "Chiffre d'affaires"),
            [(p, _francais(v, " DT")) for p, v in top.items()],
            styles,
        ))

    evolution = analyseur.evolution_mensuelle(df)
    if not evolution.empty:
        elements.append(Paragraph("Évolution mensuelle", styles["section"]))
        elements.append(_tableau_simple(
            ("Période", "Chiffre d'affaires"),
            [(str(p), _francais(v, " DT")) for p, v in evolution.items()],
            styles,
        ))
        graphe = _graphe_evolution(evolution)
        if graphe is not None:
            elements.append(Spacer(1, 8))
            elements.append(graphe)

    # --- Phase E : projection par régression linéaire ---
    tendance = analyseur.prevoir_tendance(df)
    if tendance.get("disponible"):
        sens = {"hausse": "en hausse", "baisse": "en baisse", "stable": "stable"}[tendance["sens"]]
        fiabilite = (
            "solide" if tendance["r2"] >= 0.7
            else "indicative" if tendance["r2"] >= 0.4
            else "peu fiable"
        )
        elements.append(Paragraph("Tendance et prévision", styles["section"]))
        elements.append(Paragraph(
            f"Tendance {sens} de <b>{_francais(tendance['pente'])} DT "
            f"par {tendance['unite']}</b> (R² = {tendance['r2']:.3f} — "
            f"projection {fiabilite}).",
            styles["cellule"],
        ))
        elements.append(Spacer(1, 6))
        elements.append(_tableau_simple(
            ("Projection", "Chiffre d'affaires attendu"),
            [(lab, _francais(val, " DT")) for lab, val in
             zip(tendance["projection_labels"], tendance["projection_valeurs"])],
            styles,
        ))

    # --- Phase E : corrélation de Pearson entre colonnes numériques ---
    correlations = analyseur.correlations(df)
    if correlations["paires"]:
        elements.append(Paragraph("Corrélations entre colonnes numériques", styles["section"]))
        elements.append(_tableau_simple(
            ("Colonnes", "Coefficient de Pearson"),
            [
                (f"{p['a']} et {p['b']}",
                 f"{p['valeur']} — {p['force']}, lien {p['sens']}")
                for p in correlations["paires"]
            ],
            styles,
        ))

    anomalies = analyseur.detecter_anomalies(df)
    if anomalies.get("total"):
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(
            f"<b>⚠ {anomalies['total']}</b> valeur(s) atypique(s) détectée(s) "
            "(règle IQR). À vérifier manuellement.",
            styles["cellule"],
        ))

    elements.append(Spacer(1, 14))
    elements.append(Paragraph(
        f"Généré par DataVision le {analyseur.date_rapport()} · "
        f"{kpis.get('nb_ventes')} lignes analysées · "
        f"{kpis.get('doublons_supprimes', 0)} doublon(s) supprimé(s)",
        styles["sous_titre"],
    ))

    document.build(elements)
    tampon.seek(0)
    return tampon
