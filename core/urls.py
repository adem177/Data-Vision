"""URLs de l'application core."""

from django.contrib.auth.views import (
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import path, reverse_lazy

from . import views
from .formulaires import FormulaireMotDePasseOublie

app_name = "core"

urlpatterns = [
    # Public
    path("", views.index, name="index"),
    path("health", views.sante, name="sante"),

    # Authentification
    path("inscription", views.inscription, name="inscription"),
    path("connexion", views.VueConnexion.as_view(), name="connexion"),
    path("deconnexion", LogoutView.as_view(), name="deconnexion"),

    # Mot de passe oublié (vues Django, gabarits DataVision).
    path(
        "mot-de-passe-oublie",
        PasswordResetView.as_view(
            template_name="core/mot_de_passe_oublie.html",
            email_template_name="core/email_mdp_oublie.txt",
            subject_template_name="core/sujet_mdp_oublie.txt",
            # Le lien doit pointer vers l'hôte réel, pas vers « example.com ».
            form_class=FormulaireMotDePasseOublie,
            success_url=reverse_lazy("core:mot_de_passe_envoye"),
        ),
        name="mot_de_passe_oublie",
    ),
    path(
        "mot-de-passe-oublie/envoye",
        PasswordResetDoneView.as_view(template_name="core/mot_de_passe_envoye.html"),
        name="mot_de_passe_envoye",
    ),
    path(
        "mot-de-passe-oublie/<uidb64>/<token>",
        PasswordResetConfirmView.as_view(
            template_name="core/mot_de_passe_nouveau.html",
            success_url=reverse_lazy("core:mot_de_passe_modifie"),
        ),
        name="mot_de_passe_reinit",
    ),
    path(
        "mot-de-passe-oublie/modifie",
        PasswordResetCompleteView.as_view(
            template_name="core/mot_de_passe_modifie.html"
        ),
        name="mot_de_passe_modifie",
    ),

    # Analyses sauvegardées
    path("projets", views.mes_projets, name="projets"),
    path("upload", views.upload, name="upload"),
    path("demo", views.demo, name="demo"),
    path("angular", views.page_angular, name="angular"),
    path("dashboard/<int:pk>", views.dashboard, name="dashboard"),
    path("projet/<int:pk>/colonnes", views.regler_colonnes, name="colonnes"),
    path("projet/<int:pk>/rapport", views.rapport_pdf, name="rapport"),
    path("projet/<int:pk>/renommer", views.renommer_projet, name="renommer"),
    path("projet/<int:pk>/note", views.modifier_note, name="note"),
    path("projet/<int:pk>/remplacer", views.remplacer_fichier, name="remplacer"),
    path("projet/<int:pk>/supprimer", views.supprimer_projet, name="supprimer"),

    # Compte
    path("compte/supprimer", views.supprimer_compte, name="supprimer_compte"),

    # Données
    path("api/donnees", views.api_donnees, name="api_donnees"),
    path("api/comparaison", views.api_comparaison, name="api_comparaison"),
    path("api/projets", views.api_projets, name="api_projets"),
    path("export", views.export, name="export"),
]
