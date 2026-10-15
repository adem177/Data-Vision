"""Tests de fiabilité : supervision, fichier perdu, jeu de démonstration cassé.

Ces cas ne sont pas des erreurs de programme mais des états du monde réel
(purge des media/, base inaccessible, jeu de démo absent) : l'application doit
les signaler clairement au lieu de renvoyer une erreur 500.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from unittest.mock import patch

from core import cache as cache_analyseurs
from core.models import Projet


CONTENU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    "05/01/2026,A,Info,1,400\n"
    "10/01/2026,B,Info,1,600\n"
    "05/02/2026,A,Info,1,600\n"
)


@pytest.fixture
def client_connecte():
    User.objects.create_user("fiabilite", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    client.login(username="fiabilite", password="MotDePasse-2026")
    return client


@pytest.fixture
def projet_charge(client_connecte):
    """Un projet importé, dont on retire ensuite le fichier du disque."""
    client_connecte.post(
        "/upload",
        {"fichier": SimpleUploadedFile("v.csv", CONTENU.encode("utf-8"), "text/csv")},
    )
    return Projet.objects.get()


def _perdre_le_fichier(projet):
    """Supprime le fichier du stockage en laissant l'enregistrement en base."""
    projet.fichier.storage.delete(projet.fichier.name)
    cache_analyseurs.vider()  # l'analyseur reste en cache sinon


# ----------------------------------------------------------------------
# Route de supervision
# ----------------------------------------------------------------------

def test_sante_repond_ok(client_connecte):
    reponse = client_connecte.get("/health")
    assert reponse.status_code == 200
    assert reponse.json() == {"statut": "ok", "base": "ok"}


def test_sante_signale_la_panne_de_base():
    """Un moniteur doit recevoir un 503, sinon il ne détecte jamais la panne."""
    client = Client(enforce_csrf_checks=False)
    with patch("core.vues_api.connection.cursor",
               side_effect=Exception("base injoignable")):
        reponse = client.get("/health")
    assert reponse.status_code == 503
    assert reponse.json() == {"statut": "erreur", "base": "erreur"}


# ----------------------------------------------------------------------
# Fichier retiré des media/
# ----------------------------------------------------------------------

def test_dashboard_fichier_perdu_redirige_avec_message(client_connecte, projet_charge):
    _perdre_le_fichier(projet_charge)

    reponse = client_connecte.get(f"/dashboard/{projet_charge.pk}", follow=True)

    assert reponse.status_code == 200
    assert reponse.redirect_chain[-1][0] == "/projets"
    # L'apostrophe est échappée en &#x27; par le gabarit.
    assert b"existe plus sur le serveur" in reponse.content


def test_api_fichier_perdu_renvoie_404(client_connecte, projet_charge):
    _perdre_le_fichier(projet_charge)

    reponse = client_connecte.get(f"/api/donnees?id={projet_charge.pk}")

    assert reponse.status_code == 404
    assert "n'existe plus" in reponse.json()["erreur"]


def test_export_fichier_perdu_ne_plante_pas(client_connecte, projet_charge):
    _perdre_le_fichier(projet_charge)

    reponse = client_connecte.get(f"/export?id={projet_charge.pk}", follow=True)

    assert reponse.status_code == 200


def test_rapport_fichier_perdu_ne_plante_pas(client_connecte, projet_charge):
    _perdre_le_fichier(projet_charge)

    reponse = client_connecte.get(f"/projet/{projet_charge.pk}/rapport", follow=True)

    assert reponse.status_code == 200


def test_le_fichier_retrouve_sauve_apres_reimport(client_connecte, projet_charge):
    """Une fois le fichier réimporté, l'analyse redevient accessible."""
    _perdre_le_fichier(projet_charge)
    assert client_connecte.get(f"/api/donnees?id={projet_charge.pk}").status_code == 404

    client_connecte.post(
        "/upload",
        {"fichier": SimpleUploadedFile("v2.csv", CONTENU.encode("utf-8"), "text/csv")},
    )
    assert Projet.objects.count() == 2  # l'ancien projet reste, le nouveau fonctionne


# ----------------------------------------------------------------------
# Jeu de démonstration
# ----------------------------------------------------------------------

def test_demo_casse_affiche_une_erreur_sans_orphelin(client_connecte):
    """Un jeu de démo illisible doit laisser la base propre."""
    with patch("core.services.DataAnalyzer", side_effect=ValueError("fichier corrompu")):
        reponse = client_connecte.get("/demo")

    assert reponse.status_code == 200
    assert b"fichier corrompu" in reponse.content
    assert Projet.objects.count() == 0
