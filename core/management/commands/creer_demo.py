"""Commande : crée le compte de démonstration pré-rempli de DataVision.

Permet à un jury ou à un visiteur de tester l'application sans s'inscrire.

    python manage.py creer_demo
    python manage.py creer-demo --mot-de-passe AutreMotDePasse

La commande est idempotente : relancer ne crée ni doublon de compte ni
doublon d'analyse.
"""

import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from analyzer import DataAnalyzer
from core.models import Projet

UTILISATEUR = "demo"
MOT_DE_PASSE = "DataVision2026"
NOM_PROJET = "Démo — Ventes 2026"


class Command(BaseCommand):
    help = "Crée (ou répare) le compte de démonstration avec une analyse pré-chargée."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mot-de-passe",
            default=MOT_DE_PASSE,
            help="Mot de passe du compte démo (par défaut : %(default)s).",
        )

    def handle(self, *args, **options):
        source = settings.BASE_DIR / "data" / "sample_sales.csv"
        if not source.exists():
            self.stderr.write(self.style.ERROR(
                f"Fichier de démonstration absent : {source}\n"
                "Lance d'abord : python data_generator.py"
            ))
            return

        mot_de_passe = options["mot_de_passe"]
        utilisateur, cree = User.objects.get_or_create(
            username=UTILISATEUR,
            defaults={"email": f"{UTILISATEUR}@datavision.example"},
        )
        if cree:
            utilisateur.set_password(mot_de_passe)
            utilisateur.save()
        self.stdout.write(self.style.SUCCESS(
            f"{'Compte créé' if cree else 'Compte déjà présent'} : "
            f"{UTILISATEUR} / {mot_de_passe}"
        ))

        if utilisateur.projets.exists():
            self.stdout.write("Une analyse est déjà chargée pour ce compte.")
            return

        projet = Projet(nom=NOM_PROJET, proprietaire=utilisateur)
        nom_stockage = f"{uuid.uuid4().hex[:8]}_sample_sales.csv"
        with open(source, "rb") as flux:
            projet.fichier.save(nom_stockage, flux, save=False)
        projet.save()

        analyseur = DataAnalyzer(projet.fichier.path)
        kpis = analyseur.kpis()
        projet.nb_lignes = kpis["nb_ventes"]
        projet.ca_total = kpis["ca_total"]
        projet.save(update_fields=["nb_lignes", "ca_total"])

        self.stdout.write(self.style.SUCCESS(
            f"Analyse « {NOM_PROJET} » chargée : {projet.nb_lignes} lignes."
        ))
