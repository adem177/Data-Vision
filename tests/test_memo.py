"""Tests de la mémoïsation des agrégations.

`/api/donnees` rappelle les mêmes calculs à chaque clic de pagination : sur un
fichier de 500 000 lignes, chaque recalcul inutile se paie en temps de réponse.
On vérifie ici qu'un calcul ne se fait qu'une fois, qu'un changement de filtre
le refait, et qu'un changement de mapping invalide bien le résultat.
"""

import pandas as pd
import pytest

from analyzer import DataAnalyzer


@pytest.fixture
def ventes():
    return pd.DataFrame({
        "Date": ["01/01/2026", "01/02/2026", "01/03/2026"],
        "Produit": ["A", "B", "C"],
        "Catégorie": ["Info", "Info", "Bureau"],
        "Quantité": [1, 1, 1],
        "Remise": [10, 20, 30],
        "Prix": [100, 200, 300],
    })


def _espion(monkeypatch, analyseur, methode_privee):
    """Compte les appels au calcul, en laissant passer le résultat."""
    compteur = {"appels": 0}
    original = getattr(analyseur, methode_privee)

    def appele(*args, **kwargs):
        compteur["appels"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(analyseur, methode_privee, appele)
    return compteur


# ----------------------------------------------------------------------
# Une fois par filtre
# ----------------------------------------------------------------------

def test_une_agregation_est_calculee_une_seule_fois(monkeypatch, ventes):
    a = DataAnalyzer(df=ventes)
    compteur = _espion(monkeypatch, a, "_par_categorie")

    premier = a.par_categorie()
    second = a.par_categorie()

    assert compteur["appels"] == 1
    assert premier is second  # la même valeur, pas une copie recalciee


def test_les_agregations_du_dashboard_sont_memoisees(monkeypatch, ventes):
    """Les sept calculs que `/api/donnees` réclame à chaque appel."""
    a = DataAnalyzer(df=ventes)
    cas = [
        ("_evolution_mensuelle", a.evolution_mensuelle),
        ("_par_categorie", a.par_categorie),
        ("_classement_produits", a.classement_produits),
        ("_correlations", a.correlations),
        ("_nuage_points", a.nuage_points),
        ("_detecter_anomalies", a.detecter_anomalies),
        ("_kpis", a.kpis),
    ]
    for privee, appel in cas:
        compteur = _espion(monkeypatch, a, privee)
        appel()
        appel()
        assert compteur["appels"] == 1, privee


def test_un_filtre_different_recalcule(monkeypatch, ventes):
    a = DataAnalyzer(df=ventes)
    compteur = _espion(monkeypatch, a, "_par_categorie")

    a.par_categorie()
    a.par_categorie(a.filtrer(categorie="Info"))
    a.par_categorie()

    assert compteur["appels"] == 2  # vide, « Info », puis re-« Info » en mémoire


def test_le_filtre_identique_renvoie_le_meme_dataframe(ventes):
    """Sans ce partage, l'identité du dataframe changerait à chaque appel."""
    a = DataAnalyzer(df=ventes)
    assert a.filtrer(categorie="Info") is a.filtrer(categorie="Info")
    assert a.filtrer() is a.df


# ----------------------------------------------------------------------
# Invalidation
# ----------------------------------------------------------------------

def test_changement_de_mapping_invalide_la_memo(ventes):
    a = DataAnalyzer(df=ventes)
    assert a.kpis()["ca_total"] == 600  # 1×100 + 1×200 + 1×300

    # La colonne CA change de sens : les agrégations doivent suivre.
    a.appliquer_mapping({"quantite": "Remise"})

    assert a.kpis()["ca_total"] == 10 * 100 + 20 * 200 + 30 * 300


def test_le_debordement_de_la_memo_ne_plante_pas(monkeypatch, ventes):
    """Au-delà de TAILLE_MEMO, on vide et on recommence."""
    a = DataAnalyzer(df=ventes)
    monkeypatch.setattr(a, "TAILLE_MEMO", 2)

    for categorie in ["Info", "Bureau", "Info", "Autre"]:
        a.par_categorie(a.filtrer(categorie=categorie))

    # Les valeurs restent justes après le vidage.
    assert float(a.par_categorie()["Info"]) == 300


def test_un_parametre_non_hachable_ne_plante_pas(ventes):
    """?debut=a&debut=b remonte une liste : filtrer doit rester tolérant."""
    a = DataAnalyzer(df=ventes)
    assert len(a.filtrer(debut=["2026-01-01", "2026-02-01"])) == len(a.df)
