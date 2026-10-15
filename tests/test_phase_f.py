"""Tests de la Phase F : pagination, recherche, mode sombre, compte démo."""

import pandas as pd
import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings

from analyzer import DataAnalyzer
from core.models import Projet


# ----------------------------------------------------------------------
# Fixtures locales
# ----------------------------------------------------------------------

@pytest.fixture
def client_connecte():
    User.objects.create_user("sarra", password="motdepasse123")
    client = Client()
    client.login(username="sarra", password="motdepasse123")
    return client


@pytest.fixture
def csv_gros():
    """30 lignes : largement de quoi paginer à 12 lignes par page."""
    lignes = ["Date,Produit,Catégorie,Quantité,Prix"]
    for i in range(1, 31):
        produit = "PC" if i % 2 else "Souris"
        lignes.append(f"{(i % 27) + 1:02d}/{(i % 12) + 1:02d}/2026,{produit},Informatique,{i},100")
    return SimpleUploadedFile("gros.csv", "\n".join(lignes).encode("utf-8"), "text/csv")


def _projet(nom, ca, proprietaire):
    return Projet.objects.create(
        nom=nom, proprietaire=proprietaire, fichier=f"uploads/{nom}.csv",
        nb_lignes=10, ca_total=ca,
    )


# ----------------------------------------------------------------------
# Pagination de l'aperçu
# ----------------------------------------------------------------------

@pytest.fixture
def df_25_lignes():
    return DataAnalyzer(df=pd.DataFrame({"A": list(range(25))}))


def test_apercu_divise_en_pages(df_25_lignes):
    page1 = df_25_lignes.apercu(n=10, page=1)

    assert page1["pages"] == 3
    assert page1["total"] == 25
    assert page1["page"] == 1
    assert len(page1["lignes"]) == 10
    assert page1["lignes"][0][0] == 0


def test_apercu_derniere_page_incomplete(df_25_lignes):
    page3 = df_25_lignes.apercu(n=10, page=3)

    assert page3["page"] == 3
    assert len(page3["lignes"]) == 5
    assert page3["lignes"][-1][0] == 24


def test_apercu_ramene_une_page_hors_limites(df_25_lignes):
    assert df_25_lignes.apercu(n=10, page=99)["page"] == 3
    assert df_25_lignes.apercu(n=10, page=-4)["page"] == 1


def test_apercu_avec_une_page_seule():
    a = DataAnalyzer(df=pd.DataFrame({"A": [1, 2, 3]}))
    page = a.apercu(n=12)

    assert page["pages"] == 1
    assert page["page"] == 1
    assert page["total"] == 3


def test_apercu_sur_un_jeu_vide():
    a = DataAnalyzer(df=pd.DataFrame({"A": [1, 2, 3]}))
    page = a.apercu(a.df.head(0), n=10)

    assert page["total"] == 0
    assert page["pages"] == 1
    assert page["lignes"] == []


def test_api_renvoie_la_pagination(client_connecte, csv_gros):
    client_connecte.post("/upload", {"fichier": csv_gros})
    projet = Projet.objects.get()

    donnees = client_connecte.get(f"/api/donnees?id={projet.pk}&page=2").json()

    assert donnees["apercu"]["page"] == 2
    assert donnees["apercu"]["pages"] == 3
    assert donnees["apercu"]["total"] == 30


def test_api_page_invalide_ne_plante_pas(client_connecte, csv_gros):
    client_connecte.post("/upload", {"fichier": csv_gros})
    projet = Projet.objects.get()

    donnees = client_connecte.get(f"/api/donnees?id={projet.pk}&page=abc").json()

    assert donnees["apercu"]["page"] == 1


def test_api_dates_invalides_ne_plantent_pas(client_connecte, csv_gros):
    """debut / fin viennent de l'URL : une saisie absurde ne doit pas
    renvoyer une erreur 500, la borne est simplement ignorée."""
    client_connecte.post("/upload", {"fichier": csv_gros})
    projet = Projet.objects.get()

    reponse = client_connecte.get(
        f"/api/donnees?id={projet.pk}&debut=pasune-date&fin=32/13/2026"
    )

    assert reponse.status_code == 200
    assert reponse.json()["apercu"]["total"] == 30


# ----------------------------------------------------------------------
# Recherche et tri dans « Mes analyses »
# ----------------------------------------------------------------------

def test_recherche_par_nom(client_connecte):
    utilisateur = User.objects.get(username="sarra")
    _projet("Ventes Tunis", 100, utilisateur)
    _projet("Ventes Sfax", 200, utilisateur)

    reponse = client_connecte.get("/projets?q=tunis")

    assert [p.nom for p in reponse.context["projets"]] == ["Ventes Tunis"]
    assert reponse.context["recherche"] == "tunis"


def test_recherche_sans_resultat(client_connecte):
    utilisateur = User.objects.get(username="sarra")
    _projet("Ventes Tunis", 100, utilisateur)

    reponse = client_connecte.get("/projets?q=inexistant")

    assert list(reponse.context["projets"]) == []
    assert "Aucun résultat" in reponse.content.decode()


def test_recherche_par_nom_de_fichier(client_connecte):
    """Le nom d'origine du fichier est stocké dans le champ « fichier »."""
    utilisateur = User.objects.get(username="sarra")
    Projet.objects.create(
        nom="Analyse", proprietaire=utilisateur,
        fichier="uploads/2026/10/ab12_sample_sales.csv", nb_lignes=5,
    )
    Projet.objects.create(
        nom="Autre", proprietaire=utilisateur,
        fichier="uploads/2026/10/cd34_budget.xlsx", nb_lignes=5,
    )

    reponse = client_connecte.get("/projets?q=sample")

    assert [p.nom for p in reponse.context["projets"]] == ["Analyse"]


def test_tri_par_chiffre_affaires_decroissant(client_connecte):
    utilisateur = User.objects.get(username="sarra")
    _projet("Petit", 100, utilisateur)
    _projet("Grand", 3000, utilisateur)
    _projet("Moyen", 500, utilisateur)

    reponse = client_connecte.get("/projets?tri=ca_desc")

    assert [p.nom for p in reponse.context["projets"]] == ["Grand", "Moyen", "Petit"]


def test_tri_par_nom(client_connecte):
    utilisateur = User.objects.get(username="sarra")
    _projet("Zebre", 100, utilisateur)
    _projet("Alpine", 200, utilisateur)

    reponse = client_connecte.get("/projets?tri=nom")

    assert [p.nom for p in reponse.context["projets"]] == ["Alpine", "Zebre"]


def test_tri_invalide_retombe_sur_le_plus_recent(client_connecte):
    reponse = client_connecte.get("/projets?tri=nimportequoi")
    assert reponse.context["tri"] == "recent"


def test_recherche_et_tri_combinees(client_connecte):
    utilisateur = User.objects.get(username="sarra")
    _projet("Bureau Tunis", 100, utilisateur)
    _projet("Bureau Sfax", 200, utilisateur)
    _projet("Ventes Tunis", 300, utilisateur)

    reponse = client_connecte.get("/projets?q=bureau&tri=ca_desc")

    assert [p.nom for p in reponse.context["projets"]] == ["Bureau Sfax", "Bureau Tunis"]


# ----------------------------------------------------------------------
# Compte de démonstration
# ----------------------------------------------------------------------

def test_commande_demo_cree_compte_et_analyse(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        call_command("creer_demo", verbosity=0)

    utilisateur = User.objects.get(username="demo")
    assert utilisateur.check_password("DataVision2026")

    projet = utilisateur.projets.get()
    assert projet.nb_lignes > 1000


def test_commande_demo_est_idempotente(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        call_command("creer_demo", verbosity=0)
        call_command("creer_demo", verbosity=0)

    assert User.objects.filter(username="demo").count() == 1
    assert Projet.objects.filter(proprietaire__username="demo").count() == 1


def test_connexion_du_compte_demo(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        call_command("creer_demo", verbosity=0)

    client = Client()
    reponse = client.post(
        "/connexion", {"username": "demo", "password": "DataVision2026"}, follow=True
    )

    assert reponse.status_code == 200
    assert reponse.redirect_chain, "la connexion doit rediriger"


def test_identifiants_demo_visibles_sur_la_page_connexion(client):
    html = client.get("/connexion").content.decode()
    assert "Compte de démonstration" in html


@override_settings(DEMO_LOGIN=False)
def test_identifiants_demo_masquables(client):
    html = client.get("/connexion").content.decode()
    assert "Compte de démonstration" not in html


# ----------------------------------------------------------------------
# Finitions d'interface et accessibilité
# ----------------------------------------------------------------------

def test_base_html_contient_mode_sombre_et_favicon(client):
    html = client.get("/").content.decode()

    assert 'id="btn-theme"' in html          # bouton de bascule
    assert "localStorage" in html            # préférence mémorisée
    assert 'rel="icon"' in html              # favicon SVG
    assert 'property="og:title"' in html     # aperçu au partage
    assert 'name="theme-color"' in html


def test_lien_devitement_present_sur_chaque_page(client):
    for url in ("/", "/connexion", "/inscription"):
        assert "lien-evitement" in client.get(url).content.decode(), url


def test_les_principales_pages_ont_le_point_dancrage(client):
    for url in ("/", "/connexion", "/inscription"):
        assert 'id="contenu-principal"' in client.get(url).content.decode(), url


def test_loader_accessible(client_connecte, csv_gros):
    client_connecte.post("/upload", {"fichier": csv_gros})
    projet = Projet.objects.get()
    html = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


def test_dashboard_indique_la_taille_maximale(client_connecte, csv_gros):
    """Le libellé d'upload doit refléter la limite configurée (zone visible)."""
    client_connecte.post("/upload", {"fichier": csv_gros})
    html = client_connecte.get("/").content.decode()
    assert "Mo max" in html


def test_pagination_presente_sur_le_dashboard(client_connecte, csv_gros):
    client_connecte.post("/upload", {"fichier": csv_gros})
    projet = Projet.objects.get()
    html = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    assert 'id="apercu-pagination"' in html


def test_les_graphiques_et_tables_sont_etiquetes(client_connecte, csv_gros):
    """Les cartes de graphiques portent un titre lisible (lecteurs d'écran)."""
    client_connecte.post("/upload", {"fichier": csv_gros})
    projet = Projet.objects.get()
    html = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    for texte in ("Top 5 des produits", "Flop 5 des produits", "Aperçu des données"):
        assert texte in html
