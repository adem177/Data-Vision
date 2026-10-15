"""Dispersion (nuage de points) : la paire la plus corrélée du fichier.

Le graphique porte trois promesses : le couple retenu est le plus parlant
**et jamais « CA × facteur »** (une tautologie, puisque CA = prix ×
quantité), l'échantillon couvre toute la plage du fichier, et la droite de
régression suit exactement les points affichés.
"""

import numpy as np
import pandas as pd
import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from analyzer import DataAnalyzer
from core.models import Projet

MOT_DE_PASSE = "MotDePasse-2026"
# 30 lignes : quantité qui baisse quand le prix monte.
CONTENU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    + "\n".join(
        f"0{(i % 9) + 1}/01/2026,Vis,Info,{(i % 5) + 1},{(i % 7) * 10 + 20}"
        for i in range(30)
    )
    + "\n"
)


@pytest.fixture
def ventes():
    """300 lignes où prix et quantité sont réellement liés (r négatif)."""
    rng = np.random.default_rng(7)
    prix = rng.uniform(10, 500, 300).round(2)
    quantite = (500 - prix * 0.8 + rng.normal(0, 5, 300)).round(0)
    return pd.DataFrame({
        "Prix": prix,
        "Quantité": quantite,
        "Remise": rng.uniform(0, 30, 300).round(2),
    })


# ----------------------------------------------------------------------
# Choix du couple
# ----------------------------------------------------------------------


def test_le_couple_retenu_est_le_plus_fort_et_exclut_le_ca(ventes):
    analyseur = DataAnalyzer(df=ventes)
    nuage = analyseur.nuage_points()

    assert nuage["disponible"] is True
    # Le CA existe dans ce dataframe (prix × quantité) : il ne doit jamais
    # figurer dans le couple — corréler un total à son facteur ne dit rien.
    assert "CA" not in (nuage["x_nom"], nuage["y_nom"])
    assert abs(nuage["r"]) >= 0.7
    assert nuage["force"] == "forte"


def test_le_ca_ne_suffit_pas_a_faire_un_couple():
    """Prix et quantité seuls : le CA calculé ne devient pas un candidat."""
    df = pd.DataFrame({"Quantité": [1, 2, 3, 4, 5], "Prix": [10.0, 20, 30, 40, 50]})
    nuage = DataAnalyzer(df=df).nuage_points()

    assert nuage["disponible"] is True
    assert "CA" not in (nuage["x_nom"], nuage["y_nom"])


def test_un_seul_couple_exploitable_ne_plante_pas():
    """Une seule colonne numérique : rien à disperser, pas d'erreur."""
    df = pd.DataFrame({"Prix": [1.0, 2.0, 3.0, 4.0, 5.0], "Ville": list("abcde")})
    nuage = DataAnalyzer(df=df).nuage_points()

    assert nuage["disponible"] is False
    assert nuage["x"] == []
    assert nuage["droite"] is None


def test_sans_colonne_numerique():
    nuage = DataAnalyzer(df=pd.DataFrame({"Ville": ["Tunis", "Sfax"]})).nuage_points()
    assert nuage["disponible"] is False


# ----------------------------------------------------------------------
# Échantillonnage et régression
# ----------------------------------------------------------------------


def test_l_echantillon_ne_depasse_jamais_la_limite(ventes):
    nuage = DataAnalyzer(df=ventes).nuage_points(max_points=50)

    assert nuage["echantillon"] == 50
    assert nuage["total"] == 300
    assert len(nuage["x"]) == len(nuage["y"]) == 50


def test_le_prelevement_couvre_toute_la_plage(ventes):
    """Un échantillon tronqué en tête ne montrerait que le début du fichier."""
    nuage = DataAnalyzer(df=ventes).nuage_points(max_points=50)

    assert min(nuage["x"]) == nuage["x_min"]
    assert max(nuage["x"]) == nuage["x_max"]


def test_sous_la_limite_tout_le_fichier_est_affiche(ventes):
    nuage = DataAnalyzer(df=ventes).nuage_points()
    assert nuage["echantillon"] == nuage["total"] == 300


def test_la_droite_est_celle_des_points_affiches(ventes):
    nuage = DataAnalyzer(df=ventes).nuage_points()

    assert nuage["pente"] is not None
    assert len(nuage["droite"]) == 2
    # Prix qui monte, quantité qui baisse : pente négative.
    assert nuage["pente"] < 0
    # La pente annoncée est bien celle des points renvoyés (moindres carrés).
    pente_attendue = np.polyfit(nuage["x"], nuage["y"], 1)[0]
    assert nuage["pente"] == pytest.approx(pente_attendue, abs=0.01)


def test_colonne_constante_ne_fabrique_pas_de_correlation():
    """Pearson sur une colonne immobile est NaN : aucun couple en sort."""
    df = pd.DataFrame({
        "Quantité": [1, 2, 3, 4, 5, 6],
        "Prix": [100.0, 100, 100, 100, 100, 100],
    })
    nuage = DataAnalyzer(df=df).nuage_points()

    assert nuage["disponible"] is False
    assert nuage["droite"] is None


def test_un_echantillon_sans_variance_na_pas_de_droite():
    """La seule variation de x tombe hors de l'échantillon prélevé :
    la dispersion s'affiche quand même, mais il n'y a pas de droite à
    tracer sur un x parfaitement plat."""
    df = pd.DataFrame({
        "Référence": [5.0] * 10 + [100.0],
        "Quantité": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 50],
    })
    nuage = DataAnalyzer(df=df).nuage_points(max_points=10)

    assert nuage["disponible"] is True
    assert nuage["x_nom"] == "Référence"
    assert nuage["echantillon"] == 10
    assert nuage["pente"] is None
    assert nuage["droite"] is None


def test_la_memo_renvoie_le_meme_objet(ventes):
    analyseur = DataAnalyzer(df=ventes)
    assert analyseur.nuage_points() is analyseur.nuage_points()


# ----------------------------------------------------------------------
# Passage par l'API
# ----------------------------------------------------------------------


@pytest.fixture
def client_connecte():
    User.objects.create_user("disp", password=MOT_DE_PASSE)
    client = Client(enforce_csrf_checks=False)
    client.login(username="disp", password=MOT_DE_PASSE)
    return client


@pytest.fixture
def projet(client_connecte):
    client_connecte.post("/upload", {
        "fichier": SimpleUploadedFile(
            "ventes.csv", CONTENU.encode("utf-8"), "text/csv"
        ),
    })
    return Projet.objects.get()


def test_l_api_expose_la_dispersion(client_connecte, projet):
    donnees = client_connecte.get(f"/api/donnees?id={projet.pk}").json()
    nuage = donnees["nuage"]

    assert nuage["disponible"] is True
    assert set(nuage) >= {
        "x_nom", "y_nom", "x", "y", "r", "force",
        "droite", "x_min", "x_max", "total", "echantillon",
    }
    assert len(nuage["x"]) == len(nuage["y"]) > 0
    assert len(nuage["x"]) <= 600
    assert nuage["x_nom"] and nuage["y_nom"]
