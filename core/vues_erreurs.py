"""
Pages d'erreur servies hors mode DEBUG.

En production (`DEBUG = False`), Django renvoie ses pages nues, en anglais.
Ces trois vues rendent les mêmes codes d'erreur dans le style du site, avec
un lien de retour — l'erreur reste une erreur, seule la présentation change.

La page 500 reste volontairement minimale : c'est la page affichée quand tout
le reste a déjà échoué, elle ne doit donc rien calculer, rien interroger, ni
afficher quoi que ce soit qui ressemblerait à une trace d'exécution.
"""

from django.shortcuts import render


def page_404(request, exception=None):
    """Adresse inconnue, analyse supprimée, lien périmé…"""
    return render(request, "core/erreur_404.html", status=404)


def page_403(request, exception=None):
    """Refus (action sur une analyse d'un autre compte, PermissionDenied)."""
    return render(request, "core/erreur_403.html", status=403)


def page_403_csrf(request, reason="", **_autres):
    """Refus CSRF — déclaré comme `CSRF_FAILURE_VIEW`.

    Django appelle cette vue avec un `reason` en anglais (« CSRF cookie not
    set. »…) : on ne l'affiche pas, l'utilisateur n'y comprendrait rien. Le
    gabarit explique lui-même les causes probables.
    """
    return render(request, "core/erreur_403.html", status=403)


def page_500(request):
    """Erreur serveur : la trace est journalisée, jamais affichée."""
    return render(request, "core/erreur_500.html", status=500)
