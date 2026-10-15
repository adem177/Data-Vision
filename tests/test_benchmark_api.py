"""Banc de mesure de l'API (benchmark_api.py).

Le banc fournit les chiffres annoncés dans le README : il doit donc rester
exécutable, correct — et sans effet de bord, notamment sur le réglage
partagé `TAILLE_MEMO`.
"""

from analyzer import DataAnalyzer
from benchmark_api import NAVIGATION, appel_api, mesurer, session


def test_mesurer_renvoie_des_durees_coherentes():
    resultats = mesurer(2_000)

    assert resultats["nb_lignes"] == 2_000
    assert resultats["appels_api"] == 1 + len(NAVIGATION)
    assert resultats["avec_memo"] > 0
    assert resultats["sans_memo"] > 0
    assert resultats["gain"] > 0
    assert resultats["taille_memo"] == DataAnalyzer.TAILLE_MEMO


def test_la_memoisation_ne_change_rien_aux_chiffres():
    """`mesurer` lève une AssertionError si les KPI divergent : sinon, OK."""
    mesurer(1_000)


def test_la_taille_de_memo_est_restaurée_apres_mesure():
    """Le banc modifie TAILLE_MEMO en cours de route : il doit le rendre."""
    avant = DataAnalyzer.TAILLE_MEMO

    mesurer(500)

    assert DataAnalyzer.TAILLE_MEMO == avant


def test_session_rejoue_tous_les_appels_de_l_api():
    """La séquence doit couvrir l'intégralité de `/api/donnees`."""
    appeles = []

    class Suiveur:
        """Analyses factice : on enregistre juste les noms d'appels."""

        def filtrer(self, **kwargs):
            appeles.append("filtrer")
            return None

        def __getattr__(self, nom):
            def methode(*args, **kwargs):
                appeles.append(nom)
            return methode

    session(Suiveur())

    for attendu in (
        "filtrer",
        "evolution_mensuelle",
        "par_categorie",
        "top_produits",
        "kpis",
        "resume",
        "prevoir_tendance",
        "classement_produits",
        "correlations",
        "nuage_points",
        "apercu",
        "detecter_anomalies",
    ):
        assert attendu in appeles, attendu

    # 1 chargement initial + la navigation complète.
    assert appeles.count("filtrer") == 1 + len(NAVIGATION)


def test_appel_api_accepte_les_filtres():
    """Le rejoué doit suivre la même signature que la vue (filtres + page)."""
    class Suiveur:
        def filtrer(self, **kwargs):
            return None

        def __getattr__(self, nom):
            return lambda *args, **kwargs: None

    appel_api(Suiveur(), categorie="Vis", debut="01/01/2026", page=3)
