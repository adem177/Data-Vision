"""Configuration de déploiement (render.yaml) et constantes de réglage.

Ces valeurs sont exposées en production : un test les verrouille pour éviter
qu'une régression silencieuse republie les identifiants de démonstration ou
désactive une protection mémoire.
"""

import re
from pathlib import Path

from core import cache, throttle

RACINE = Path(__file__).resolve().parents[1]


def _environnement(nom: str) -> str:
    """Valeur de la variable `nom` déclarée dans `render.yaml`."""
    texte = (RACINE / "render.yaml").read_text(encoding="utf-8")
    trouve = re.search(
        rf"- key: {re.escape(nom)}\s*\n\s+value:\s*\"?([^\"\n]+)\"?",
        texte,
    )
    assert trouve is not None, f"{nom} manque dans render.yaml"
    return trouve.group(1).strip()


# ----------------------------------------------------------------------
# Déploiement
# ----------------------------------------------------------------------

def test_identifiants_demo_masques_en_production():
    """Afficher « demo / DataVision2026 » sur la page de connexion revient
    à publier un compte d'accès : le déploiement doit les masquer."""
    assert _environnement("DATAVISION_DEMO_LOGIN") == "False"


def test_debug_eteint_dans_le_deploiement():
    assert _environnement("DJANGO_DEBUG") == "False"


def test_protections_memoire_declarees():
    """Les deux limites doivent être présentes et numériques dans le blueprint."""
    assert int(_environnement("DATAVISION_MAX_ROWS")) > 0
    # « 0 » désactive la mise en cache des gros fichiers : refusé ici.
    assert int(_environnement("DATAVISION_CACHE_MAX_ROWS")) > 0


def test_limite_de_cache_respectee_en_local():
    """La valeur par défaut doit rester positive (0 = pas de protection)."""
    assert cache.LIMITE_CACHE_LIGNES > 0
    assert cache.DUREE_VIE > 0


# ----------------------------------------------------------------------
# Supervision
# ----------------------------------------------------------------------

def test_render_surveille_la_route_de_sante():
    """Sans healthCheckPath, Render ne verrait jamais un 503 de /health :
    l'instance resterait « en vie » alors que la base est injoignable."""
    texte = (RACINE / "render.yaml").read_text(encoding="utf-8")
    assert re.search(r"^\s+healthCheckPath:\s*/health\s*$", texte, re.M), (
        "healthCheckPath: /health manque dans render.yaml"
    )


def test_route_de_sante_presente_dans_l_urlconf():
    """La route surveillée doit continuer d'exister sous le nom attendu."""
    from django.urls import resolve

    resolution = resolve("/health")
    assert resolution.url_name == "sante"
    assert resolution.namespace == "core"


def test_ci_verifie_la_configuration_de_production():
    """`manage.py check` seul ignore tout ce qui ne se voit qu'en production
    (HTTPS, HSTS, clé secrète) : le second contrôle doit tourner en CI."""
    texte = (RACINE / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "manage.py check --deploy" in texte
    # Il doit s'exécuter avec un DEBUG éteint, sinon il ne vérifie rien.
    assert 'DJANGO_DEBUG: "False"' in texte


# ----------------------------------------------------------------------
# Pages d'erreur
# ----------------------------------------------------------------------

def test_refus_csrf_delegue_a_la_vue_du_site():
    """Sans ce réglage, un POST sans jeton rend la page nue de Django."""
    from django.conf import settings
    from django.utils.module_loading import import_string

    vue = import_string(settings.CSRF_FAILURE_VIEW)
    assert callable(vue)


# ----------------------------------------------------------------------
# Limites de débit
# ----------------------------------------------------------------------

def test_routes_limitees_couvrent_les_operations_couteuses():
    """Upload (écriture lourde) et export (relecture complète) sont couverts."""
    assert set(throttle.LIMITES) == {"upload", "export"}
    nombre, fenetre = throttle.LIMITES["upload"]
    assert (nombre, fenetre) == (10, 3600)
    nombre, fenetre = throttle.LIMITES["export"]
    assert (nombre, fenetre) == (60, 60)
