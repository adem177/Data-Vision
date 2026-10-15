"""Tests du parcours utilisateur : compte, projets sauvegardés, isolation."""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.models import Projet


@pytest.fixture
def donnees_csv():
    contenu = (
        "Date,Produit,Catégorie,Quantité,Prix\n"
        "01/09/2026,PC portable,Informatique,2,1800\n"
        "02/09/2026,Souris,Accessoires,10,25\n"
        "03/09/2026,Écran,Informatique,4,220\n"
    )
    return SimpleUploadedFile("ventes.csv", contenu.encode("utf-8"), "text/csv")


@pytest.fixture
def client_connecte():
    """Client de test connecté avec un utilisateur de test."""
    User.objects.create_user("amine", password="motdepasse123")
    client = Client()
    client.login(username="amine", password="motdepasse123")
    return client


def test_inscription_cree_un_compte(donnees_csv):
    client = Client()
    reponse = client.post("/inscription", {
        "username": "nouveau",
        "email": "nouveau@test.tn",
        "password1": "MotDePasse-S3cur1sé",
        "password2": "MotDePasse-S3cur1sé",
    })
    assert reponse.status_code == 302
    assert User.objects.filter(username="nouveau").exists()


def test_page_protégée_redirige_vers_connexion():
    client = Client()
    reponse = client.get("/projets")
    assert reponse.status_code == 302
    assert "/connexion" in reponse.url


def test_upload_sans_connexion_redirige(donnees_csv):
    client = Client()
    reponse = client.post("/upload", {"fichier": donnees_csv})
    assert reponse.status_code == 302
    assert "/connexion" in reponse.url


def test_upload_cree_un_projet(client_connecte, donnees_csv):
    avant = Projet.objects.count()
    reponse = client_connecte.post("/upload", {"fichier": donnees_csv}, follow=True)
    assert reponse.status_code == 200
    assert Projet.objects.count() == avant + 1

    projet = Projet.objects.get()
    assert projet.proprietaire.username == "amine"
    assert projet.nb_lignes == 3
    assert float(projet.ca_total) == 2 * 1800 + 10 * 25 + 4 * 220


def test_dashboard_et_api_fonctionnent(client_connecte, donnees_csv):
    client_connecte.post("/upload", {"fichier": donnees_csv})
    projet = Projet.objects.get()

    reponse = client_connecte.get(f"/dashboard/{projet.pk}")
    assert reponse.status_code == 200

    reponse = client_connecte.get(f"/api/donnees?id={projet.pk}")
    assert reponse.status_code == 200
    assert reponse.json()["kpis"]["ca_total"] == 4730


def test_export_fonctionne(client_connecte, donnees_csv):
    client_connecte.post("/upload", {"fichier": donnees_csv})
    projet = Projet.objects.get()
    reponse = client_connecte.get(f"/export?id={projet.pk}&format=csv")
    assert reponse.status_code == 200
    assert b"CA" in reponse.content


def test_isolation_des_projets_entre_utilisateurs(client_connecte, donnees_csv):
    """Un utilisateur ne peut pas voir l'analyse d'un autre."""
    client_connecte.post("/upload", {"fichier": donnees_csv})
    projet = Projet.objects.get()

    # Deuxième utilisateur
    User.objects.create_user("inconnu", password="motdepasse123")
    autre = Client()
    autre.login(username="inconnu", password="motdepasse123")

    # Son tableau de bord est vide
    assert autre.get("/projets").context["projets"].count() == 0
    # Il ne peut ni ouvrir, ni interroger, ni exporter l'analyse d'autrui
    assert autre.get(f"/dashboard/{projet.pk}").status_code == 302
    assert autre.get(f"/api/donnees?id={projet.pk}").status_code == 404
    assert autre.get(f"/export?id={projet.pk}").status_code == 302


def test_demo_cree_une_analyse(client_connecte):
    import os
    from django.conf import settings

    if not os.path.exists(settings.BASE_DIR / "data" / "sample_sales.csv"):
        pytest.skip("Jeu de démonstration absent")
    reponse = client_connecte.get("/demo", follow=True)
    assert reponse.status_code == 200
    assert Projet.objects.filter(nom__startswith="Démo").exists()


def test_suppression_de_projet(client_connecte, donnees_csv):
    client_connecte.post("/upload", {"fichier": donnees_csv})
    projet = Projet.objects.get()
    reponse = client_connecte.post(f"/projet/{projet.pk}/supprimer")
    assert reponse.status_code == 302
    assert Projet.objects.count() == 0
