"""Tests unitaires du moteur d'analyse — indépendants de Django."""

import pandas as pd
import pytest

from analyzer import DataAnalyzer


@pytest.fixture
def ventes():
    return pd.DataFrame({
        "Date": ["01/09/2026", "02/09/2026", "02/09/2026", "03/09/2026"],
        "Produit": ["PC portable", "Souris", "Souris", "Écran"],
        "Catégorie": ["Informatique", "Accessoires", "Accessoires", None],
        "Quantité": [2, 10, 10, 4],
        "Prix": [1800, 25, 25, 220],
    })


def test_nettoyage_supprime_doublons(ventes):
    analyseur = DataAnalyzer(df=ventes)
    assert analyseur.nb_doublons == 1
    assert len(analyseur.df) == 3


def test_colonnes_detectees(ventes):
    analyseur = DataAnalyzer(df=ventes)
    assert analyseur.colonnes["date"] == "Date"
    assert analyseur.colonnes["produit"] == "Produit"
    assert analyseur.colonnes["categorie"] == "Catégorie"
    assert analyseur.colonnes["quantite"] == "Quantité"
    assert analyseur.colonnes["prix"] == "Prix"


def test_kpis(ventes):
    analyseur = DataAnalyzer(df=ventes)
    k = analyseur.kpis()
    # 2×1800 + 10×25 + 4×220 = 4730
    assert k["ca_total"] == 4730
    assert k["nb_ventes"] == 3
    assert k["produits_vendus"] == 16
    assert k["nb_produits_uniques"] == 3


def test_evolution_mensuelle(ventes):
    analyseur = DataAnalyzer(df=ventes)
    evolution = analyseur.evolution_mensuelle()
    assert list(evolution.index) == ["2026-09"]
    assert float(evolution.iloc[0]) == 4730


def test_par_categorie(ventes):
    analyseur = DataAnalyzer(df=ventes)
    categories = analyseur.par_categorie()
    assert categories.index[0] == "Informatique"
    assert float(categories["Informatique"]) == 3600


def test_top_produits(ventes):
    analyseur = DataAnalyzer(df=ventes)
    top = analyseur.top_produits(2)
    assert list(top.index) == ["PC portable", "Écran"]


def test_filtre_categorie(ventes):
    analyseur = DataAnalyzer(df=ventes)
    filtre = analyseur.filtrer(categorie="Accessoires")
    assert len(filtre) == 1


def test_filtre_categorie_nan_ne_ravisse_pas_les_vides(ventes):
    """`astype(str)` fait de chaque NaN la chaîne « nan ».

    Une catégorie fantôme « nan » (saisie dans l'URL) ne doit donc pas
    renvoyer toutes les lignes à catégorie manquante.
    """
    analyseur = DataAnalyzer(df=ventes)
    assert analyseur.df["Catégorie"].isna().sum() == 1
    assert len(analyseur.filtrer(categorie="nan")) == 0


def test_filtre_categorie_numerique_renvoie_les_bonnes_lignes():
    """Une catégorie numérique offre « 2 » dans le menu : il faut la retrouver."""
    df = pd.DataFrame({
        "Date": ["01/09/2026", "02/09/2026", "03/09/2026"],
        "Produit": ["A", "B", "C"],
        "Type": [2, 3, 2],
        "Quantité": [1, 1, 1],
        "Prix": [10, 20, 30],
    })
    analyseur = DataAnalyzer(df=df)
    assert analyseur.colonnes["categorie"] == "Type"
    assert "2" in analyseur.options_filtres()["categories"]
    assert len(analyseur.filtrer(categorie="2")) == 2


def test_filtre_date(ventes):
    analyseur = DataAnalyzer(df=ventes)
    filtre = analyseur.filtrer(debut="2026-09-03")
    assert len(filtre) == 1


def test_filtre_date_invalide_est_ignore(ventes):
    """Une saisie illisible arrive de l'URL : la borne saute, rien ne plante."""
    analyseur = DataAnalyzer(df=ventes)
    filtre = analyseur.filtrer(debut="pasune-date", fin="31/13/2026")
    assert len(filtre) == len(analyseur.df)


def test_filtre_date_non_scalaire_est_ignore(ventes):
    """Un paramètre répété (?debut=a&debut=b) remonte une liste : ignoré."""
    analyseur = DataAnalyzer(df=ventes)
    filtre = analyseur.filtrer(debut=["2026-09-01", "2026-09-02"])
    assert len(filtre) == len(analyseur.df)


def test_filtre_date_na_est_ignore(ventes):
    analyseur = DataAnalyzer(df=ventes)
    filtre = analyseur.filtrer(debut=float("nan"))
    assert len(filtre) == len(analyseur.df)


def test_filtre_date_valide_toujours_applique(ventes):
    """La tolérance n'affaiblit pas le filtrage normal."""
    analyseur = DataAnalyzer(df=ventes)
    assert len(analyseur.filtrer(debut="2026-09-03", fin="2026-09-03")) == 1


def test_export_csv(ventes):
    analyseur = DataAnalyzer(df=ventes)
    contenu = analyseur.export(fmt="csv").getvalue()
    assert b"CA" in contenu


def test_export_excel(ventes):
    analyseur = DataAnalyzer(df=ventes)
    contenu = analyseur.export(fmt="excel").getvalue()
    assert contenu[:2] == b"PK"  # signature ZIP d'un fichier xlsx


def test_anomalies(ventes):
    analyseur = DataAnalyzer(df=ventes)
    anomalies = analyseur.detecter_anomalies()
    assert anomalies["total"] == 0  # moins de 4 lignes : pas d'analyse IQR


# ----------------------------------------------------------------------
# Synthèse en langage naturel
# ----------------------------------------------------------------------


def test_resume_mentionne_les_kpis(ventes):
    analyseur = DataAnalyzer(df=ventes)
    texte = analyseur.resume()
    assert "4 730,00 DT" in texte          # chiffre d'affaires formaté en français
    assert "3 ventes" in texte
    assert "PC portable" in texte          # produit star
    assert "Accessoires" in texte          # catégorie dominante


def test_resume_tient_compte_du_filtre(ventes):
    analyseur = DataAnalyzer(df=ventes)
    texte = analyseur.resume(analyseur.filtrer(categorie="Accessoires"))
    assert "250,00 DT" in texte            # 10 × 25 de la seule ligne filtrée
    assert "une seule catégorie" in texte


def test_resume_sur_fichier_vide(ventes):
    analyseur = DataAnalyzer(df=ventes)
    texte = analyseur.resume(analyseur.df.head(0))
    assert texte == "Aucune ligne ne correspond à ces filtres."


def test_resume_sans_date_ni_produit():
    """Un fichier minimal reste honnête : pas de « mois » inventé sans date.

    Sans colonne de date, le moteur découpe en tranches et projette sur
    des tranches — le résumé doit suivre ce vocabulaire.
    """
    analyseur = DataAnalyzer(df=pd.DataFrame({"Montant": [100, 300, 200]}))
    texte = analyseur.resume()
    assert "600,00 DT" in texte
    assert "produit star" not in texte      # aucune colonne produit
    assert "mois" not in texte              # tranches, jamais « mois »
    if "tendance" in texte:
        assert "tranches" in texte


def test_resume_ne_mentionne_que_ce_qui_existe():
    """Pas de catégorie dans le fichier => pas de phrase sur la catégorie."""
    analyseur = DataAnalyzer(df=pd.DataFrame({
        "Date": ["2026-01-05", "2026-02-05", "2026-03-05"],
        "Montant": [100, 300, 200],
    }))
    texte = analyseur.resume()
    assert "catégorie" not in texte.lower()
    assert "La période couverte" in texte
