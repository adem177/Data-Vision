"""
Configuration du projet DataVision (Django).
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def charger_fichier_env(chemin: Path | None = None) -> None:
    """Charge le fichier `.env` de la racine dans l'environnement (s'il existe).

    Syntaxe : `CLE=valeur` par ligne, `#` pour un commentaire. Les variables
    déjà présentes dans l'environnement priment (utile sur Render), donc on
    utilise `setdefault`. Aucune dépendance externe (pas de python-dotenv).
    """
    fichier = chemin or BASE_DIR / ".env"
    if not fichier.exists():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        os.environ.setdefault(cle.strip(), valeur.strip().strip("\"'"))


charger_fichier_env()

# Clé secrète et mode DEBUG lus dans les variables d'environnement.
# En production, DJANGO_SECRET_KEY doit OBLIGATOIREMENT être défini.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-datavision-cle-de-developpement-a-changer",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",  # requis par django-allauth (fournisseur Google)
    "core",  # application principale : import, analyse, dashboard
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# django-allauth a besoin de l'application « sites » et de cet identifiant.
SITE_ID = 1

# Connexion par mot de passe (Django) + connexion Google (django-allauth).
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ROOT_URLCONF = "datavision.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "datavision.wsgi.application"

# Base de données : SQLite en développement, PostgreSQL en production.
# Render (et la plupart des hébergeurs) fournissent une variable DATABASE_URL.
import dj_database_url

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True

# Fichiers statiques (CSS, JS) et fichiers uploadés.
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentification : redirections par défaut.
LOGIN_URL = "core:connexion"
LOGIN_REDIRECT_URL = "core:projets"
LOGOUT_REDIRECT_URL = "core:index"

# --- Connexion Google (django-allauth) ---
#
# Les clés viennent du fichier `.env` à la racine (ignoré par git) :
#   GOOGLE_CLIENT_ID=...
#   GOOGLE_CLIENT_SECRET=...
# Tant qu'elles sont absentes, le bouton « Continuer avec Google » n'est pas
# affiché sur les pages de connexion et d'inscription (voir les vues).
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": GOOGLE_CLIENT_ID,
            "secret": GOOGLE_CLIENT_SECRET,
        },
        "SCOPE": ["email", "profile"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}

# Un clic sur le bouton Google démarre immédiatement la connexion.
SOCIALACCOUNT_LOGIN_ON_GET = True
# Le compte est créé automatiquement au premier retour de Google.
SOCIALACCOUNT_AUTO_SIGNUP = True

# django-allauth ne sert ici qu'au bouton Google : le formulaire classique de
# /connexion reste celui de Django (avec limitation des tentatives). Les
# inscriptions allauth se limitent à l'adresse e-mail, sans mot de passe, pour
# qu'aucun formulaire intermédiaire n'apparaisse après la connexion Google.
ACCOUNT_LOGIN_METHODS = ["email"]
ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_EMAIL_VERIFICATION = "none"

# --- E-mails (réinitialisation du mot de passe) ---
#
# En développement, les e-mails sont simplement imprimés dans la console où
# tourne `runserver` : le lien de réinitialisation fonctionne donc sans
# configurateur. En production, renseigner EMAIL_HOST (+ utilisateur/mot de
# passe) via le `.env` ; sinon on garde la console au lieu de planter sur un
# envoi SMTP.
#
# On utilise l'API « MAILERS » de Django 6 : définir en parallèle les anciennes
# variables EMAIL_HOST / EMAIL_PORT / … lèverait une erreur de configuration
# (elles sont supprimées en Django 2028). On lit donc l'environnement dans des
# variables locales.
_hote_smtp = os.environ.get("EMAIL_HOST", "")
_port_smtp = int(os.environ.get("EMAIL_PORT", "587"))
_utilisateur_smtp = os.environ.get("EMAIL_HOST_USER", "")
_mot_de_passe_smtp = os.environ.get("EMAIL_HOST_PASSWORD", "")
_tls_smtp = os.environ.get("EMAIL_USE_TLS", "True").lower() in ("1", "true", "yes")
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "DataVision <no-reply@datavision.local>"
)

MAILERS = {
    "default": (
        {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": _hote_smtp,
                "port": _port_smtp,
                "username": _utilisateur_smtp,
                "password": _mot_de_passe_smtp,
                "use_tls": _tls_smtp,
            },
        }
        if _hote_smtp
        else {"BACKEND": "django.core.mail.backends.console.EmailBackend"}
    ),
}

if not DEBUG and not _hote_smtp:
    # Sans SMTP configuré en production, `check --deploy` remonte mail.E001
    # (« backend de développement »). On l'assume : le backend console imprime
    # le lien de réinitialisation dans les logs Render — il est donc lisible,
    # là où un refus de démarrer couperait tout le site. Renseigner EMAIL_HOST
    # réactive un envoi réel et rend ce silence sans effet.
    SILENCED_SYSTEM_CHECKS = ["mail.E001"]

# Validation des mots de passe à l'inscription.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Cache partagé.
#
# En développement, le cache local suffit. En production (plusieurs workers
# gunicorn), on définit REDIS_URL pour que tous les processus partagent le
# même cache : les analyseurs chargés et la protection force-brute.
REDIS_URL = os.environ.get("REDIS_URL", "")

if REDIS_URL:
    try:
        import django_redis  # noqa: F401 — vérifie simplement la présence

        CACHES = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": REDIS_URL,
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                    "IGNORE_EXCEPTIONS": True,  # ne pas faire tomber le site si Redis disparaît
                },
                "KEY_PREFIX": "datavision",
            }
        }
        CACHE_BACKEND = "redis"
    except ImportError:
        CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "datavision-secu",
            }
        }
        CACHE_BACKEND = "locmem"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "datavision-secu",
        }
    }
    CACHE_BACKEND = "locmem"

# --- Journalisation ---
#
# Tout part vers la console : en production, Render collecte justement ces
# sorties — il n'y a donc aucun fichier de log à faire tourner ni à purger.
# Le niveau se règle avec DATAVISION_LOG_LEVEL (DEBUG, INFO, WARNING,
# ERROR, CRITICAL) ; une valeur absurde retombe sur INFO, car la
# journalisation ne doit jamais empêcher le site de démarrer.
NIVEAUX_JOURNAL = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
NIVEAU_JOURNAL = os.environ.get("DATAVISION_LOG_LEVEL", "INFO").upper()
if NIVEAU_JOURNAL not in NIVEAUX_JOURNAL:
    NIVEAU_JOURNAL = "INFO"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "datavision": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "datavision",
        },
    },
    # Une seule sortie pour toute l'application.
    "root": {
        "handlers": ["console"],
        "level": NIVEAU_JOURNAL,
    },
    "loggers": {
        # Django : requêtes, avertissements de sécurité (CSRF, en-têtes…),
        # et les erreurs 500 journalisées avec leur trace complète.
        "django": {
            "handlers": ["console"],
            "level": NIVEAU_JOURNAL,
            "propagate": False,
        },
        # Serveur de développement : une ligne par requête servie.
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # DataVision (core.cache, core.throttle, purge de media/…) : pas de
        # handler propre, la journalisation remonte à la racine — une seule
        # trace en console, et les tests peuvent la capter.
        "core": {
            "level": NIVEAU_JOURNAL,
        },
    },
}

# --- Compte de démonstration ---
# Créé par : python manage.py creer_demo
# Les identifiants sont affichés sur la page de connexion pour permettre à un
# visiteur de tester l'application sans s'inscrire. Mettre
# DATAVISION_DEMO_LOGIN=False pour les masquer (recommandé en production).
DEMO_LOGIN = os.environ.get("DATAVISION_DEMO_LOGIN", "True").lower() in ("1", "true", "yes")
DEMO_UTILISATEUR = os.environ.get("DATAVISION_DEMO_USER", "demo")
DEMO_MOT_DE_PASSE = os.environ.get("DATAVISION_DEMO_PASSWORD", "DataVision2026")

# La protection mémoire (nombre de lignes analysées au maximum) est gérée
# par le moteur d'analyse : voir LIMITE_LIGNES dans analyzer.py, réglable
# avec la variable d'environnement DATAVISION_MAX_ROWS.
#
# De même, la mise en cache d'un analyseur refuse les fichiers trop gros
# (voir LIMITE_CACHE_LIGNES dans core/cache.py), réglable avec
# DATAVISION_CACHE_MAX_ROWS — « 0 » désactive cette limite.
#
# Taille maximale d'un fichier importé, en octets (100 Mo par défaut).
# Configurable avec DATAVISION_MAX_UPLOAD_MB.
TAILLE_MAX_UPLOAD = int(os.environ.get("DATAVISION_MAX_UPLOAD_MB", "100")) * 1024 * 1024

# --- Sécurité ---
# Empêche le navigateur de deviner le type des fichiers servis.
SECURE_CONTENT_TYPE_NOSNIFF = True
# Le navigateur ne doit pas pouvoir intégrer nos pages dans une iframe.
X_FRAME_OPTIONS = "DENY"
# Un POST sans jeton CSRF rend la page « Accès refusé » du site, en français,
# plutôt que la page nue de Django.
CSRF_FAILURE_VIEW = "core.vues_erreurs.page_403_csrf"
# La session n'est accessible qu'en JavaScript serveur (anti-XSS).
SESSION_COOKIE_HTTPONLY = True
# La session reste valide même après fermeture du navigateur.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 jours

# En production (DEBUG = False), on exige le HTTPS.
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Un an de contrainte HTTPS, sous-domaines compris et éligible au
    # préchargement HSTS : après la première visite en HTTPS, le navigateur
    # n'accepte plus jamais de requête en clair sur le domaine.
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # En prod, la clé secrète doit venir de l'environnement.
    if SECRET_KEY.startswith("django-insecure-"):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY doit être défini en production. "
            "Génère-en un avec : python -c \"from django.core.management.utils import "
            "get_random_secret_key; print(get_random_secret_key())\""
        )
