"""Suppression définitive du compte (confirmation par mot de passe).

L'objet utilisateur supprime ses analyses en cascade, mais pas les fichiers
sur le disque : chaque CSV doit être retiré à la main, sinon la suppression
du compte laisse des orphelins dans `media/uploads/`.
"""

import os

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.models import Projet


CONTENU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    "05/01/2026,A,Info,1,400\n"
    "10/01/2026,B,Info,1,600\n"
)

MOT_DE_PASSE = "MotDePasse-2026"


@pytest.fixture
def client_connecte():
    User.objects.create_user("compte", password=MOT_DE_PASSE)
    client = Client(enforce_csrf_checks=False)
    client.login(username="compte", password=MOT_DE_PASSE)
    return client


@pytest.fixture
def projet(client_connecte):
    client_connecte.post("/upload", {
        "fichier": SimpleUploadedFile("v.csv", CONTENU.encode("utf-8"), "text/csv")
    })
    return Projet.objects.get()


def _supprimer(client, mdp):
    return client.post("/compte/supprimer", {"mot_de_passe": mdp}, follow=True)


# ----------------------------------------------------------------------
# Confirmation par mot de passe
# ----------------------------------------------------------------------

def test_mauvais_mdp_ne_supprime_rien(client_connecte, projet):
    reponse = _supprimer(client_connecte, "MotDePasseFaux")

    assert "Mot de passe incorrect" in reponse.content.decode("utf-8")
    assert User.objects.filter(username="compte").exists()
    assert Projet.objects.count() == 1
    # L'utilisateur reste connecté.
    assert reponse.wsgi_request.user.is_authenticated


def test_get_ne_supprime_rien(client_connecte, projet):
    """La destruction ne doit jamais venir d'un simple lien suivi (GET)."""
    reponse = client_connecte.get("/compte/supprimer")

    assert reponse.status_code == 302
    assert User.objects.filter(username="compte").exists()
    assert Projet.objects.count() == 1


def test_sans_mdp_ne_supprime_rien(client_connecte, projet):
    reponse = client_connecte.post("/compte/supprimer", {})

    assert reponse.status_code == 302
    assert User.objects.count() == 1


# ----------------------------------------------------------------------
# Suppression complète
# ----------------------------------------------------------------------

def test_suppression_complete(client_connecte, projet):
    chemin = projet.fichier.path

    reponse = _supprimer(client_connecte, MOT_DE_PASSE)

    assert reponse.status_code == 200
    assert b"Compte supprim" in reponse.content  # page de confirmation
    assert User.objects.count() == 0
    assert Projet.objects.count() == 0
    assert not os.path.exists(chemin)  # le CSV ne reste pas orphelin


def test_suppression_deconnecte_l_utilisateur(client_connecte, projet):
    _supprimer(client_connecte, MOT_DE_PASSE)

    # La session est close : on repart vers la connexion.
    reponse = client_connecte.get("/projets", follow=True)
    assert reponse.redirect_chain[0][0] == "/connexion?next=/projets"


def test_suppression_quand_un_fichier_est_deja_perdu(client_connecte, projet):
    """Un fichier déjà disparu ne doit pas empêcher de supprimer le compte."""
    projet.fichier.storage.delete(projet.fichier.name)

    reponse = _supprimer(client_connecte, MOT_DE_PASSE)

    assert reponse.status_code == 200
    assert User.objects.count() == 0
    assert Projet.objects.count() == 0


def test_suppression_ne_touche_pas_aux_autres_comptes(client_connecte, projet):
    User.objects.create_user("temoin", password=MOT_DE_PASSE)
    temoin = Client(enforce_csrf_checks=False)
    temoin.login(username="temoin", password=MOT_DE_PASSE)
    temoin.post("/upload", {
        "fichier": SimpleUploadedFile("t.csv", CONTENU.encode("utf-8"), "text/csv")
    })

    _supprimer(client_connecte, MOT_DE_PASSE)

    assert list(User.objects.values_list("username", flat=True)) == ["temoin"]
    assert Projet.objects.count() == 1
    assert Projet.objects.get().proprietaire.username == "temoin"


def test_zone_dangereuse_presente_sur_la_liste(client_connecte):
    page = client_connecte.get("/projets").content.decode("utf-8")

    assert "/compte/supprimer" in page
    assert "Supprimer mon compte" in page
    assert 'type="password"' in page
