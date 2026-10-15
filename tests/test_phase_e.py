"""Tests de la Phase E : prévision de tendance, corrélations, Top/Flop."""

import numpy as np
import pandas as pd
import pytest

from analyzer import DataAnalyzer


# ----------------------------------------------------------------------
# Jeux de données
# ----------------------------------------------------------------------

@pytest.fixture
def serie_lineaire():
    """CA strictement croissant : 1 000, 2 000 … 6 000 DT sur 6 mois."""
    return pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=6, freq="MS"),
        "Quantité": [10, 20, 30, 40, 50, 60],
        "Prix": [100] * 6,
    })


@pytest.fixture
def serie_decroissante():
    return pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=6, freq="MS"),
        "Quantité": [60, 50, 40, 30, 20, 10],
        "Prix": [100] * 6,
    })


@pytest.fixture
def produits():
    """4 produits au CA volontairement étalé."""
    return pd.DataFrame({
        "Produit": ["A", "B", "C", "D"],
        "Quantité": [1, 2, 3, 4],
        "Prix": [10, 10, 10, 10],
    })


# ----------------------------------------------------------------------
# Prévision de tendance
# ----------------------------------------------------------------------

def test_tendance_lineaire_parfaite(serie_lineaire):
    """Sur une droite parfaite, la pente vaut exactement la hausse mensuelle."""
    t = DataAnalyzer(df=serie_lineaire).prevoir_tendance()

    assert t["disponible"] is True
    assert t["pente"] == pytest.approx(1000.0, abs=0.01)
    assert t["r2"] == pytest.approx(1.0, abs=1e-3)
    assert t["sens"] == "hausse"
    assert t["unite"] == "mois"


def test_tendance_projection_sur_les_mois_suivants(serie_lineaire):
    """La projection prolonge la série de 3 mois calendaires."""
    t = DataAnalyzer(df=serie_lineaire).prevoir_tendance(horizon=3)

    assert t["projection_labels"] == ["2026-07", "2026-08", "2026-09"]
    assert t["projection_valeurs"] == pytest.approx([7000.0, 8000.0, 9000.0], abs=0.01)


def test_tendance_decroissante_signale_une_baisse(serie_decroissante):
    t = DataAnalyzer(df=serie_decroissante).prevoir_tendance()

    assert t["sens"] == "baisse"
    assert t["pente"] < 0


def test_tendance_horizon_configurable(serie_lineaire):
    t = DataAnalyzer(df=serie_lineaire).prevoir_tendance(horizon=5)
    assert len(t["projection_valeurs"]) == 5


def test_tendance_indisponible_si_serie_trop_courte():
    """Deux points ne suffisent pas à ajuster une droite de façon honnête."""
    df = pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=2, freq="MS"),
        "Quantité": [10, 20],
        "Prix": [100] * 2,
    })
    t = DataAnalyzer(df=df).prevoir_tendance()

    assert t["disponible"] is False
    assert t["projection_valeurs"] == []


def test_tendance_indisponible_si_ca_constant(serie_lineaire):
    """Une série plate n'a ni pente ni projection exploitables."""
    df = serie_lineaire.copy()
    df["Quantité"] = 10
    t = DataAnalyzer(df=df).prevoir_tendance()

    assert t["disponible"] is False


def test_tendance_sans_colonne_date_utilise_des_tranches(produits):
    """Sans colonne date, la projection se fait sur des tranches et non des mois."""
    t = DataAnalyzer(df=produits).prevoir_tendance()

    assert t["disponible"] is True
    assert t["unite"] == "tranches"
    assert t["projection_labels"] == ["Part 5", "Part 6", "Part 7"]


def test_r2_est_borne_entre_0_et_1(serie_lineaire):
    rng = np.random.default_rng(0)
    df = serie_lineaire.copy()
    df["Quantité"] = df["Quantité"] + rng.integers(-30, 30, len(df))
    t = DataAnalyzer(df=df).prevoir_tendance()

    assert 0.0 <= t["r2"] <= 1.0


# ----------------------------------------------------------------------
# Corrélations
# ----------------------------------------------------------------------

def test_correlation_parfaite_directe():
    df = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": [2, 4, 6, 8, 10]})
    c = DataAnalyzer(df=df).correlations()

    assert c["paires"], "une paire est attendue"
    paire = c["paires"][0]
    assert {paire["a"], paire["b"]} == {"A", "B"}
    assert paire["valeur"] == pytest.approx(1.0, abs=1e-6)
    assert paire["sens"] == "direct"
    assert paire["force"] == "forte"


def test_correlation_inverse():
    df = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": [5, 4, 3, 2, 1]})
    c = DataAnalyzer(df=df).correlations()

    assert c["paires"][0]["valeur"] == pytest.approx(-1.0, abs=1e-6)
    assert c["paires"][0]["sens"] == "inverse"


def test_correlations_tri_par_intensite():
    df = pd.DataFrame({
        "faible": [1, 2, 3, 4, 100],
        "moyen": [1, 3, 2, 5, 4],
        "fort": [1, 2, 3, 4, 5],
    })
    c = DataAnalyzer(df=df).correlations()

    valeurs = [abs(p["valeur"]) for p in c["paires"]]
    assert valeurs == sorted(valeurs, reverse=True)


def test_correlations_vides_sans_donnees_numeriques():
    df = pd.DataFrame({"Texte": ["a", "b", "c"]})
    c = DataAnalyzer(df=df).correlations()

    assert c["paires"] == []
    assert c["colonnes"] == []


def test_forces_correlation_qualifiees():
    for coefficient, qualificatif in [
        (0.9, "forte"), (0.5, "modérée"), (0.3, "faible"), (0.05, "négligeable"),
    ]:
        assert DataAnalyzer._forcer_correlation(coefficient) == qualificatif


# ----------------------------------------------------------------------
# Top / Flop
# ----------------------------------------------------------------------

def test_classement_top_et_flop(produits):
    c = DataAnalyzer(df=produits).classement_produits(n=2)

    assert c["metrique"] == "CA"
    assert c["top_labels"] == ["D", "C"]     # CA 40 puis 30
    assert c["flop_labels"] == ["A", "B"]     # CA 10 puis 20
    assert c["top_valeurs"] == pytest.approx([40.0, 30.0])
    assert c["flop_valeurs"] == pytest.approx([10.0, 20.0])


def test_flop_est_l_inverse_du_top(produits):
    c = DataAnalyzer(df=produits).classement_produits(n=4)

    assert c["top_labels"] == list(reversed(c["flop_labels"]))


def test_classement_avec_un_seul_produit():
    df = pd.DataFrame({"Produit": ["A", "A"], "Quantité": [1, 2], "Prix": [10, 10]})
    c = DataAnalyzer(df=df).classement_produits()

    assert c["top_labels"] == []
    assert c["flop_labels"] == []
    assert c["raison"] == "un_seul_produit"


def test_classement_sans_colonne_produit():
    df = pd.DataFrame({"Prix": [10, 20, 30]})
    c = DataAnalyzer(df=df).classement_produits()

    assert c["metrique"] is None
    assert c["top_labels"] == []
    assert c["raison"] == "sans_produit"


def test_classement_refuse_un_score_uniforme():
    """Tous les produits au même CA : un classement serait purement arbitraire."""
    df = pd.DataFrame({
        "Produit": ["A", "B", "C"],
        "Quantité": [1, 1, 1],
        "Prix": [100, 100, 100],
    })
    c = DataAnalyzer(df=df).classement_produits()

    assert c["top_labels"] == []
    assert c["metrique"] == "CA"
    assert c["raison"] == "scores_identiques"


def test_classement_valide_quand_le_score_varie(produits):
    c = DataAnalyzer(df=produits).classement_produits()
    assert c["raison"] is None


def test_classement_repli_sur_quantite_sans_prix():
    """Quand aucun CA n'est calculable, on classe sur la quantité vendue."""
    analyseur = DataAnalyzer(df=pd.DataFrame({"Produit": ["A", "B"], "Quantité": [5, 50]}))
    analyseur.colonnes["prix"] = None
    analyseur.df["CA"] = np.nan  # pas de prix => pas de chiffre d'affaires

    c = analyseur.classement_produits(n=1)

    assert c["metrique"] == "Quantité"
    assert c["top_labels"] == ["B"]
    assert c["flop_labels"] == ["A"]


# ----------------------------------------------------------------------
# Intégration : API et rapport PDF
# ----------------------------------------------------------------------

@pytest.fixture
def client_connecte():
    from django.contrib.auth.models import User
    from django.test import Client

    User.objects.create_user("karim", password="motdepasse123")
    client = Client()
    client.login(username="karim", password="motdepasse123")
    return client


@pytest.fixture
def donnees_csv():
    from django.core.files.uploadedfile import SimpleUploadedFile

    lignes = ["Date,Produit,Catégorie,Quantité,Prix"]
    # Deux produits répartis sur 4 mois : indispensable pour un classement Top/Flop.
    for date, produit, quantite in [
        ("01/01/2026", "PC portable", 10),
        ("01/02/2026", "Souris", 20),
        ("01/03/2026", "PC portable", 30),
        ("01/04/2026", "Souris", 40),
    ]:
        lignes.append(f"{date},{produit},Informatique,{quantite},100")
    return SimpleUploadedFile(
        "ventes.csv", "\n".join(lignes).encode("utf-8"), "text/csv"
    )


def test_api_renvoie_les_analyses_phase_e(client_connecte, donnees_csv):
    client_connecte.post("/upload", {"fichier": donnees_csv})
    from core.models import Projet

    projet = Projet.objects.get()
    donnees = client_connecte.get(f"/api/donnees?id={projet.pk}").json()

    assert donnees["tendance"]["disponible"] is True
    assert donnees["tendance"]["sens"] == "hausse"
    assert donnees["classement"]["metrique"] == "CA"
    assert donnees["correlations"]["paires"]


def test_dashboard_affiche_les_nouvelles_sections(client_connecte, donnees_csv):
    client_connecte.post("/upload", {"fichier": donnees_csv})
    from core.models import Projet

    projet = Projet.objects.get()
    html = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    assert "carte-tendance" in html
    assert "chart-flop" in html
    assert "table-correlations" in html


def test_rapport_pdf_integre_phase_e(client_connecte, donnees_csv):
    """Le PDF se génère toujours, avec la projection et les corrélations."""
    client_connecte.post("/upload", {"fichier": donnees_csv})
    from core.models import Projet

    projet = Projet.objects.get()
    reponse = client_connecte.get(f"/projet/{projet.pk}/rapport")

    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"
    assert reponse.content[:5] == b"%PDF-"
    # Le document doit contenir au moins une page (le %PDF + %%EOF).
    assert b"%%EOF" in reponse.content[-1024:]
