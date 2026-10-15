"""Limitation du débit des routes coûteuses — sans dépendance externe.

Un compte ne doit pas pouvoir saturer le serveur en montant des fichiers de
100 Mo à la chaîne, ni en générant des exports à répétition (chacun relit et
recalcule le fichier entier).

Les compteurs vivent dans le même cache que la protection force-brute :
Redis en production (partagé entre les workers), cache local en
développement. Si le cache devient indisponible, on **laisse passer** :
bloquer des utilisateurs légitimes serait plus grave qu'un pic de charge
ponctuel.
"""

from django.core.cache import cache

# Route              → (clés max, fenêtre en secondes)
LIMITES = {
    "upload": (10, 3600),        # 10 fichiers par heure et par compte
    "export": (60, 60),          # 60 exports par minute et par compte
}

# Nom présenté à l'utilisateur (« trop d'exports », pas « trop de export »).
LIBELLES = {
    "upload": "imports de fichiers",
    "export": "exports",
}


def _cle(route: str, utilisateur) -> str:
    return f"debit:{route}:{getattr(utilisateur, 'pk', None) or 'anonyme'}"


def autoriser(route: str, utilisateur) -> bool:
    """Compteur la requête et dit si l'action reste autorisée."""
    if route not in LIMITES:
        raise KeyError(f"Route non limitée : {route}")
    max_tentatives, fenetre = LIMITES[route]
    cle = _cle(route, utilisateur)
    try:
        compte = cache.get(cle, 0) + 1
        cache.set(cle, compte, fenetre)
    except Exception:  # noqa: BLE001 — cache indisponible : on ne bloque pas
        return True
    return compte <= max_tentatives


def message_limite(route: str) -> str:
    """Message lisible annonçant quand réessayer."""
    max_tentatives, fenetre = LIMITES[route]
    moment = "dans une heure" if fenetre >= 3600 else "dans une minute"
    return (
        f"Trop de {LIBELLES[route]} en peu de temps "
        f"({max_tentatives} maximum). Réessaie {moment}."
    )
