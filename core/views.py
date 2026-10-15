"""
DataVision — vues Django.

Chaque utilisateur s'authentifie, importe un fichier CSV/Excel qui devient
un « Projet » sauvegardé en base, puis consulte son dashboard. Le moteur
d'analyse reste dans analyzer.py (indépendant de Django).

Le code est réparti en modules thématiques ; ce fichier les ré-exporte tous
pour que `from . import views` (dans `core.urls`) continue de fonctionner
sans changer une ligne d'import.

    core.services      chargement de l'analyseur, recherche d'un projet, KPIs
    core.vues_auth     inscription, connexion, anti-force-brute
    core.vues_projets  import, dashboard, liste, export, rapport PDF
    core.vues_api      API JSON (Chart.js, Angular, supervision)
    core.vues_erreurs  pages 404 / 403 / 500 hors mode DEBUG
"""

from .services import (  # noqa: F401 — ré-exporté pour la compatibilité
    EXTENSIONS_VALIDES,
    FichierPerdu,
    _analyseur,
    _enregistrer_indicateurs,
    _erreur,
    _projet_utilisateur,
    oublier_analyseur,
)
from .vues_api import (  # noqa: F401
    api_comparaison,
    api_donnees,
    api_projets,
    sante,
)
from .vues_auth import (  # noqa: F401
    FENETRE_MINUTES,
    TENTATIVES_MAX,
    VueConnexion,
    inscription,
    supprimer_compte,
)
from .vues_projets import (  # noqa: F401
    TRIS_VALIDES,
    dashboard,
    demo,
    export,
    index,
    mes_projets,
    modifier_note,
    page_angular,
    rapport_pdf,
    regler_colonnes,
    renommer_projet,
    remplacer_fichier,
    supprimer_projet,
    upload,
)
