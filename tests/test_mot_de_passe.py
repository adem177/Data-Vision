"""Réinitialisation du mot de passe : gabarits, e-mail et changement effectif."""

import re

from django.contrib.auth import get_user_model
from django.core import mail

Utilisateur = get_user_model()


def _utilisateur():
    return Utilisateur.objects.create_user(
        username="alice",
        email="alice@example.com",
        password="Ancien-Mdp-2026",
    )


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------

def test_page_demande_de_reinit(client):
    reponse = client.get("/mot-de-passe-oublie")

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert 'id="contenu-principal"' in html
    assert "lien-evitement" in html
    assert "auth-scene" in html, "la page doit réutiliser la scène scindée"


def test_le_lien_est_affiche_sur_la_page_de_connexion(client):
    html = client.get("/connexion").content.decode()

    assert "Mot de passe oublié ?" in html
    assert "/mot-de-passe-oublie" in html


# ----------------------------------------------------------------------
# Envoi de l'e-mail
# ----------------------------------------------------------------------

def test_envoi_du_lien_de_reinitialisation(client):
    _utilisateur()

    reponse = client.post("/mot-de-passe-oublie", {"email": "alice@example.com"})

    assert reponse.status_code == 302
    assert reponse["Location"] == "/mot-de-passe-oublie/envoye"
    assert len(mail.outbox) == 1

    courrier = mail.outbox[0]
    assert courrier.to == ["alice@example.com"]
    assert "DataVision" in courrier.subject
    assert "/mot-de-passe-oublie/" in courrier.body


def test_adresse_inconnue_nenvoie_rien(client):
    """Énumération impossible : toujours un redirection, jamais d'e-mail."""
    reponse = client.post("/mot-de-passe-oublie", {"email": "inconnu@example.com"})

    assert reponse.status_code == 302
    assert mail.outbox == []


def test_le_lien_utilise_le_domaine_reel_de_la_requete(client):
    """L'application « sites » fournit example.com par défaut.

    Le lien envoyé doit pourtant pointer vers l'hôte sur lequel l'utilisateur
    se trouve réellement, sans quoi il est inutilisable.
    """
    _utilisateur()

    client.post(
        "/mot-de-passe-oublie",
        {"email": "alice@example.com"},
        SERVER_NAME="127.0.0.1",
        SERVER_PORT="8000",
    )

    corps = mail.outbox[0].body
    assert "example.com/mot-de-passe-oublie" not in corps
    assert "http://127.0.0.1:8000/mot-de-passe-oublie/" in corps


# ----------------------------------------------------------------------
# Changement effectif du mot de passe
# ----------------------------------------------------------------------

def test_changement_de_mdp_depuis_le_lien(client):
    utilisateur = _utilisateur()
    client.post("/mot-de-passe-oublie", {"email": "alice@example.com"})

    lien = re.search(
        r"/mot-de-passe-oublie/[-\w]+/[-\w]+", mail.outbox[0].body
    ).group(0)

    # Le lien réel redirige vers une URL sans jeton (fuite dans le Referer).
    redirection = client.get(lien)
    assert redirection.status_code == 302
    url_formulaire = redirection["Location"]
    assert url_formulaire.endswith("/set-password")

    page = client.get(url_formulaire)
    assert page.status_code == 200
    assert "Nouveau mot de passe" in page.content.decode("utf-8", "ignore")

    reponse = client.post(
        url_formulaire,
        {"new_password1": "Nouveau-Mdp-2026", "new_password2": "Nouveau-Mdp-2026"},
    )
    assert reponse.status_code == 302
    assert reponse["Location"] == "/mot-de-passe-oublie/modifie"

    utilisateur.refresh_from_db()
    assert utilisateur.check_password("Nouveau-Mdp-2026")
    assert not utilisateur.check_password("Ancien-Mdp-2026")


def test_ancien_mdp_ne_plus_valide_apres_reinit(client):
    _utilisateur()
    client.post("/mot-de-passe-oublie", {"email": "alice@example.com"})
    lien = re.search(r"/mot-de-passe-oublie/[-\w]+/[-\w]+", mail.outbox[0].body).group(0)
    url_formulaire = client.get(lien)["Location"]

    client.post(
        url_formulaire,
        {"new_password1": "Nouveau-Mdp-2026", "new_password2": "Nouveau-Mdp-2026"},
    )

    assert client.login(username="alice", password="Nouveau-Mdp-2026")
    client.logout()
    assert not client.login(username="alice", password="Ancien-Mdp-2026")


def test_lien_invalide_affiche_un_message(client):
    _utilisateur()

    reponse = client.get("/mot-de-passe-oublie/cGllcnJl/mauvais-jeton")

    assert reponse.status_code == 200
    assert "Lien expiré" in reponse.content.decode("utf-8", "ignore")
