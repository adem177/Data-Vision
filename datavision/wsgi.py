"""Point d'entrée WSGI pour le déploiement (gunicorn, serveur Apache...)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datavision.settings")

application = get_wsgi_application()
