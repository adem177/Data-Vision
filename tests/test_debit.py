"""Tests de la limite de débit sur les routes coûteuses (upload, export).

Un compte ne doit pas pouvoir saturer le serveur : chaque export relit et
recalcule le fichier entier, chaque upload enregistre jusqu'à 100 Mo.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core import throttle
from core.models import Projet


CONTENU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    "05/01/2026,A,Info,1,400\n"
    "10/01/2026,B,Info,1,600\n"
)


@pytest.fixture
def client_connecte():
    User.objects.create_user("debit", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    client.login(username="debit", password="MotDePasse-2026")
    return client


def _fichier(nom="v.csv"):
    return SimpleUploadedFile(nom, CONTENU.encode("utf-8"), "text/csv")


def _importer(client, nom="v.csv"):
    return client.post("/upload", {"fichier": _fichier(nom)})


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

def test_routes_limitees_sont_configurees():
    assert set(throttle.LIMITES) == {"upload", "export"}
    for maximum, fenetre in throttle.LIMITES.values():
        assert maximum > 0
        assert fenetre > 0


def test_message_limite_en_francais():
    message = throttle.message_limite("upload")
    assert "imports de fichiers" in message
    assert "dans une heure" in message
    assert "dans une minute" in throttle.message_limite("export")


def test_route_inconnue_leve():
    """Se tromper de nom de route doit échouer fort, pas laisser passer."""
    with pytest.raises(KeyError):
        throttle.autoriser("telechargement", User())


# ----------------------------------------------------------------------
# Import
# ----------------------------------------------------------------------

def test_les_premiers_imports_passent(client_connecte):
    limite = throttle.LIMITES["upload"][0]
    for i in range(limite):
        assert _importer(client_connecte, f"v{i}.csv").status_code == 302
    assert Projet.objects.count() == limite


def test_import_au_dela_de_la_limite_refuse(client_connecte):
    limite = throttle.LIMITES["upload"][0]
    for i in range(limite):
        _importer(client_connecte, f"v{i}.csv")

    reponse = _importer(client_connecte, "en_trop.csv")

    assert reponse.status_code == 200  # page d'accueil avec le message
    assert b"imports de fichiers" in reponse.content
    assert Projet.objects.count() == limite  # rien n'a été enregistré


def test_la_limite_d_import_est_par_compte(client_connecte):
    """Un autre compte n'est pas pénalisé par les excès du premier."""
    limite = throttle.LIMITES["upload"][0]
    for i in range(limite):
        _importer(client_connecte, f"v{i}.csv")

    User.objects.create_user("autre", password="MotDePasse-2026")
    autre = Client(enforce_csrf_checks=False)
    autre.login(username="autre", password="MotDePasse-2026")

    assert _importer(autre, "libre.csv").status_code == 302


# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------

def test_export_au_dela_de_la_limite_renvoie_429(client_connecte, monkeypatch):
    """La cadence est vérifiée sans attendre soixante requêtes réelles."""
    monkeypatch.setitem(throttle.LIMITES, "export", (3, 60))
    _importer(client_connecte)
    projet = Projet.objects.get()

    reponses = [
        client_connecte.get(f"/export?id={projet.pk}") for _ in range(4)
    ]

    assert [r.status_code for r in reponses[:3]] == [200, 200, 200]
    assert reponses[3].status_code == 429
    assert "exports" in reponses[3].content.decode("utf-8")


def test_export_sans_limite_normale(client_connecte):
    _importer(client_connecte)
    projet = Projet.objects.get()

    reponse = client_connecte.get(f"/export?id={projet.pk}")

    assert reponse.status_code == 200
    assert reponse["Content-Type"].startswith("text/csv")


def test_limite_d_export_ne_bloque_pas_le_dashboard(client_connecte, monkeypatch):
    """La limite vise l'export, pas la consultation."""
    monkeypatch.setitem(throttle.LIMITES, "export", (1, 60))
    _importer(client_connecte)
    projet = Projet.objects.get()

    client_connecte.get(f"/export?id={projet.pk}")

    assert client_connecte.get(f"/api/donnees?id={projet.pk}").status_code == 200
    assert client_connecte.get(f"/dashboard/{projet.pk}").status_code == 200
