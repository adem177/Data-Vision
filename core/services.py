"""
Services partagés par les vues de DataVision.

Le chargement de l'analyseur (avec son cache), la recherche d'une analyse
appartenant à l'utilisateur, la persistance des KPIs et le rendu des messages
d'erreur servent aussi bien l'interface que les API JSON : tout est centralisé
ici, et les modules `vues_*` ne contiennent que de la logique de vue.
"""

import os

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render

from analyzer import DataAnalyzer

from . import cache as cache_analyseurs
from .models import Projet

EXTENSIONS_VALIDES = {".csv", ".xlsx", ".xls"}


class FichierPerdu(Exception):
    """Le fichier associé au projet n'existe plus sur le disque du serveur.

    Une purge des `media/` (ou une restauration incomplète d'une base) peut
    laisser des projets orphelins : ce n'est pas une erreur de programme,
    c'est un état à signaler clairement à l'utilisateur.
    """


def _analyseur(projet: Projet) -> DataAnalyzer:
    """Charge (et met en cache) l'analyseur d'un projet depuis son fichier.

    Le cache est partagé entre les workers en production (Redis via REDIS_URL).

    Le mapping manuel enregistré en base est réappliqué à chaque construction :
    la base reste donc la source de vérité, même quand le cache est vide.
    """
    analyseur = cache_analyseurs.charger(projet.pk)
    if analyseur is None:
        chemin = projet.fichier.path
        if not os.path.exists(chemin):
            raise FichierPerdu(
                f"Le fichier « {projet.nom_fichier} » n'existe plus sur le serveur."
            )
        analyseur = DataAnalyzer(chemin)
        analyseur.appliquer_mapping(projet.mapping_colonnes)
        cache_analyseurs.stocker(projet.pk, analyseur)
    return analyseur


def oublier_analyseur(projet: Projet) -> None:
    """Vide le cache d'un projet : à appeler dès que la configuration change.

    `cache.set` **sérialise** sa valeur : modifier l'analyseur rendu par
    `_analyseur()` ne met donc pas le cache à jour. Sans cet oubli, un
    changement de mapping ne se verrait qu'après l'expiration du cache (1 h).
    """
    cache_analyseurs.oublier(projet.pk)


def _analyseur_ou_perdu(request, projet: Projet):
    """Analyseur du projet, ou None avec un message si le fichier a disparu.

    Un projet peut survivre à son fichier (purge des `media/`, restauration
    partielle d'une base) : plutôt qu'une erreur 500, l'utilisateur doit
    comprendre ce qui s'est passé et pouvoir réimporter.
    """
    try:
        return _analyseur(projet)
    except FichierPerdu as exc:
        messages.error(
            request,
            f"{exc} Réimporte un fichier pour retrouver cette analyse.",
        )
        return None


def _projet_utilisateur(request, pk) -> Projet | None:
    """Projet appartenant à l'utilisateur, ou None (id invalide / non autorisé)."""
    try:
        return Projet.objects.get(pk=pk, proprietaire=request.user)
    except (Projet.DoesNotExist, ValueError, TypeError):
        return None


def _enregistrer_indicateurs(projet: Projet, analyseur: DataAnalyzer) -> None:
    """Persiste les KPIs principaux sur la fiche du projet (pour la liste)."""
    kpis = analyseur.kpis()
    projet.nb_lignes = kpis["nb_ventes"]
    projet.ca_total = kpis["ca_total"]
    projet.save(update_fields=["nb_lignes", "ca_total"])


def _erreur(request, message: str):
    """Rend la page d'accueil avec le message destiné à l'utilisateur."""
    return render(request, "core/index.html", {
        "erreur": message,
        "taille_max_mo": settings.TAILLE_MAX_UPLOAD // (1024 * 1024),
    })


def _limite_debit(request, message: str):
    """Réponse 429 pour une action refusée à cause de la limite de débit."""
    return render(
        request,
        "core/trop_de_requetes.html",
        {"message": message},
        status=429,
    )
