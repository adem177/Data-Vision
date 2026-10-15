"""Renommage d'une analyse et remplacement de son fichier.

Deux opérations qui se font depuis « Mes analyses » : renommer ne touche pas
au fichier importé, et remplacer ne l'écrase jamais avant d'avoir vérifié que
le nouveau fichier est lisible — sinon un import raté détruirait des données
qui fonctionnaient.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from unittest.mock import patch

from core.models import Projet


CONTENU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    "05/01/2026,A,Info,1,400\n"
    "10/01/2026,B,Info,1,600\n"
    "05/02/2026,A,Info,1,600\n"
)

NOUVEAU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    "07/03/2026,C,Bureau,2,250\n"
    "09/03/2026,D,Bureau,1,900\n"
)

ENTETE_SEULE = "Date,Produit,Catégorie,Quantité,Prix\n"


def _fichier(contenu, nom="v.csv"):
    if isinstance(contenu, str):
        contenu = contenu.encode("utf-8")
    return SimpleUploadedFile(nom, contenu, "text/csv")


@pytest.fixture
def client_connecte():
    User.objects.create_user("gestion", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    client.login(username="gestion", password="MotDePasse-2026")
    return client


@pytest.fixture
def projet(client_connecte):
    client_connecte.post("/upload", {"fichier": _fichier(CONTENU)})
    return Projet.objects.get()


# ----------------------------------------------------------------------
# Renommage
# ----------------------------------------------------------------------

def test_renommage_change_le_nom(client_connecte, projet):
    reponse = client_connecte.post(
        f"/projet/{projet.pk}/renommer", {"nom": "Bilan 2026"}
    )

    assert reponse.status_code == 302
    projet.refresh_from_db()
    assert projet.nom == "Bilan 2026"


def test_renommage_ne_touche_ni_au_fichier_ni_aux_indicateurs(
    client_connecte, projet
):
    ancien_fichier = projet.fichier.name
    ancien_ca = projet.ca_total

    client_connecte.post(f"/projet/{projet.pk}/renommer", {"nom": "Autre"})

    projet.refresh_from_db()
    assert projet.fichier.name == ancien_fichier
    assert projet.ca_total == ancien_ca
    assert Projet.objects.count() == 1


def test_renommage_du_fichier_refuse(client_connecte, projet):
    """Un nom vide (ou d'espaces) doit être refusé, pas écrire « None »."""
    reponse = client_connecte.post(
        f"/projet/{projet.pk}/renommer", {"nom": "   "}, follow=True
    )

    assert "ne peut pas être vide" in reponse.content.decode("utf-8")
    projet.refresh_from_db()
    assert projet.nom == "v"  # nom d'origine du fichier, inchangé


def test_renommage_nom_trop_long_refuse(client_connecte, projet):
    client_connecte.post(f"/projet/{projet.pk}/renommer", {"nom": "x" * 201})

    projet.refresh_from_db()
    assert projet.nom == "v"


def test_renommage_get_ne_change_rien(client_connecte, projet):
    """La modification exige un POST : un lien suivi ne renomme pas."""
    client_connecte.get(f"/projet/{projet.pk}/renommer")

    projet.refresh_from_db()
    assert projet.nom == "v"


def test_renommage_d_un_autre_compte_404(client_connecte, projet):
    User.objects.create_user("intrus", password="MotDePasse-2026")
    intrus = Client(enforce_csrf_checks=False)
    intrus.login(username="intrus", password="MotDePasse-2026")

    reponse = intrus.post(f"/projet/{projet.pk}/renommer", {"nom": "Volé"})

    assert reponse.status_code == 404
    projet.refresh_from_db()
    assert projet.nom == "v"


# ----------------------------------------------------------------------
# Remplacement du fichier
# ----------------------------------------------------------------------

def test_remplacement_garde_le_projet_et_ses_identifiants(client_connecte, projet):
    ancien_pk = projet.pk

    reponse = client_connecte.post(
        f"/projet/{projet.pk}/remplacer",
        {"fichier": _fichier(NOUVEAU, "nouveau.csv")},
        follow=True,
    )

    assert reponse.status_code == 200
    assert Projet.objects.count() == 1  # pas de nouveau projet créé
    projet.refresh_from_db()
    assert projet.pk == ancien_pk
    assert projet.nom_fichier == "nouveau.csv"
    assert projet.nb_lignes == 2  # indicateurs recalculés


def test_remplacement_invalide_le_cache(client_connecte, projet):
    """L'analyseur de l'ancien fichier reste en cache une heure sans invalidation."""
    avant = client_connecte.get(f"/api/donnees?id={projet.pk}").json()
    assert avant["kpis"]["nb_ventes"] == 3

    client_connecte.post(
        f"/projet/{projet.pk}/remplacer", {"fichier": _fichier(NOUVEAU, "n2.csv")}
    )

    apres = client_connecte.get(f"/api/donnees?id={projet.pk}").json()
    assert apres["kpis"]["nb_ventes"] == 2
    assert apres["mois"] == ["2026-03"]  # plus de janvier/février
    assert apres["categories"]["labels"] == ["Bureau"]


def test_remplacement_format_non_supporte(client_connecte, projet):
    ancien = projet.fichier.name

    client_connecte.post(
        f"/projet/{projet.pk}/remplacer",
        {"fichier": SimpleUploadedFile("note.txt", b"du texte", "text/plain")},
    )

    projet.refresh_from_db()
    assert projet.fichier.name == ancien


def test_remplacement_sans_fichier(client_connecte, projet):
    ancien = projet.fichier.name

    reponse = client_connecte.post(f"/projet/{projet.pk}/remplacer", {})

    assert reponse.status_code == 302
    projet.refresh_from_db()
    assert projet.fichier.name == ancien


def test_remplacement_fichier_illisible_conserve_l_ancien(client_connecte, projet):
    """Un fichier refusé au chargement ne doit pas détruire ce qui marchait."""
    ancien = projet.fichier.name

    with patch("core.services.DataAnalyzer",
               side_effect=ValueError("fichier illisible")):
        reponse = client_connecte.post(
            f"/projet/{projet.pk}/remplacer",
            {"fichier": _fichier(CONTENU, "cassé.csv")},
            follow=True,
        )

    assert "fichier illisible" in reponse.content.decode("utf-8")
    projet.refresh_from_db()
    assert projet.fichier.name == ancien
    # L'analyse continue de fonctionner avec les données précédentes.
    assert client_connecte.get(
        f"/api/donnees?id={projet.pk}"
    ).status_code == 200


def test_remplacement_vide_conserve_l_ancien(client_connecte, projet):
    ancien = projet.fichier.name

    client_connecte.post(
        f"/projet/{projet.pk}/remplacer", {"fichier": _fichier(ENTETE_SEULE, "vide.csv")}
    )

    projet.refresh_from_db()
    assert projet.fichier.name == ancien
    assert client_connecte.get(
        f"/api/donnees?id={projet.pk}"
    ).status_code == 200


def test_remplacement_repare_un_fichier_perdu(client_connecte, projet):
    """Le cas d'usage principal : le fichier a disparu, on le réimporte."""
    projet.fichier.storage.delete(projet.fichier.name)

    reponse = client_connecte.post(
        f"/projet/{projet.pk}/remplacer",
        {"fichier": _fichier(CONTENU, "retour.csv")},
        follow=True,
    )

    assert reponse.status_code == 200
    assert reponse.redirect_chain[-1][0] == f"/dashboard/{projet.pk}"
    projet.refresh_from_db()
    assert projet.fichier_existe


def test_remplacement_autre_compte_404(client_connecte, projet):
    User.objects.create_user("intrus2", password="MotDePasse-2026")
    intrus = Client(enforce_csrf_checks=False)
    intrus.login(username="intrus2", password="MotDePasse-2026")

    reponse = intrus.post(
        f"/projet/{projet.pk}/remplacer", {"fichier": _fichier(NOUVEAU, "x.csv")}
    )

    assert reponse.status_code == 404
    assert Projet.objects.count() == 1


# ----------------------------------------------------------------------
# Signalement d'un fichier manquant sur la liste
# ----------------------------------------------------------------------

def test_liste_signale_un_fichier_manquant(client_connecte, projet):
    page = client_connecte.get("/projets").content.decode("utf-8")
    assert "Fichier perdu sur le serveur" not in page

    projet.fichier.storage.delete(projet.fichier.name)

    page = client_connecte.get("/projets").content.decode("utf-8")
    assert "Fichier perdu sur le serveur" in page
    assert "Réimporter le fichier" in page


def test_liste_propose_le_renommage(client_connecte, projet):
    page = client_connecte.get("/projets").content.decode("utf-8")

    assert f"/projet/{projet.pk}/renommer" in page
    assert "/compte/supprimer" in page
