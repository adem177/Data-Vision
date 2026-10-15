"""
Vues de l'espace analyses : import, dashboard, liste, réglage des colonnes,
export et rapport PDF.

Chaque utilisateur ne voit que ses propres analyses : toutes les vues
passent par `_projet_utilisateur()`, qui refuse un projet d'un autre compte.
"""

import os
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from . import throttle
from .models import Projet
from .rapport import generer_rapport
from .services import (
    EXTENSIONS_VALIDES,
    _analyseur,
    _analyseur_ou_perdu,
    _enregistrer_indicateurs,
    _erreur,
    _limite_debit,
    _projet_utilisateur,
    oublier_analyseur,
)

# Tri proposé dans « Mes analyses » : clé d'URL -> champ de tri.
TRIS_VALIDES = {
    "recent": "-date_creation",
    "ancien": "date_creation",
    "nom": "nom",
    "ca_desc": "-ca_total",
    "ca_asc": "ca_total",
}

# Analyses affichées par page : au-delà, la liste devient interminable et
# chaque carte coûte du rendu — l'utilisateur comme le serveur y gagnent.
PAR_PAGE = 30


# ----------------------------------------------------------------------
# Accueil et import
# ----------------------------------------------------------------------

def index(request):
    """Page d'accueil : import si connecté, invitation à s'inscrire sinon."""
    return render(request, "core/index.html", {
        "erreur": None,
        "taille_max_mo": settings.TAILLE_MAX_UPLOAD // (1024 * 1024),
    })


@login_required
def page_angular(request):
    """Preuve de concept : hébergée par Django, rendue côté client par Angular."""
    return render(request, "core/angular.html")


@login_required
def upload(request):
    """Réception du fichier CSV/Excel → création d'un projet sauvegardé."""
    if request.method != "POST":
        return redirect("core:index")

    # Un compte ne doit pas pouvoir monter 100 Mo à la chaîne.
    if not throttle.autoriser("upload", request.user):
        return _erreur(request, throttle.message_limite("upload"))

    fichier = request.FILES.get("fichier")
    if fichier is None:
        return _erreur(request, "Aucun fichier sélectionné.")

    extension = os.path.splitext(fichier.name)[1].lower()
    if extension not in EXTENSIONS_VALIDES:
        return _erreur(
            request,
            f"Format « {extension} » non supporté. Utilise un fichier .csv ou .xlsx.",
        )

    # Phase D : on refuse un fichier trop volumineux avant de l'enregistrer.
    taille = fichier.size or 0
    limite = settings.TAILLE_MAX_UPLOAD
    if taille > limite:
        return _erreur(
            request,
            f"Fichier trop volumineux ({taille // (1024 * 1024)} Mo). "
            f"Maximum autorisé : {limite // (1024 * 1024)} Mo.",
        )

    projet = Projet(
        nom=os.path.splitext(fichier.name)[0][:200],
        proprietaire=request.user,
        fichier=fichier,
    )
    try:
        projet.save()
        analyseur = _analyseur(projet)
    except Exception as exc:  # noqa: BLE001 — message clair pour l'utilisateur
        if projet.pk:
            # Un save avorté n'a pas de clé : rien à vider dans ce cas.
            oublier_analyseur(projet)
            projet.fichier.delete(save=False)
            projet.delete()
        return _erreur(request, f"Impossible de lire le fichier : {exc}")

    if analyseur.df.empty:
        oublier_analyseur(projet)
        projet.fichier.delete(save=False)
        projet.delete()
        return _erreur(request, "Le fichier ne contient aucune ligne exploitable.")

    _enregistrer_indicateurs(projet, analyseur)
    return redirect("core:dashboard", pk=projet.pk)


@login_required
def demo(request):
    """Copie le jeu de démonstration dans les projets de l'utilisateur."""
    source = settings.BASE_DIR / "data" / "sample_sales.csv"
    if not source.exists():
        return _erreur(
            request,
            "Jeu de démonstration absent. Lance d'abord : python data_generator.py",
        )

    projet = Projet(nom="Démo — Ventes 2026", proprietaire=request.user)
    nom_stockage = f"{uuid.uuid4().hex[:8]}_sample_sales.csv"
    with open(source, "rb") as flux:
        projet.fichier.save(nom_stockage, flux, save=False)

    try:
        projet.save()
        analyseur = _analyseur(projet)
    except Exception as exc:  # noqa: BLE001 — jeu démo corrompu : on nettoie
        if projet.pk:
            oublier_analyseur(projet)
            projet.fichier.delete(save=False)
            projet.delete()
        return _erreur(request, f"Impossible de lire le jeu de démonstration : {exc}")

    _enregistrer_indicateurs(projet, analyseur)
    return redirect("core:dashboard", pk=projet.pk)


# ----------------------------------------------------------------------
# Projets sauvegardés
# ----------------------------------------------------------------------

@login_required
def mes_projets(request):
    """Liste des analyses de l'utilisateur : recherche, tri et pagination.

    Trois valeurs de contexte coexistent volontairement :
    - `projets` : le queryset filtré/trié complet (ce que compte la recherche) ;
    - `page`    : la tranche de 30 analyses à afficher ;
    - `total`   : le nombre de résultats, identique quelle que soit la page.
    """
    projets = request.user.projets.all()

    recherche = request.GET.get("q", "").strip()
    if recherche:
        # `nom_fichier` est une propriété Python, pas un champ de modèle :
        # on cherche donc dans le chemin stocké, qui contient le nom d'origine.
        projets = projets.filter(
            Q(nom__icontains=recherche) | Q(fichier__icontains=recherche)
        )

    tri = request.GET.get("tri", "recent")
    if tri not in TRIS_VALIDES:
        tri = "recent"
    projets = projets.order_by(TRIS_VALIDES[tri])

    # `get_page` avale les valeurs absurdes d'URL : `?page=abc` retombe sur
    # la première page, `?page=999` sur la dernière — jamais d'erreur 500.
    page = Paginator(projets, PAR_PAGE).get_page(request.GET.get("page"))

    return render(request, "core/projets.html", {
        "projets": projets,
        "page": page,
        "total": page.paginator.count,
        "recherche": recherche,
        "tri": tri,
    })


@login_required
def supprimer_projet(request, pk: int):
    """Supprime une analyse (et son fichier) — POST uniquement."""
    projet = get_object_or_404(Projet, pk=pk, proprietaire=request.user)
    if request.method == "POST":
        oublier_analyseur(projet)
        projet.fichier.delete(save=False)
        projet.delete()
        messages.success(request, f"Analyse « {projet.nom} » supprimée.")
    return redirect("core:projets")


@login_required
def renommer_projet(request, pk: int):
    """Renomme une analyse — le fichier importé, lui, n'est pas touché."""
    projet = get_object_or_404(Projet, pk=pk, proprietaire=request.user)
    if request.method != "POST":
        return redirect("core:projets")

    nom = (request.POST.get("nom") or "").strip()
    if not nom:
        messages.error(request, "Le nom de l'analyse ne peut pas être vide.")
    elif len(nom) > 200:
        messages.error(request, "Nom trop long : 200 caractères maximum.")
    else:
        projet.nom = nom
        projet.save(update_fields=["nom"])
        messages.success(request, f"Analyse renommée en « {nom} ».")
    return redirect("core:projets")


@login_required
def modifier_note(request, pk: int):
    """Enregistre la note de l'analyste et la source des données.

    Réflexe éditorial emprunté à Datawrapper : une visualisation sans note
    ni source force le lecteur à deviner ce qu'il regarde et d'où viennent
    les chiffres. Les deux champs sont coupés net (1000 et 300 car.) pour
    qu'un formulaire reste un formulaire, pas un dépôt de texte.
    """
    projet = get_object_or_404(Projet, pk=pk, proprietaire=request.user)
    if request.method != "POST":
        return redirect("core:dashboard", pk=projet.pk)

    note = (request.POST.get("note") or "").strip()
    source = (request.POST.get("source") or "").strip()
    if len(note) > 1000:
        messages.error(request, "Note trop longue : 1000 caractères maximum.")
    elif len(source) > 300:
        messages.error(request, "Source trop longue : 300 caractères maximum.")
    else:
        projet.note_analyste = note
        projet.source_donnees = source
        projet.save(update_fields=["note_analyste", "source_donnees"])
        messages.success(request, "Note de l'analyste enregistrée.")
    return redirect("core:dashboard", pk=projet.pk)


@login_required
def remplacer_fichier(request, pk: int):
    """Remplace le fichier d'une analyse (fichier perdu, ou données mises à jour).

    Le projet garde son identifiant, ses indicateurs et son réglage des
    colonnes : seuls les données changent. L'ancien fichier n'est retiré du
    disque qu'une fois le nouveau confirmé lisible.
    """
    projet = get_object_or_404(Projet, pk=pk, proprietaire=request.user)
    if request.method != "POST":
        return redirect("core:projets")

    # Même garde que l'import : c'est la même opération coûteuse côté serveur.
    if not throttle.autoriser("upload", request.user):
        return _erreur(request, throttle.message_limite("upload"))

    fichier = request.FILES.get("fichier")
    if fichier is None:
        messages.error(request, "Aucun fichier sélectionné.")
        return redirect("core:projets")

    extension = os.path.splitext(fichier.name)[1].lower()
    if extension not in EXTENSIONS_VALIDES:
        messages.error(
            request,
            f"Format « {extension} » non supporté. Utilise un fichier .csv ou .xlsx.",
        )
        return redirect("core:projets")

    taille = fichier.size or 0
    if taille > settings.TAILLE_MAX_UPLOAD:
        messages.error(
            request,
            f"Fichier trop volumineux ({taille // (1024 * 1024)} Mo). "
            f"Maximum autorisé : {settings.TAILLE_MAX_UPLOAD // (1024 * 1024)} Mo.",
        )
        return redirect("core:projets")

    ancien_nom = projet.fichier.name
    projet.fichier = fichier  # le nouveau fichier s'enregistre au `save()`
    try:
        projet.save()
        oublier_analyseur(projet)  # l'ancien analyseur est périmé
        analyseur = _analyseur(projet)
    except Exception as exc:  # noqa: BLE001 — on retombe sur l'ancien fichier
        _retablir_ancien_fichier(projet, ancien_nom)
        messages.error(request, f"Impossible de lire le fichier : {exc}")
        return redirect("core:projets")

    if analyseur.df.empty:
        _retablir_ancien_fichier(projet, ancien_nom)
        messages.error(
            request,
            "Le fichier ne contient aucune ligne exploitable : "
            "l'analyse précédente est conservée.",
        )
        return redirect("core:projets")

    _enregistrer_indicateurs(projet, analyseur)
    messages.success(request, f"Fichier remplacé pour l'analyse « {projet.nom} ».")
    return redirect("core:dashboard", pk=projet.pk)


def _retablir_ancien_fichier(projet: Projet, ancien_nom: str) -> None:
    """Remet l'ancien fichier en place après un remplacement raté.

    Le fichier refusé est retiré du stockage : il ne doit pas rester orphelin
    sur le disque, et l'analyse continue de fonctionner avec ses données.
    """
    nouveau_nom = projet.fichier.name
    projet.fichier.name = ancien_nom
    projet.save(update_fields=["fichier"])
    if nouveau_nom and nouveau_nom != ancien_nom:
        try:
            projet.fichier.storage.delete(nouveau_nom)
        except OSError:
            pass  # une orpheline sur le disque ne vaut pas une erreur 500
    oublier_analyseur(projet)


@login_required
def regler_colonnes(request, pk: int):
    """Choix manuel de la colonne pour chaque rôle (si la détection auto échoue)."""
    projet = _projet_utilisateur(request, pk)
    if projet is None:
        return redirect("core:projets")

    analyseur = _analyseur_ou_perdu(request, projet)
    if analyseur is None:
        return redirect("core:projets")

    if request.method == "POST":
        mapping = {
            role: request.POST.get(role, "").strip()
            for role in analyseur.ROLES_AFFICHAGES
        }
        mapping = {r: c for r, c in mapping.items() if c}
        projet.mapping_colonnes = mapping
        projet.save(update_fields=["mapping_colonnes"])
        analyseur.appliquer_mapping(mapping)
        _enregistrer_indicateurs(projet, analyseur)
        # Le cache stocke une copie sérialisée de l'analyseur : sans cet
        # oubli, le dashboard continuerait d'afficher l'ancien mapping
        # jusqu'à l'expiration du cache (1 heure).
        oublier_analyseur(projet)
        messages.success(request, "Correspondance des colonnes mise à jour.")
        return redirect("core:dashboard", pk=projet.pk)

    return render(
        request,
        "core/colonnes.html",
        {"projet": projet, "options": analyseur.options_mapping()},
    )


# ----------------------------------------------------------------------
# Dashboard, export et rapport
# ----------------------------------------------------------------------

@login_required
def dashboard(request, pk: int):
    """Tableau de bord : KPIs initiaux + structure des graphiques."""
    projet = _projet_utilisateur(request, pk)
    if projet is None:
        return redirect("core:projets")
    analyseur = _analyseur_ou_perdu(request, projet)
    if analyseur is None:
        return redirect("core:projets")
    return render(
        request,
        "core/dashboard.html",
        {
            "projet": projet,
            "kpis": analyseur.kpis(),
            "options": analyseur.options_filtres(),
            "nom_fichier": projet.nom_fichier,
        },
    )


@login_required
def rapport_pdf(request, pk: int):
    """Génère et télécharge le rapport PDF d'une analyse."""
    projet = _projet_utilisateur(request, pk)
    if projet is None:
        return redirect("core:projets")

    analyseur = _analyseur_ou_perdu(request, projet)
    if analyseur is None:
        return redirect("core:projets")
    filtre = analyseur.filtrer(
        categorie=request.GET.get("categorie"),
        debut=request.GET.get("debut"),
        fin=request.GET.get("fin"),
    )
    contenu = generer_rapport(
        analyseur, filtre, projet.nom, projet.nom_fichier,
        note=projet.note_analyste, source=projet.source_donnees,
    )

    reponse = HttpResponse(contenu.getvalue(), content_type="application/pdf")
    reponse["Content-Disposition"] = (
        f'attachment; filename="rapport_{projet.pk}.pdf"'
    )
    return reponse


@login_required
def export(request):
    """Télécharge les données (filtrées) en CSV ou Excel."""
    projet = _projet_utilisateur(request, request.GET.get("id"))
    if projet is None:
        return redirect("core:projets")

    # Chaque export relit et recalcule le fichier : on limite la cadence.
    if not throttle.autoriser("export", request.user):
        return _limite_debit(request, throttle.message_limite("export"))

    analyseur = _analyseur_ou_perdu(request, projet)
    if analyseur is None:
        return redirect("core:projets")
    fmt = "excel" if request.GET.get("format") == "excel" else "csv"
    filtre = analyseur.filtrer(
        categorie=request.GET.get("categorie"),
        debut=request.GET.get("debut"),
        fin=request.GET.get("fin"),
    )
    contenu = analyseur.export(filtre, fmt=fmt).getvalue()

    if fmt == "excel":
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        nom = "datavision_export.xlsx"
    else:
        mimetype = "text/csv"
        nom = "datavision_export.csv"

    reponse = HttpResponse(contenu, content_type=mimetype)
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse
