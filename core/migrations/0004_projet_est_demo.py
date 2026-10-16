"""Marqueur `est_demo` : la vue /demo réutilise son analyse au lieu d'un doublon.

Avant, chaque clic sur « Essayer la démo » empilait une copie du jeu de
ventes. Le marqueur survit à un renommage (le champ `nom` est éditable par
l'utilisateur) et les analyses déjà créées sont reconnues par leur nom
exact à la date de cette migration.
"""

from django.conf import settings
from django.db import migrations, models


def marquer_projets_demo(apps, schema_editor):
    """Reconnaît les analyses déjà créées par /demo (nom exact de l'époque)."""
    Projet = apps.get_model("core", "Projet")
    Projet.objects.filter(nom="Démo — Ventes 2026").update(est_demo=True)


def demarquer_projets_demo(apps, schema_editor):
    """Retour arrière : le champ disparaît avec la migration."""
    Projet = apps.get_model("core", "Projet")
    Projet.objects.filter(est_demo=True).update(est_demo=False)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0003_projet_note_analyste_projet_source_donnees"),
    ]

    operations = [
        migrations.AddField(
            model_name="projet",
            name="est_demo",
            field=models.BooleanField(
                default=False,
                help_text="Marque l'analyse créée par /demo : la vue la réutilise au lieu d'un doublon.",
                verbose_name="jeu de démonstration",
            ),
        ),
        migrations.RunPython(marquer_projets_demo, demarquer_projets_demo),
    ]
