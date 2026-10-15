"""
Configuration de pytest pour DataVision.

Configure Django avant la collecte des tests (sans dépendre de pytest-django),
crée une base de test éphémère pour la session, puis la remet à zéro
avant chaque test afin d'isoler les cas.
"""

import os
import sys

import django
import pytest
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import setup_test_environment

# Chemin du projet ajouté au PYTHONPATH pour importer analyzer / core / datavision.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datavision.settings")
django.setup()


@pytest.fixture(scope="session")
def django_db_setup():
    """Crée une base de test isolée pour toute la session de tests."""
    setup_test_environment()
    connection.creation.create_test_db(verbosity=0)
    yield
    connection.creation.destroy_test_db(verbosity=0)


@pytest.fixture(autouse=True)
def _db_propre(django_db_setup):
    """Vide les tables et le cache des analyseurs avant chaque test.

    Le cache est indexé par l'identifiant du projet : comme la base est
    remise à zéro, les identifiants repartent de 1 et un test pourrait sinon
    réutiliser l'analyseur laissé par le test précédent.
    """
    from core import cache as cache_analyseurs

    call_command("flush", verbosity=0, interactive=False, allow_cascade=True)
    cache_analyseurs.vider()
    # La boîte de réception de test est partagée par toute la session.
    mail.outbox.clear()
    yield


@pytest.fixture(autouse=True)
def _media_isole(tmp_path):
    """Redirige `MEDIA_ROOT` vers un dossier temporaire pendant le test.

    Les tests importent de vrais fichiers : sans cette garde, chaque exécution
    dépose ses CSV dans le vrai `media/` du projet — à côté des analyses
    réellement importées par l'utilisateur — et les noms se télescopent
    (Django ajoute alors un suffixe aléatoire, ce qui rend les assertions sur
    les noms de fichiers instables d'une exécution à l'autre).
    """
    with override_settings(MEDIA_ROOT=tmp_path):
        yield tmp_path


@pytest.fixture
def client() -> Client:
    """Client de test Django (protection CSRF désactivée)."""
    return Client(enforce_csrf_checks=False)
