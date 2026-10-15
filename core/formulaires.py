"""Formulaires d'authentification de DataVision."""

from django import forms
from django.contrib.auth.forms import PasswordResetForm, UserCreationForm
from django.contrib.auth.models import User


class FormulaireInscription(UserCreationForm):
    """Inscription : nom d'utilisateur + e-mail unique + mot de passe confirmé."""

    email = forms.EmailField(
        label="Adresse e-mail",
        required=True,
        help_text="Utilisée pour te connecter (non partagée).",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_username(self):
        nom = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=nom).exists():
            raise forms.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return nom

    def clean_email(self):
        adresse = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=adresse).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return adresse


class FormulaireMotDePasseOublie(PasswordResetForm):
    """Réinitialisation dont le lien reprend le domaine réel de la requête.

    L'application « sites » (installée pour allauth) fournit par défaut le
    domaine « example.com » : le lien envoyé serait alors inutilisable, puisqu'il
    pointerait vers un hôte qui n'existe pas. On reprend donc le domaine de la
    requête courante — « 127.0.0.1:8000 » en développement, l'URL de production
    sur Render — pour que le lien reçu fonctionne réellement.
    """

    def save(self, domain_override=None, **kwargs):
        requete = kwargs.get("request")
        if domain_override is None and requete is not None:
            domain_override = requete.get_host()
        return super().save(domain_override=domain_override, **kwargs)
