"""
API JSON consommées par le dashboard (Chart.js) et par la page Angular.

Ces routes renvoient du JSON et non des gabarits : une erreur y est un
message structuré avec un code HTTP approprié, jamais une page HTML.
"""

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse

from .services import FichierPerdu, _analyseur, _projet_utilisateur


def _fichier_perdu(exc: FichierPerdu) -> JsonResponse:
    """Réponse d'API quand le projet existe mais son fichier a disparu."""
    return JsonResponse({"erreur": str(exc)}, status=404)


def sante(request):
    """Route de supervision : vérifie que l'application et la base répondent.

    Renvoie un statut HTTP honnête : 503 si la base est injoignable, sinon
    Render (ou tout autre moniteur) recevrait un 200 et ne signalerait jamais
    la panne.
    """
    try:
        with connection.cursor() as curseur:
            curseur.execute("SELECT 1")
        base = "ok"
    except Exception:  # noqa: BLE001 — on veut juste signaler l'échec
        base = "erreur"
    return JsonResponse(
        {"statut": "ok" if base == "ok" else "erreur", "base": base},
        status=503 if base == "erreur" else 200,
    )


@login_required
def api_donnees(request):
    """JSON consommé par Chart.js — prend en compte les filtres."""
    projet = _projet_utilisateur(request, request.GET.get("id"))
    if projet is None:
        return JsonResponse({"erreur": "Analyse introuvable."}, status=404)

    try:
        analyseur = _analyseur(projet)
    except FichierPerdu as exc:
        return _fichier_perdu(exc)
    filtre = analyseur.filtrer(
        categorie=request.GET.get("categorie"),
        debut=request.GET.get("debut"),
        fin=request.GET.get("fin"),
    )
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    evolution = analyseur.evolution_mensuelle(filtre)
    categories = analyseur.par_categorie(filtre)
    top = analyseur.top_produits(5, filtre)

    return JsonResponse(
        {
            "kpis": analyseur.kpis(filtre),
            "resume": analyseur.resume(filtre),
            "mois": [str(i) for i in evolution.index],
            "ca_mensuel": [round(float(v), 2) for v in evolution.values],
            "tendance": analyseur.prevoir_tendance(filtre),
            "classement": analyseur.classement_produits(5, filtre),
            "correlations": analyseur.correlations(filtre),
            "nuage": analyseur.nuage_points(filtre),
            "categories": {
                "labels": [str(i) for i in categories.index],
                "valeurs": [round(float(v), 2) for v in categories.values],
            },
            "top": {
                "labels": [str(i) for i in top.index],
                "valeurs": [round(float(v), 2) for v in top.values],
            },
            "apercu": analyseur.apercu(filtre, page=page),
            "anomalies": analyseur.detecter_anomalies(filtre),
        }
    )


@login_required
def api_comparaison(request):
    """Compare deux périodes (CA, ventes, panier moyen) avec variations en %."""
    projet = _projet_utilisateur(request, request.GET.get("id"))
    if projet is None:
        return JsonResponse({"erreur": "Analyse introuvable."}, status=404)

    try:
        analyseur = _analyseur(projet)
    except FichierPerdu as exc:
        return _fichier_perdu(exc)
    resultat = analyseur.comparer_periodes(
        p1_debut=request.GET.get("p1_debut"),
        p1_fin=request.GET.get("p1_fin"),
        p2_debut=request.GET.get("p2_debut"),
        p2_fin=request.GET.get("p2_fin"),
        categorie=request.GET.get("categorie") or None,
    )
    return JsonResponse(resultat)


@login_required
def api_projets(request):
    """JSON des analyses de l'utilisateur — consommé par l'application Angular."""
    projets = [
        {
            "id": projet.pk,
            "nom": projet.nom,
            "fichier": projet.nom_fichier,
            "lignes": projet.nb_lignes,
            "ca": str(projet.ca_total) if projet.ca_total is not None else None,
            "date": projet.date_creation.strftime("%d/%m/%Y"),
        }
        for projet in request.user.projets.all()
    ]
    return JsonResponse({"projets": projets})
