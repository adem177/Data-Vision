"""Pagination de la liste des analyses (30 par page).

Une liste qui grandit ne doit pas produire une page interminable, et aucun
ajout d'URL ne doit pouvoir faire planter la vue : `?page=abc` et `?page=999`
sont avalés par `Paginator.get_page`. Les liens doivent en outre conserver la
recherche et le tri en cours.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core.models import Projet
from core.vues_projets import PAR_PAGE


@pytest.fixture
def utilisateur():
    return User.objects.create_user("pagine", password="MotDePasse-2026")


@pytest.fixture
def client_connecte(utilisateur):
    client = Client()
    client.login(username="pagine", password="MotDePasse-2026")
    return client


def _creer_projets(n: int, utilisateur) -> None:
    """Des analyses légères (sans fichier) : le test porte sur la liste."""
    for i in range(n):
        Projet.objects.create(nom=f"Analyse {i:03d}", proprietaire=utilisateur)


def _nb_cartes(html: str) -> int:
    return html.count('class="carte carte-projet"')


# ----------------------------------------------------------------------
# Taille des pages
# ----------------------------------------------------------------------

def test_constant_trente_par_page():
    assert PAR_PAGE == 30


def test_peu_d_analyses_sans_pagination(client_connecte, utilisateur):
    _creer_projets(3, utilisateur)

    page = client_connecte.get("/projets?tri=nom")

    assert page.status_code == 200
    html = page.content.decode("utf-8")
    assert _nb_cartes(html) == 3
    assert "pagination-analyses" not in html
    assert "page 1 sur 1" in html


def test_exactement_une_page_complete_ne_bascule_pas(client_connecte, utilisateur):
    """30 analyses = une page : il ne faut pas proposer une page 2 vide."""
    _creer_projets(PAR_PAGE, utilisateur)

    html = client_connecte.get("/projets").content.decode("utf-8")

    assert _nb_cartes(html) == PAR_PAGE
    assert "pagination-analyses" not in html


def test_trente_cinq_analyses_deux_pages(client_connecte, utilisateur):
    _creer_projets(35, utilisateur)

    html = client_connecte.get("/projets?tri=nom").content.decode("utf-8")

    assert _nb_cartes(html) == PAR_PAGE  # 30 sur la première
    assert "page 1 sur 2" in html
    assert "pagination-analyses" in html
    assert "Suivante" in html
    # Le total, lui, reste celui de tous les résultats.
    assert "35 résultats" in html


def test_deuxieme_page_affiche_les_cinq_restantes(client_connecte, utilisateur):
    _creer_projets(35, utilisateur)

    html = client_connecte.get("/projets?page=2&tri=nom").content.decode("utf-8")

    assert _nb_cartes(html) == 5
    assert "page 2 sur 2" in html
    assert "Analyse 034" in html
    assert "Analyse 000" not in html


# ----------------------------------------------------------------------
# Valeurs d'URL absurdes
# ----------------------------------------------------------------------

def test_page_abc_retombe_sur_la_premiere(client_connecte, utilisateur):
    _creer_projets(35, utilisateur)

    reponse = client_connecte.get("/projets?page=abc&tri=nom")

    assert reponse.status_code == 200
    html = reponse.content.decode("utf-8")
    assert "page 1 sur 2" in html
    assert "Analyse 000" in html


def test_page_hors_limites_retombe_sur_la_derniere(client_connecte, utilisateur):
    """`?page=999` ne doit ni planter ni afficher une page vide."""
    _creer_projets(35, utilisateur)

    reponse = client_connecte.get("/projets?page=999&tri=nom")

    assert reponse.status_code == 200
    html = reponse.content.decode("utf-8")
    assert "page 2 sur 2" in html
    assert "Analyse 034" in html


def test_page_zero_ne_planne_pas(client_connecte, utilisateur):
    _creer_projets(35, utilisateur)

    assert client_connecte.get("/projets?page=0").status_code == 200


# ----------------------------------------------------------------------
# Recherche et tri conservés
# ----------------------------------------------------------------------

def test_liens_de_page_conservent_q_et_tri(client_connecte, utilisateur):
    _creer_projets(35, utilisateur)

    html = client_connecte.get("/projets?q=Analyse&tri=nom").content.decode("utf-8")

    lien = re.search(r'href="(\?[^"]*page=2[^"]*)"', html)
    assert lien, "aucun lien vers la page 2"
    assert "q=Analyse" in lien.group(1)
    assert "tri=nom" in lien.group(1)


def test_recherche_restreinte_ne_change_pas_le_total(client_connecte, utilisateur):
    """5 résultats sur 35 : le compteur doit annoncer 5, pas 35."""
    _creer_projets(35, utilisateur)

    html = client_connecte.get("/projets?q=Analyse+03").content.decode("utf-8")

    assert "5 résultats" in html
    assert _nb_cartes(html) == 5
    assert "pagination-analyses" not in html


# ----------------------------------------------------------------------
# Contexte rendu et états limites
# ----------------------------------------------------------------------

def test_contexte_conserve_le_queryset_complet(client_connecte, utilisateur):
    """`projets` reste le queryset (`.count()` disponible) ; `page` la tranche."""
    _creer_projets(35, utilisateur)

    reponse = client_connecte.get("/projets?page=2")

    assert reponse.context["projets"].count() == 35
    assert reponse.context["total"] == 35
    assert len(reponse.context["page"]) == 5


def test_aucune_analyse_n_ecrase_la_page_vide(client_connecte):
    """Le queryset vide doit tomber sur l'état « aucune analyse » (200)."""
    reponse = client_connecte.get("/projets")

    assert reponse.status_code == 200
    assert reponse.context["total"] == 0
    assert "Aucune analyse pour l'instant" in reponse.content.decode("utf-8")


def test_tri_inconnu_retombe_sur_recent(client_connecte, utilisateur):
    """Un `tri` bidon dans l'URL ne doit pas planter le tri."""
    _creer_projets(3, utilisateur)

    reponse = client_connecte.get("/projets?tri=nimporte-quoi")

    assert reponse.status_code == 200
    assert reponse.context["tri"] == "recent"
