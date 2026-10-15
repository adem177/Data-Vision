# -*- coding: utf-8 -*-
"""Preuve de concept Angular : page hébergée par Django + API JSON consommées par Angular."""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.models import Projet


# ----------------------------------------------------------------------
# Fixtures locales
# ----------------------------------------------------------------------

@pytest.fixture
def client_connecte():
    """Client connecté à un compte vierge."""
    User.objects.create_user("ng", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    client.login(username="ng", password="MotDePasse-2026")
    return client


def _fichier():
    contenu = (
        "Date,Produit,Catégorie,Quantité,Prix\n"
        "05/01/2026,A,Info,1,400\n"
        "10/02/2026,B,Info,2,600\n"
    )
    return SimpleUploadedFile("angular.csv", contenu.encode("utf-8"), "text/csv")


# ----------------------------------------------------------------------
# Page hébergée par Django
# ----------------------------------------------------------------------

def test_page_angular_redirige_vers_connexion(client):
    """Sans session, la page Angular exige une connexion."""
    reponse = client.get("/angular")
    assert reponse.status_code == 302
    assert "/connexion" in reponse.url


def test_page_angular_heberge_le_composant(client_connecte):
    """Django rend la coquille et laisse l'affichage à Angular."""
    reponse = client_connecte.get("/angular")
    assert reponse.status_code == 200

    html = reponse.content.decode()
    assert "<app-root" in html
    assert "angular/browser/main.js" in html
    assert "api/projets" in html  # le rôle de la page est expliqué


# ----------------------------------------------------------------------
# API JSON consommées par Angular
# ----------------------------------------------------------------------

def test_api_projets_interdit_aux_anonymes(client):
    """Une API JSON reste protégée par la session."""
    reponse = client.get("/api/projets")
    assert reponse.status_code == 302


def test_api_projets_renvoie_les_analyses(client_connecte):
    """L'API liste les analyses du compte connecté, champs attendus par Angular."""
    client_connecte.post("/upload", {"fichier": _fichier()})
    projet = Projet.objects.get()

    reponse = client_connecte.get("/api/projets")
    assert reponse.status_code == 200
    assert reponse["Content-Type"].startswith("application/json")

    projets = reponse.json()["projets"]
    assert len(projets) == 1
    assert {"id", "nom", "fichier", "lignes", "ca", "date"} <= set(projets[0])
    assert projets[0]["id"] == projet.pk
    assert projets[0]["nom"] == projet.nom


def test_api_projets_ne_montre_que_ses_propres_analyses(client_connecte):
    """Le compte connecté ne voit pas les analyses des autres."""
    autre = User.objects.create_user("autre", password="MotDePasse-2026")
    Projet.objects.create(
        nom="Analyse d'autrui", proprietaire=autre,
        fichier="uploads/autrui.csv", nb_lignes=5,
    )

    projets = client_connecte.get("/api/projets").json()["projets"]
    assert projets == []
