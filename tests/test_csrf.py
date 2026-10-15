"""Protection CSRF des routes POST, vérifiée avec un client strict.

Ces tests utilisent `enforce_csrf_checks=True` : sans jeton, le middleware
doit refuser la requête **avant** d'atteindre la vue — y compris pour un
utilisateur connecté, qui est précisément la cible d'une attaque par site
tiers. Le jeton arrive ensuite soit dans le champ `csrfmiddlewaretoken`
(formulaire), soit en en-tête `X-CSRFToken` (appel JavaScript).

Le jeton n'est délivré que par les pages qui en rendent un : l'accueil n'a
aucun formulaire et n'en émet pas, la page de connexion, si.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.models import Projet

CONTENU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    "05/01/2026,A,Info,1,400\n"
)
MOT_DE_PASSE = "MotDePasse-2026"


def _routes(pk: int) -> dict:
    """Les cinq routes POST représentatives du site."""
    return {
        "connexion": "/connexion",
        "upload": "/upload",
        "renommer": f"/projet/{pk}/renommer",
        "note": f"/projet/{pk}/note",
        "compte": "/compte/supprimer",
    }


@pytest.fixture
def client_fort():
    """Client qui applique réellement la vérification CSRF, déjà connecté."""
    User.objects.create_user("csrf", password=MOT_DE_PASSE)
    client = Client(enforce_csrf_checks=True)
    client.login(username="csrf", password=MOT_DE_PASSE)
    return client


@pytest.fixture
def projet(client_fort):
    """Analyse créée via un client souple : le strict refuse sans jeton."""
    souple = Client()
    souple.login(username="csrf", password=MOT_DE_PASSE)
    souple.post("/upload", {
        "fichier": SimpleUploadedFile("v.csv", CONTENU.encode("utf-8"), "text/csv"),
    })
    return Projet.objects.get()


def _jeton(client, url="/connexion") -> str:
    """Obtient un jeton valide en passant par une page qui en rend un."""
    client.get(url)
    assert "csrftoken" in client.cookies, f"{url} n'a délivré aucun jeton CSRF"
    return client.cookies["csrftoken"].value


# ----------------------------------------------------------------------
# Délivrance du jeton
# ----------------------------------------------------------------------

def test_accueil_ne_delivre_aucun_jeton(client):
    """Sans formulaire, pas de jeton : c'est Django qui décide, pas nous."""
    reponse = client.get("/")

    assert reponse.status_code == 200
    assert "csrftoken" not in reponse.cookies


def test_page_de_connexion_delivre_un_jeton(client):
    reponse = client.get("/connexion")

    assert reponse.status_code == 200
    assert "csrftoken" in reponse.cookies
    assert reponse.cookies["csrftoken"].value


# ----------------------------------------------------------------------
# Refus sans jeton
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "nom_route", ["connexion", "upload", "renommer", "note", "compte"]
)
def test_post_sans_jeton_rejete(client_fort, projet, nom_route):
    """Les cinq routes POST doivent répondre 403 sans jeton."""
    reponse = client_fort.post(_routes(projet.pk)[nom_route], {})

    assert reponse.status_code == 403


def test_sans_jeton_la_vue_ne_tourne_meme_pas(client_fort, projet):
    """Preuve que le 403 est bien un refus CSRF : rien n'a été modifié."""
    client_fort.post(
        _routes(projet.pk)["renommer"],
        {"csrfmiddlewaretoken": "", "nom": "Piratage"},
    )

    projet.refresh_from_db()
    assert projet.nom != "Piratage"


def test_jeton_tamponne_rejete(client_fort, projet):
    """Un jeton modifié ne doit pas passer la comparaison."""
    jeton = _jeton(client_fort)

    reponse = client_fort.post(
        _routes(projet.pk)["renommer"],
        {"csrfmiddlewaretoken": jeton + "X", "nom": "Piratage"},
    )

    assert reponse.status_code == 403
    projet.refresh_from_db()
    assert projet.nom != "Piratage"


# ----------------------------------------------------------------------
# Acceptation avec jeton
# ----------------------------------------------------------------------

def test_jeton_de_formulaire_accede_a_la_vue(client_fort, projet):
    """Chemin classique : le jeton rendu par le gabarit revient en champ."""
    jeton = _jeton(client_fort)

    reponse = client_fort.post(
        _routes(projet.pk)["renommer"],
        {"csrfmiddlewaretoken": jeton, "nom": "Nouveau nom"},
    )

    # La vue a été atteinte (redirection de succès), pas de refus.
    assert reponse.status_code == 302
    projet.refresh_from_db()
    assert projet.nom == "Nouveau nom"


def test_jeton_en_tete_xcsrftoken_accede_a_la_vue(client_fort):
    """Chemin JavaScript (fetch / XHR) : le jeton passe en en-tête."""
    jeton = _jeton(client_fort)

    # Mot de passe volontairement faux : la vue tourne mais refuse, et le
    # compte survit — on observe le passage sans conséquence.
    reponse = client_fort.post(
        "/compte/supprimer",
        {"mot_de_passe": "faux"},
        HTTP_X_CSRFTOKEN=jeton,
    )

    assert reponse.status_code == 302
    assert User.objects.filter(username="csrf").exists()


def test_connexion_avec_jeton_pour_un_anonyme():
    """Le chemin anonyme (formulaire de connexion) obéit aux mêmes règles."""
    User.objects.create_user("anonyme", password=MOT_DE_PASSE)
    client = Client(enforce_csrf_checks=True)
    client.get("/connexion")
    jeton = client.cookies["csrftoken"].value

    sans_jeton = Client(enforce_csrf_checks=True).post(
        "/connexion", {"username": "anonyme", "password": MOT_DE_PASSE}
    )
    avec_jeton = client.post(
        "/connexion",
        {
            "csrfmiddlewaretoken": jeton,
            "username": "anonyme",
            "password": MOT_DE_PASSE,
        },
    )

    assert sans_jeton.status_code == 403
    assert avec_jeton.status_code == 302  # connexion acceptée


# ----------------------------------------------------------------------
# Méthodes sûres
# ----------------------------------------------------------------------

def test_get_ne_demande_jamais_de_jeton(client_fort, projet):
    """Le CSRF ne s'applique qu'aux méthodes dangereuses (POST, PUT…)."""
    assert client_fort.get(f"/dashboard/{projet.pk}").status_code == 200
    assert client_fort.get("/projets").status_code == 200
    # `upload` n'accepte que POST : il redirige, il ne refuse pas.
    assert client_fort.get("/upload").status_code == 302
