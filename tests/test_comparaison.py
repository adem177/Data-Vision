"""Tests de la comparaison de périodes (moteur + API)."""

import pandas as pd
import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from analyzer import DataAnalyzer
from core.models import Projet


@pytest.fixture
def ventes():
    """CA de 1000 en janvier, 1500 en février, 2000 en mars."""
    return pd.DataFrame({
        "Date": ["05/01/2026", "10/01/2026", "05/02/2026", "10/02/2026", "05/03/2026"],
        "Produit": ["A", "B", "A", "B", "A"],
        "Catégorie": ["Info", "Info", "Info", "Info", "Info"],
        "Quantité": [1, 1, 1, 1, 1],
        "Prix": [400, 600, 600, 900, 2000],
    })


def test_comparaison_meme_duree(ventes):
    a = DataAnalyzer(df=ventes)
    r = a.comparer_periodes("2026-01-01", "2026-01-31", "2026-02-01", "2026-02-28")
    assert r["periode_1"]["ca"] == 1000
    assert r["periode_2"]["ca"] == 1500
    assert r["variations"]["ca"] == 50.0
    assert r["comparable"] is True


def test_comparaison_durees_differentes(ventes):
    a = DataAnalyzer(df=ventes)
    r = a.comparer_periodes("2026-01-01", "2026-01-31", "2026-02-01", "2026-03-31")
    assert r["comparable"] is False


def test_variation_avec_base_nulle(ventes):
    """Pas de division par zéro si la première période est vide."""
    a = DataAnalyzer(df=ventes)
    r = a.comparer_periodes("2027-01-01", "2027-01-31", "2026-01-01", "2026-01-31")
    assert r["periode_1"]["ca"] == 0
    assert r["variations"]["ca"] is None


def test_comparaison_respecte_le_filtre_categorie(ventes):
    a = DataAnalyzer(df=ventes)
    r = a.comparer_periodes(
        "2026-01-01", "2026-01-31", "2026-02-01", "2026-02-28", categorie="Info"
    )
    assert r["periode_1"]["ca"] == 1000


def test_comparaison_dates_illisibles(ventes):
    """Une saisie de date illisible est ignorée au lieu de faire échouer l'API."""
    a = DataAnalyzer(df=ventes)
    r = a.comparer_periodes("pasune-date", "", "2026-02-01", "2026-02-28")

    # Période 1 sans borne exploitable : toutes les lignes sont retenues.
    assert r["periode_1"]["ca"] == 4500
    # Et rien d'inutilisable n'est renvoyé au navigateur.
    assert r["periode_1"]["debut"] == ""
    assert r["periode_2"]["debut"] == "2026-02-01"
    assert r["comparable"] is False


def test_comparaison_durees_calculable_partiellement(ventes):
    """Une période bornée d'un seul côté ne casse pas le calcul de durée."""
    a = DataAnalyzer(df=ventes)
    r = a.comparer_periodes("2026-01-01", None, "2026-02-01", "2026-02-28")
    assert r["periode_1"]["lignes"] is None
    assert r["comparable"] is False


@pytest.fixture
def client_connecte():
    User.objects.create_user("cmp", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    client.login(username="cmp", password="MotDePasse-2026")
    return client


def _fichier():
    contenu = (
        "Date,Produit,Catégorie,Quantité,Prix\n"
        "05/01/2026,A,Info,1,400\n"
        "10/01/2026,B,Info,1,600\n"
        "05/02/2026,A,Info,1,600\n"
        "10/02/2026,B,Info,1,900\n"
    )
    return SimpleUploadedFile("cmp.csv", contenu.encode("utf-8"), "text/csv")


def test_api_comparaison(client_connecte):
    client_connecte.post("/upload", {"fichier": _fichier()})
    projet = Projet.objects.get()
    reponse = client_connecte.get(
        f"/api/comparaison?id={projet.pk}"
        "&p1_debut=2026-01-01&p1_fin=2026-01-31"
        "&p2_debut=2026-02-01&p2_fin=2026-02-28"
    )
    assert reponse.status_code == 200
    donnees = reponse.json()
    assert donnees["periode_1"]["ca"] == 1000
    assert donnees["periode_2"]["ca"] == 1500
    assert donnees["variations"]["ca"] == 50.0


def test_api_comparaison_date_illisible(client_connecte):
    """Une date illisible dans l'URL ne renvoie pas une erreur 500."""
    client_connecte.post("/upload", {"fichier": _fichier()})
    projet = Projet.objects.get()
    reponse = client_connecte.get(
        f"/api/comparaison?id={projet.pk}"
        "&p1_debut=pasune-date&p1_fin=&p2_debut=2026-02-01&p2_fin=2026-02-28"
    )
    assert reponse.status_code == 200
    donnees = reponse.json()
    assert donnees["periode_1"]["debut"] == ""
    assert donnees["periode_2"]["ca"] == 1500


def test_api_comparaison_protegee():
    client = Client(enforce_csrf_checks=False)
    assert client.get("/api/comparaison?id=1").status_code == 302
