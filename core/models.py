"""
Modèles de données de DataVision.

Un « Projet » = une analyse sauvegardée : le fichier importé (CSV/Excel)
et les indicateurs calculés au moment de l'import.
"""

import os

from django.conf import settings
from django.db import models


class Projet(models.Model):
    """Une analyse enregistrée et rattachée à un utilisateur."""

    nom = models.CharField("nom de l'analyse", max_length=200)
    proprietaire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projets",
        verbose_name="propriétaire",
    )
    fichier = models.FileField("fichier importé", upload_to="uploads/%Y/%m/")
    date_creation = models.DateTimeField("créé le", auto_now_add=True)
    nb_lignes = models.PositiveIntegerField("nombre de lignes", default=0)
    ca_total = models.DecimalField(
        "chiffre d'affaires", max_digits=14, decimal_places=2, null=True, blank=True
    )
    mapping_colonnes = models.JSONField(
        "correspondance des colonnes",
        null=True,
        blank=True,
        help_text="Choix manuel de l'utilisateur si la détection auto s'est trompée.",
    )
    note_analyste = models.TextField(
        "note de l'analyste",
        blank=True,
        default="",
        help_text="Lecture éditoriale de l'analyse, affichée sur le dashboard et dans le PDF.",
    )
    source_donnees = models.CharField(
        "source des données",
        max_length=300,
        blank=True,
        default="",
        help_text="Provenance des données, citée comme en journalisme.",
    )

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "analyse"
        verbose_name_plural = "analyses"

    def __str__(self) -> str:
        return self.nom

    @property
    def nom_fichier(self) -> str:
        """Nom d'origine du fichier, sans le préfixe de stockage."""
        return os.path.basename(self.fichier.name)

    @property
    def fichier_existe(self) -> bool:
        """Vrai si le fichier importé est encore présent sur le disque.

        Une purge des `media/` peut laisser des projets orphelins : on le
        signale sur la liste pour proposer un réimport, au lieu d'attendre
        une erreur au moment d'ouvrir le dashboard.
        """
        if not self.fichier.name:
            return False
        try:
            return self.fichier.storage.exists(self.fichier.name)
        except (NotImplementedError, ValueError, OSError):
            # Stockage distant indisponible ou nom illisible : on préfère
            # ne pas afficher « perdu » à tort.
            return True
