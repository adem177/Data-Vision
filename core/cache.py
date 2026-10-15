"""
Cache partagé des analyseurs.

Chargée une fois, une analyse est mise en cache pour éviter de relire le
fichier à chaque appel AJAX des graphiques.

En développement, le cache local (LocMemCache) suffit. En production, on
définit REDIS_URL : tous les workers gunicorn partagent alors le même cache,
ce qui évite de recharger inutilement les gros fichiers.
"""

import logging
import os

from django.core.cache import cache

logger = logging.getLogger(__name__)

PREFIXE = "datavision:analyseur:"
# Durée de vie d'un analyseur en cache : 1 h (au-delà, on relit le fichier).
DUREE_VIE = 3600

# Un analyseur mis en cache est sérialisé entièrement (dataframe compris).
# Au-delà de ce nombre de lignes, on préfère le relire à chaque fois plutôt
# que d'occuper une tranche de mémoire Redis proportionnelle au fichier.
# Ajustable avec DATAVISION_CACHE_MAX_ROWS ; « 0 » désactive la limite.
LIMITE_CACHE_LIGNES = int(os.environ.get("DATAVISION_CACHE_MAX_ROWS", "200000"))


def _trop_pour_le_cache(analyseur) -> bool:
    """Vrai si l'analyseur est trop gros pour être mis en cache."""
    if LIMITE_CACHE_LIGNES <= 0:
        return False
    try:
        return len(analyseur.df) > LIMITE_CACHE_LIGNES
    except Exception:  # noqa: BLE001 — on ne veut pas faire échouer la mise en cache
        return False


def charger(projet_id) -> object | None:
    """Renvoie l'analyseur mis en cache, ou None s'il n'y est pas."""
    try:
        return cache.get(f"{PREFIXE}{projet_id}")
    except Exception:  # noqa: BLE001 — Redis inaccessible : on retente le chargement
        logger.warning("Cache illisible pour le projet %s", projet_id, exc_info=True)
        return None


def stocker(projet_id, analyseur) -> None:
    """Met l'analyseur en cache (échec silencieux : ce n'est qu'une optimisation)."""
    if _trop_pour_le_cache(analyseur):
        logger.debug(
            "Projet %s non mis en cache : %s lignes dépassent la limite de %s",
            projet_id, len(analyseur.df), LIMITE_CACHE_LIGNES,
        )
        return
    try:
        cache.set(f"{PREFIXE}{projet_id}", analyseur, DUREE_VIE)
    except Exception:  # noqa: BLE001
        logger.warning("Impossible de mettre en cache le projet %s", projet_id, exc_info=True)


def oublier(projet_id) -> None:
    """Vide le cache d'un projet (après modification ou suppression)."""
    try:
        cache.delete(f"{PREFIXE}{projet_id}")
    except Exception:  # noqa: BLE001
        logger.warning("Impossible de vider le cache du projet %s", projet_id, exc_info=True)


def vider() -> None:
    """Vide tout le cache des analyseurs (utile pour les tests)."""
    try:
        cache.clear()
    except Exception:  # noqa: BLE001
        logger.warning("Impossible de vider le cache", exc_info=True)
