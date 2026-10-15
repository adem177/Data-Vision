"""Configuration de la journalisation (LOGGING).

En production, la console est le seul canal disponible : une règle manquante
signalerait des erreurs 500 perdues. Ces tests verrouillent la présence du
handler console, le niveau par défaut, sa surcharge par
`DATAVISION_LOG_LEVEL`, et le fait qu'une alerte de cache atteigne
réellement la journalisation.

Le niveau réglé par l'environnement est vérifié en sous-processus : les
réglages sont figés au démarrage de Django, on ne peut pas les recharger à
chaud dans le processus de test.
"""

import logging
import os
import subprocess
import sys
from types import SimpleNamespace

from django.conf import settings
from django.core.cache import cache as cache_django

from core import cache


def _niveau_configure(valeur: str | None) -> str:
    """Niveau effectif de la racine avec DATAVISION_LOG_LEVEL = valeur."""
    env = os.environ.copy()
    if valeur is None:
        env.pop("DATAVISION_LOG_LEVEL", None)
    else:
        env["DATAVISION_LOG_LEVEL"] = valeur
    code = (
        "import os, django; "
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'datavision.settings'); "
        "django.setup(); "
        "from django.conf import settings; "
        "print(settings.LOGGING['root']['level'])"
    )
    resultat = subprocess.run(
        [sys.executable, "-c", code],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert resultat.returncode == 0, resultat.stderr
    return resultat.stdout.strip().splitlines()[-1]


# ----------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------

def test_le_handler_est_une_console():
    """Pas de fichier de log : la sortie va sur stderr, collectée par Render."""
    handler = settings.LOGGING["handlers"]["console"]

    assert handler["class"] == "logging.StreamHandler"
    assert "formatter" in handler


def test_un_seul_canal_pour_toute_l_application():
    assert settings.LOGGING["root"]["handlers"] == ["console"]
    # Le journal de l'application remonte à la racine (pas de handler propre) :
    # une seule trace en console, et les tests peuvent la capter.
    assert "handlers" not in settings.LOGGING["loggers"]["core"]


def test_django_et_son_serveur_sont_couverts():
    assert "console" in settings.LOGGING["loggers"]["django"]["handlers"]
    assert "console" in settings.LOGGING["loggers"]["django.server"]["handlers"]


# ----------------------------------------------------------------------
# Niveau
# ----------------------------------------------------------------------

def test_niveau_par_defaut_info():
    assert _niveau_configure(None) == "INFO"


def test_niveau_reglable_par_l_environnement():
    assert _niveau_configure("DEBUG") == "DEBUG"
    assert _niveau_configure("warning") == "WARNING"  # insensible à la casse


def test_niveau_invalide_retombe_sur_info():
    """Une valeur absurde ne doit pas empêcher le site de démarrer."""
    assert _niveau_configure("brouillard") == "INFO"


# ----------------------------------------------------------------------
# Une alerte atteint réellement la journalisation
# ----------------------------------------------------------------------

def _panner(*_args, **_kwargs):
    raise RuntimeError("panne simulée")


def test_echec_de_cache_est_journalise(caplog, monkeypatch):
    """Redis peut tomber : l'alerte doit rester lisible dans les logs."""
    monkeypatch.setattr(cache_django, "set", _panner)

    with caplog.at_level(logging.WARNING, logger="core.cache"):
        cache.stocker(42, SimpleNamespace(df=[]))

    assert "Impossible de mettre en cache le projet 42" in caplog.text


def test_cache_illisible_est_journalise(caplog, monkeypatch):
    monkeypatch.setattr(cache_django, "get", _panner)

    with caplog.at_level(logging.WARNING, logger="core.cache"):
        assert cache.charger(7) is None

    assert "Cache illisible pour le projet 7" in caplog.text
