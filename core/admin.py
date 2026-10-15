"""Administration Django — enregistrement des modèles."""

from django.contrib import admin

from .models import Projet


@admin.register(Projet)
class ProjetAdmin(admin.ModelAdmin):
    list_display = ("nom", "proprietaire", "nb_lignes", "ca_total", "date_creation")
    list_filter = ("date_creation",)
    search_fields = ("nom", "proprietaire__username")
    readonly_fields = ("date_creation",)
