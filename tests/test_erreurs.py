"""Pages d'erreur du site (404, 403, 500).

Hors DEBUG, Django affiche ses pages nues, en anglais : DataVision déclare ses
propres handlers. Ils ne se déclenchent qu'avec `DEBUG=False`, d'où
l'override de réglage dans chacun de ces tests — et la page 500 est tenue de
ne rien laisser filtrer de l'exécution interrompue.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from core.models import Projet


CONTENU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    "05/01/2026,A,Info,1,400\n"
    "10/01/2026,B,Info,1,600\n"
)


@pytest.fixture
def client_connecte():
    User.objects.create_user("erreurs", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    client.login(username="erreurs", password="MotDePasse-2026")
    return client


@pytest.fixture
def projet(client_connecte):
    client_connecte.post("/upload", {
        "fichier": SimpleUploadedFile("v.csv", CONTENU.encode("utf-8"), "text/csv")
    })
    return Projet.objects.get()


@pytest.fixture
def client_sans_levee(client_connecte):
    """Client qui renvoie la page 500 au lieu de relancer l'exception.

    Par défaut, le client de test Django **relance** toute exception capturée
    pendant le rendu — on ne pourrait donc jamais examiner la page 500.
    """
    client_connecte.raise_request_exception = False
    return client_connecte


# ----------------------------------------------------------------------
# 404 — adresse inconnue
# ----------------------------------------------------------------------

@override_settings(DEBUG=False)
def test_page_404_du_site(client):
    reponse = client.get("/adresse-qui-nexiste-pas")

    assert reponse.status_code == 404
    page = reponse.content.decode("utf-8")
    assert "Page introuvable" in page
    assert "erreur 404" in page


@override_settings(DEBUG=False)
def test_page_404_propose_un_retour(client):
    reponse = client.get("/adresse-qui-nexiste-pas")
    page = reponse.content.decode("utf-8")

    assert 'href="/projets"' in page
    assert 'href="/"' in page


@override_settings(DEBUG=False)
def test_page_404_sur_une_analyse_inexistante(client_connecte):
    """Un identifiant jamais créé ne doit pas planter ni afficher une trace."""
    reponse = client_connecte.get("/projet/999999/supprimer")

    assert reponse.status_code == 404
    assert "erreur 404" in reponse.content.decode("utf-8")


# ----------------------------------------------------------------------
# 403 — jeton CSRF absent
# ----------------------------------------------------------------------

@override_settings(DEBUG=False)
def test_page_403_sans_jeton_csrf(client):
    """Un POST sans jeton rend la page « Accès refusé » (CSRF_FAILURE_VIEW)."""
    reponse = Client(enforce_csrf_checks=True).post("/upload", {})

    assert reponse.status_code == 403
    page = reponse.content.decode("utf-8")
    assert "Accès refusé" in page
    assert "erreur 403" in page
    assert "jeton" in page  # on explique la cause probable


# ----------------------------------------------------------------------
# 500 — erreur serveur
# ----------------------------------------------------------------------

@override_settings(DEBUG=False)
def test_page_500_sans_fuite(client_sans_levee, projet, monkeypatch):
    """La page 500 ne doit rien laisser filtrer de l'exécution interrompue."""

    def casser(_projet):
        raise RuntimeError("PANNE_SIMULEE_NE_DOIT_PAS_APPARAITRE")

    # `dashboard` appelle `_analyseur_ou_perdu`, qui résout `_analyseur`
    # dans `core.services` : c'est donc là qu'il faut interrompre le chemin.
    monkeypatch.setattr("core.services._analyseur", casser)

    reponse = client_sans_levee.get(f"/dashboard/{projet.pk}")

    assert reponse.status_code == 500
    page = reponse.content.decode("utf-8")
    assert "Erreur serveur" in page
    assert "erreur 500" in page
    assert "PANNE_SIMULEE_NE_DOIT_PAS_APPARAITRE" not in page
    assert "Traceback" not in page
    assert "core/vues_projets" not in page


@override_settings(DEBUG=False)
def test_page_500_rassure_sur_les_donnees(client_sans_levee, projet, monkeypatch):
    """L'utilisateur doit savoir que son import n'a pas disparu."""
    monkeypatch.setattr(
        "core.services._analyseur",
        lambda _p: (_ for _ in ()).throw(RuntimeError("panne")),
    )

    page = client_sans_levee.get(f"/dashboard/{projet.pk}").content.decode("utf-8")

    assert "restent enregistrés" in page
    assert 'href="/projets"' in page


# ----------------------------------------------------------------------
# Hors DEBUG, le handler ne se déclenche pas (Django garde ses pages)
# ----------------------------------------------------------------------

def test_en_developpement_l_erreur_404_renvoie_quand_meme_404(client):
    """Quel que soit le gabarit, le code HTTP reste juste."""
    assert client.get("/adresse-qui-nexiste-pas").status_code == 404
