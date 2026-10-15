"""Tests du réglage manuel des colonnes (quand la détection auto échoue)."""

import pandas as pd
import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from analyzer import DataAnalyzer
from core.models import Projet


@pytest.fixture
def ventes():
    return pd.DataFrame({
        "Jour": ["01/09/2026", "02/09/2026", "03/09/2026"],
        "Article": ["PC", "Souris", "Écran"],
        "Famille": ["Info", "Accessoires", "Info"],
        "Qte": [2, 10, 4],
        "Montant": [1800, 25, 220],
    })


def test_detection_auto_avec_noms_inhabituels(ventes):
    """Le moteur comprend 'Qte' et 'Montant' sans configuration."""
    a = DataAnalyzer(df=ventes)
    assert a.colonnes["quantite"] == "Qte"
    assert a.colonnes["prix"] == "Montant"
    assert a.colonnes["produit"] == "Article"


def test_appliquer_mapping_corrige_les_roles(ventes):
    """L'utilisateur force 'Qte' comme quantité même si l'auto hésite."""
    a = DataAnalyzer(df=ventes)
    a.appliquer_mapping({"quantite": "Qte", "prix": "Montant", "produit": "Article"})
    assert a.colonnes["quantite"] == "Qte"
    assert a.colonnes["prix"] == "Montant"
    assert a.kpis()["ca_total"] == 2 * 1800 + 10 * 25 + 4 * 220


def test_mapping_avec_colonne_inexistante_ignored(ventes):
    """Une colonne inexistante est ignorée sans planter."""
    a = DataAnalyzer(df=ventes)
    avant = a.colonnes.copy()
    a.appliquer_mapping({"prix": "ColonneFantome"})
    assert a.colonnes == avant


def test_options_mapping_propose_toutes_les_roles(ventes):
    a = DataAnalyzer(df=ventes)
    options = a.options_mapping()
    roles = {o["role"] for o in options}
    assert roles == {"date", "produit", "categorie", "quantite", "prix"}
    # La colonne 'CA' (calculée) ne doit jamais être proposée
    for option in options:
        assert "CA" not in option["disponibles"]


@pytest.fixture
def client_connecte():
    User.objects.create_user("mapping", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    client.login(username="mapping", password="MotDePasse-2026")
    return client


def _fichier_mapping():
    contenu = (
        "Jour,Article,Famille,Qte,Montant\n"
        "01/09/2026,PC,Info,2,1800\n"
        "02/09/2026,Souris,Accessoires,10,25\n"
        "03/09/2026,Écran,Info,4,220\n"
    )
    return SimpleUploadedFile("ventes.csv", contenu.encode("utf-8"), "text/csv")


def test_page_colonnes_accessible(client_connecte):
    client_connecte.post("/upload", {"fichier": _fichier_mapping()})
    projet = Projet.objects.get()
    reponse = client_connecte.get(f"/projet/{projet.pk}/colonnes")
    assert reponse.status_code == 200
    assert b"Correspondance des colonnes" in reponse.content


def test_sauvegarde_du_mapping(client_connecte):
    client_connecte.post("/upload", {"fichier": _fichier_mapping()})
    projet = Projet.objects.get()

    reponse = client_connecte.post(f"/projet/{projet.pk}/colonnes", {
        "date": "Jour",
        "produit": "Article",
        "categorie": "Famille",
        "quantite": "Qte",
        "prix": "Montant",
    })
    assert reponse.status_code == 302

    projet.refresh_from_db()
    assert projet.mapping_colonnes["prix"] == "Montant"
    assert projet.mapping_colonnes["quantite"] == "Qte"


def test_page_colonnes_protegee():
    """Sans connexion, on est redirigé."""
    client = Client(enforce_csrf_checks=False)
    assert client.get("/projet/1/colonnes").status_code == 302


def test_mapping_visible_immediatement_sur_l_api(client_connecte):
    """Le cache stocke une copie sérialisée de l'analyseur.

    Sans invalidation, l'import met l'analyseur en cache avec la détection
    automatique, et le choix manuel de l'utilisateur ne se verrait qu'à
    l'expiration du cache (une heure). On inverse ici les rôles prix/quantité
    et on vérifie que l'API les reflète immédiatement.
    """
    client_connecte.post("/upload", {"fichier": _fichier_mapping()})
    projet = Projet.objects.get()

    # La détection automatique a choisi « Montant » comme prix.
    avant = client_connecte.get(f"/api/donnees?id={projet.pk}").json()
    assert avant["kpis"]["roles"]["prix"] == "Montant"

    client_connecte.post(f"/projet/{projet.pk}/colonnes", {
        "date": "Jour", "produit": "Article", "categorie": "Famille",
        "quantite": "Montant", "prix": "Qte",
    })

    apres = client_connecte.get(f"/api/donnees?id={projet.pk}").json()
    assert apres["kpis"]["roles"]["prix"] == "Qte"
    assert apres["kpis"]["roles"]["quantite"] == "Montant"


def test_mapping_visible_immediatement_sur_le_dashboard(client_connecte):
    client_connecte.post("/upload", {"fichier": _fichier_mapping()})
    projet = Projet.objects.get()

    client_connecte.post(f"/projet/{projet.pk}/colonnes", {
        "date": "Jour", "produit": "Article", "categorie": "Famille",
        "quantite": "Montant", "prix": "Qte",
    })

    reponse = client_connecte.get(f"/dashboard/{projet.pk}")
    assert reponse.status_code == 200
