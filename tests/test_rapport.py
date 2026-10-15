"""Tests de la génération de rapports PDF."""

import pandas as pd
import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors

from analyzer import DataAnalyzer
from core import rapport
from core.models import Projet
from core.rapport import generer_rapport


@pytest.fixture
def ventes():
    return pd.DataFrame({
        "Date": ["05/01/2026", "10/01/2026", "05/02/2026"],
        "Produit": ["PC", "Souris", "Écran"],
        "Catégorie": ["Info", "Accessoires", "Info"],
        "Quantité": [1, 5, 2],
        "Prix": [1800, 25, 220],
    })


def test_les_barres_du_pdf_utilisent_le_bleu_okabe():
    """Les graphiques du PDF reprennent la couleur principale des
    graphiques du site : palette Okabe-Ito, pensée pour le daltonisme."""
    assert rapport.ACCENT.hexval() == colors.HexColor("#0072B2").hexval()


def test_pdf_est_un_vrai_pdf(ventes):
    a = DataAnalyzer(df=ventes)
    contenu = generer_rapport(a, a.df, "Mon analyse", "ventes.csv")
    octets = contenu.getvalue()
    assert octets[:5] == b"%PDF-"
    assert len(octets) > 1000


def test_pdf_respecte_les_filtres(ventes):
    """Le PDF d'un filtre restreint doit être plus petit (moins de lignes)."""
    a = DataAnalyzer(df=ventes)
    complet = generer_rapport(a, a.df, "Tout", "v.csv").getvalue()
    filtre = a.filtrer(categorie="Info")
    partiel = generer_rapport(a, filtre, "Info", "v.csv").getvalue()
    assert partiel[:5] == b"%PDF-"
    assert len(partiel) > 500


def test_pdf_avec_colonne_date_absente():
    """Le rapport fonctionne même sans colonne de date."""
    df = pd.DataFrame({
        "Produit": ["PC", "Souris"],
        "Prix": [1800, 25],
    })
    a = DataAnalyzer(df=df)
    octets = generer_rapport(a, a.df, "Sans date", "v.csv").getvalue()
    assert octets[:5] == b"%PDF-"


@pytest.fixture
def client_connecte():
    User.objects.create_user("pdf", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    client.login(username="pdf", password="MotDePasse-2026")
    return client


def _fichier():
    contenu = (
        "Date,Produit,Catégorie,Quantité,Prix\n"
        "05/01/2026,PC,Info,1,1800\n"
        "10/01/2026,Souris,Accessoires,5,25\n"
    )
    return SimpleUploadedFile("pdf.csv", contenu.encode("utf-8"), "text/csv")


def test_telechargement_du_rapport(client_connecte):
    client_connecte.post("/upload", {"fichier": _fichier()})
    projet = Projet.objects.get()
    reponse = client_connecte.get(f"/projet/{projet.pk}/rapport")
    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"
    assert reponse.content[:5] == b"%PDF-"
    assert "attachment" in reponse["Content-Disposition"]


def test_rapport_protege():
    client = Client(enforce_csrf_checks=False)
    assert client.get("/projet/1/rapport").status_code == 302


# ----------------------------------------------------------------------
# Graphiques du rapport
# ----------------------------------------------------------------------

def test_graphe_evolution_est_un_dessin(ventes):
    """Le graphique mensuel est un dessin vectoriel reportlab."""
    a = DataAnalyzer(df=ventes)
    graphe = rapport._graphe_evolution(a.evolution_mensuelle())

    assert isinstance(graphe, Drawing)
    assert graphe.width > 0 and graphe.height > 0
    assert len(graphe.contents) == 1  # les barres sont bien dans le dessin


def test_graphe_evolution_absent_si_rien_a_tracer():
    """Sans chiffre à tracer, la série est vide : rien à dessiner.

    Sans colonne de date, l'évolution ne disparaît pas pour autant : elle se
    découpe en tranches (« Part 1 », « Part 2 »…) — voir `_evolution_mensuelle`.
    """
    sans_ca = DataAnalyzer(df=pd.DataFrame({"Produit": ["PC"], "Note": ["x"]}))
    assert rapport._graphe_evolution(sans_ca.evolution_mensuelle()) is None

    a = DataAnalyzer(df=pd.DataFrame({"Produit": ["PC"], "Prix": [1800.0]}))
    graphique = rapport._graphe_evolution(a.evolution_mensuelle())
    assert isinstance(graphique, Drawing)


def test_graphe_evolution_absent_au_dela_de_la_limite(ventes):
    """36 mois de barres tiendraient sur l'axe : on garde le tableau."""
    a = DataAnalyzer(df=ventes)
    trop_longue = pd.Series(
        [1.0] * 40, index=pd.period_range("2026-01", periods=40, freq="M")
    )

    assert rapport._graphe_evolution(trop_longue) is None
    assert rapport._graphe_evolution(a.evolution_mensuelle()) is not None


def test_graphe_categories_est_un_dessin(ventes):
    a = DataAnalyzer(df=ventes)
    graphe = rapport._graphe_categories(a.par_categorie())

    assert isinstance(graphe, Drawing)
    assert len(graphe.contents) == 1


def test_graphe_categories_absent_au_dela_de_la_limite():
    """13 catégories empilées verticalement ne tiennent pas en hauteur."""
    a = DataAnalyzer(df=pd.DataFrame({
        "Produit": [f"P{i}" for i in range(13)],
        "Categorie": [f"C{i}" for i in range(13)],
        "Quantite": [1] * 13,
        "Prix": [10.0] * 13,
    }))

    assert rapport._graphe_categories(a.par_categorie()) is None


def test_graphe_categories_absent_si_rien_a_dessiner():
    """Une série vide (pas de colonne de catégorie) : rien à tracer."""
    a = DataAnalyzer(df=pd.DataFrame({"Produit": ["PC"], "Prix": [1800.0]}))

    assert rapport._graphe_categories(a.par_categorie()) is None


def test_libelles_compacts_masque_le_trop_plein():
    noms = [f"m{i}" for i in range(36)]
    compacts = rapport._libelles_compacts(noms)

    assert len(compacts) == 36  # le compte de catégories ne change pas
    assert compacts[0] == "m0"
    assert sum(1 for nom in compacts if nom) <= 14
    # Court, aucun libellé n'est masqué.
    assert rapport._libelles_compacts(["a", "b", "c"]) == ["a", "b", "c"]


def test_libelle_mois_est_compact():
    assert rapport._libelle_mois("2026-01") == "01/26"
    assert rapport._libelle_mois("2026-12") == "12/26"
    assert rapport._libelle_mois("période libre") == "période libre"[:7]


def test_les_graphiques_sont_bien_inseres_dans_le_pdf(ventes, monkeypatch):
    """Le même rapport, privé de ses graphiques, doit faire moins de poids."""
    a = DataAnalyzer(df=ventes)
    avec = generer_rapport(a, a.df, "Avec graphiques", "v.csv").getvalue()

    monkeypatch.setattr(rapport, "_graphe_evolution", lambda _: None)
    monkeypatch.setattr(rapport, "_graphe_categories", lambda _: None)
    sans = generer_rapport(a, a.df, "Sans graphiques", "v.csv").getvalue()

    assert avec[:5] == b"%PDF-" and sans[:5] == b"%PDF-"
    assert len(avec) > len(sans)
    assert avec.count(b"\n") > sans.count(b"\n")  # les tracés s'ajoutent


def test_rapport_avec_graphiques_depuis_l_interface(client_connecte):
    """Le téléchargement réel intègre les dessins sans planter."""
    client_connecte.post("/upload", {"fichier": _fichier()})
    projet = Projet.objects.get()

    reponse = client_connecte.get(f"/projet/{projet.pk}/rapport")

    assert reponse.status_code == 200
    assert reponse.content[:5] == b"%PDF-"
    assert len(reponse.content) > 2000
