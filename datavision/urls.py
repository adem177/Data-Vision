"""URLs du projet DataVision."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # django-allauth : bouton Google (chemins /accounts/google/...).
    path("accounts/", include("allauth.urls")),
    path("", include("core.urls")),
]

# Pages d'erreur du site (uniquement hors DEBUG : en développement, Django
# affiche ses propres pages détaillées). Sans ces déclarations, une erreur
# en production afficherait la page nue de Django, en anglais.
handler404 = "core.vues_erreurs.page_404"
handler403 = "core.vues_erreurs.page_403"
handler500 = "core.vues_erreurs.page_500"

# Sert les fichiers uploadés en développement (DEBUG uniquement).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
