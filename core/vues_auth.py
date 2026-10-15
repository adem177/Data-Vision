"""
Vues d'authentification : inscription, connexion (avec anti-force-brute),
réinitialisation du mot de passe (vues Django, dans `core.urls`).
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.shortcuts import render, redirect

from . import cache as cache_analyseurs
from .formulaires import FormulaireInscription

# --- Limitation des tentatives de connexion (anti force brute) ---
TENTATIVES_MAX = 5          # nombre d'échecs autorisés
FENETRE_MINUTES = 15        # puis blocage pendant 15 minutes


def _cle_tentatives(ip: str, utilisateur: str) -> str:
    return f"tentatives-connexion:{ip}:{utilisateur}"


def _connexion_bloquee(ip: str, utilisateur: str) -> bool:
    return cache.get(_cle_tentatives(ip, utilisateur), 0) >= TENTATIVES_MAX


def _enregistrer_echec(ip: str, utilisateur: str) -> int:
    """Incrémente le compteur d'échecs et renvoie le nombre total."""
    cle = _cle_tentatives(ip, utilisateur)
    reste = cache.get(cle, 0) + 1
    # La fenêtre de blocage démarre au premier échec et dure 15 minutes.
    cache.set(cle, reste, FENETRE_MINUTES * 60)
    return reste


def _reinitialiser_tentatives(ip: str, utilisateur: str) -> None:
    cache.delete(_cle_tentatives(ip, utilisateur))


class VueConnexion(LoginView):
    """Connexion avec limitation du nombre de tentatives échouées."""

    template_name = "core/connexion.html"

    def get_context_data(self, **kwargs):
        """Affiche (ou masque) les identifiants du compte de démonstration."""
        context = super().get_context_data(**kwargs)
        context["demo_visible"] = settings.DEMO_LOGIN
        context["demo_utilisateur"] = settings.DEMO_UTILISATEUR
        context["demo_mdp"] = settings.DEMO_MOT_DE_PASSE
        # Le bouton Google n'apparaît que si les clés OAuth sont configurées.
        context["google_actif"] = bool(
            settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET
        )
        return context

    def post(self, request, *args, **kwargs):
        ip = self.request.META.get("REMOTE_ADDR", "inconnue")
        utilisateur = (request.POST.get("username") or "").strip()
        if utilisateur and _connexion_bloquee(ip, utilisateur):
            messages.error(
                request,
                f"Compte bloqué après trop de tentatives échouées. "
                f"Réessaie dans {FENETRE_MINUTES} minutes.",
            )
            return self.render_to_response(self.get_context_data())
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """Connexion réussie : on remet le compteur à zéro."""
        _reinitialiser_tentatives(
            self.request.META.get("REMOTE_ADDR", "inconnue"),
            form.cleaned_data.get("username", ""),
        )
        reponse = super().form_valid(form)
        # Case « Se souvenir de moi » : cochée, la session dure SESSION_COOKIE_AGE ;
        # sinon elle expire à la fermeture du navigateur (set_expiry(0)).
        if self.request.POST.get("remember"):
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        else:
            self.request.session.set_expiry(0)
        return reponse

    def form_invalid(self, form):
        """Échec : on compte la tentative et on prévient l'utilisateur."""
        ip = self.request.META.get("REMOTE_ADDR", "inconnue")
        utilisateur = (self.request.POST.get("username") or "").strip()
        if utilisateur:
            reste = _enregistrer_echec(ip, utilisateur)
            if reste >= TENTATIVES_MAX:
                messages.error(
                    self.request,
                    f"Compte bloqué pendant {FENETRE_MINUTES} minutes "
                    "après trop de tentatives échouées.",
                )
            else:
                messages.error(
                    self.request,
                    f"Identifiants incorrects. Tentative(s) restante(s) : "
                    f"{TENTATIVES_MAX - reste}.",
                )
        return super().form_invalid(form)


def inscription(request):
    """Création d'un compte puis connexion automatique."""
    if request.user.is_authenticated:
        return redirect("core:projets")
    if request.method == "POST":
        formulaire = FormulaireInscription(request.POST)
        if formulaire.is_valid():
            utilisateur = formulaire.save()
            # Plusieurs backends sont déclarés (Django + allauth) : on précise
            # celui qui gère les comptes créés ici.
            login(request, utilisateur, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, f"Bienvenue {utilisateur.username} ! Ton compte est prêt.")
            return redirect("core:projets")
    else:
        formulaire = FormulaireInscription()
    return render(
        request,
        "core/inscription.html",
        {
            "form": formulaire,
            "google_actif": bool(
                settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET
            ),
        },
    )


@login_required
def supprimer_compte(request):
    """Suppression définitive du compte, confirmée par le mot de passe.

    L'objet utilisateur porte les analyses en cascade, mais **pas** les
    fichiers sur le disque : on les retire à la main avant, sinon la
    suppression du compte laisse les CSV orphelins dans `media/uploads/`.
    """
    if request.method != "POST":
        return redirect("core:projets")

    mdp = request.POST.get("mot_de_passe") or ""
    if not request.user.check_password(mdp):
        messages.error(
            request,
            "Mot de passe incorrect : ton compte n'a pas été supprimé.",
        )
        return redirect("core:projets")

    utilisateur = request.user
    for projet in utilisateur.projets.all():
        cache_analyseurs.oublier(projet.pk)
        try:
            projet.fichier.delete(save=False)
        except OSError:
            pass  # fichier déjà perdu : on supprime quand même le compte

    # La session doit être fermée AVANT la destruction de l'utilisateur,
    # sinon Django tente de la sauvegarder sur une ligne qui n'existe plus.
    logout(request)
    utilisateur.delete()

    return render(request, "core/compte_supprime.html")
