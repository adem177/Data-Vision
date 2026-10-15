"""Tests de la Phase A : sécurité et robustesse."""

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client


@pytest.fixture(autouse=True)
def vider_cache():
    """Le cache des tentatives de connexion doit repartir à zéro."""
    cache.clear()
    yield
    cache.clear()


def _post_connexion(client, username="inconnu", password="mauvais"):
    return client.post("/connexion", {"username": username, "password": password})


def test_inscription_email_deja_utilise():
    User.objects.create_user("amine", email="a@b.tn", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    reponse = client.post("/inscription", {
        "username": "autre",
        "email": "a@b.tn",
        "password1": "MotDePasse-2026",
        "password2": "MotDePasse-2026",
    })
    assert reponse.status_code == 200  # ré-affiche le formulaire avec l'erreur
    assert not User.objects.filter(username="autre").exists()


def test_inscription_mot_de_passe_faible_rejete():
    client = Client(enforce_csrf_checks=False)
    reponse = client.post("/inscription", {
        "username": "fragile",
        "email": "f@b.tn",
        "password1": "12345678",
        "password2": "12345678",
    })
    assert reponse.status_code == 200
    assert not User.objects.filter(username="fragile").exists()


def test_inscription_nom_deja_pris():
    User.objects.create_user("amine", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)
    reponse = client.post("/inscription", {
        "username": "amine",
        "email": "x@y.tn",
        "password1": "MotDePasse-2026",
        "password2": "MotDePasse-2026",
    })
    assert reponse.status_code == 200
    assert User.objects.filter(username="amine").count() == 1


def test_force_brute_bloquee_apres_5_echecs():
    User.objects.create_user("victime", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)

    for _ in range(5):
        _post_connexion(client, "victime", "mauvais")

    # 6e tentative : même les BONS identifiants sont refusés
    reponse = _post_connexion(client, "victime", "MotDePasse-2026")
    assert reponse.status_code == 200
    assert "bloqué" in reponse.content.decode("utf-8", "ignore").lower()
    assert not reponse.wsgi_request.user.is_authenticated


def test_bon_mdp_apres_peu_d_echecs_fonctionne():
    User.objects.create_user("victime", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)

    _post_connexion(client, "victime", "mauvais")
    _post_connexion(client, "victime", "mauvais")

    reponse = _post_connexion(client, "victime", "MotDePasse-2026")
    assert reponse.status_code == 302  # connexion réussie
    assert reponse.wsgi_request.user.is_authenticated


def test_blocage_isole_par_utilisateur():
    """Bloquer un compte n'empêche pas de se connecter avec un autre."""
    User.objects.create_user("victime", password="MotDePasse-2026")
    User.objects.create_user("autre", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)

    for _ in range(5):
        _post_connexion(client, "victime", "mauvais")

    reponse = _post_connexion(client, "autre", "MotDePasse-2026")
    assert reponse.status_code == 302
    assert reponse.wsgi_request.user.is_authenticated


def test_connexion_reussie_reinitialise_le_compteur():
    User.objects.create_user("victime", password="MotDePasse-2026")
    client = Client(enforce_csrf_checks=False)

    _post_connexion(client, "victime", "mauvais")
    _post_connexion(client, "victime", "mauvais")
    _post_connexion(client, "victime", "MotDePasse-2026")  # réussi -> compteur à 0

    # On peut encore rater 5 fois sans être bloqué
    for _ in range(5):
        client.logout()
        _post_connexion(client, "victime", "mauvais")

    reponse = _post_connexion(client, "victime", "MotDePasse-2026")
    assert reponse.status_code == 200  # toujours bloqué 15 min (échecs des 5 ci-dessus)
