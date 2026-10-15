"""Mesure le gain de la mémoïsation de l'API du tableau de bord.

Usage :
    python benchmark_api.py [nombre_de_lignes]

`/api/donnees` recalcule à chaque appel l'évolution, les catégories, le
classement, les corrélations, la dispersion (nuage de points) et les
anomalies. Le banc génère un CSV de N
lignes, puis rejoue la séquence réelle du tableau de bord — un chargement
initial, puis la navigation d'un visiteur (filtres, pages, retours) — avec
la mémoïsation activée (`TAILLE_MEMO = 32`) puis désactivée
(`TAILLE_MEMO = 0`). La différence est le gain apporté par la mémoïsation.

Les chiffres KPI des deux configurations sont comparés à la fin : la
mémoïsation ne doit jamais changer un résultat, seulement l'accélérer.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyzer import DataAnalyzer  # noqa: E402
from benchmark_lecteur import chronometre, generer_csv  # noqa: E402

# Ce que fait un visiteur après le chargement initial de la page : filtre par
# catégorie, change de page, change de catégorie, revient à l'ensemble, puis
# borne la période. Chaque étape est un appel complet à `/api/donnees`.
NAVIGATION = [
    {"categorie": "Vis"},
    {"categorie": "Vis", "page": 2},
    {"categorie": "Boulon"},
    {},
    {"debut": "01/01/2026", "fin": "30/06/2026"},
]


def appel_api(analyseur: DataAnalyzer, page: int = 1, **filtre) -> None:
    """Rejoue un appel à `/api/donnees` (hors HTTP, hors rendu JSON)."""
    filtre_df = analyseur.filtrer(**filtre)
    analyseur.evolution_mensuelle(filtre_df)
    analyseur.par_categorie(filtre_df)
    analyseur.top_produits(5, filtre_df)
    analyseur.kpis(filtre_df)
    analyseur.resume(filtre_df)
    analyseur.prevoir_tendance(filtre_df)
    analyseur.classement_produits(5, filtre_df)
    analyseur.correlations(filtre_df)
    analyseur.nuage_points(filtre_df)
    analyseur.apercu(filtre_df, page=page)
    analyseur.detecter_anomalies(filtre_df)


def session(analyseur: DataAnalyzer) -> None:
    """Un chargement de tableau de bord, puis la navigation d'un visiteur."""
    appel_api(analyseur)
    for etape in NAVIGATION:
        appel_api(analyseur, **etape)


def mesurer(nb_lignes: int) -> dict:
    """Durées de la séquence complète, avec puis sans mémoïsation.

    `DataAnalyzer.TAILLE_MEMO` est un réglage partagé par tout le processus :
    le banc le remet dans son état d'origine en quittant, pour ne pas fausser
    ce qui tourne ensuite (les tests, notamment).
    """
    taille_initiale = DataAnalyzer.TAILLE_MEMO
    dossier = Path(tempfile.mkdtemp(prefix="datavision-bench-api-"))
    try:
        chemin = dossier / "api.csv"
        generer_csv(chemin, nb_lignes)

        # Échauffement : le premier chargement remplit le cache du système
        # de fichiers, et fausserait la première mesure.
        DataAnalyzer.TAILLE_MEMO = taille_initiale
        DataAnalyzer(str(chemin))

        durees: dict[str, float] = {}
        kpis: dict[str, dict] = {}
        for libelle, taille_memo in (("avec_memo", taille_initiale), ("sans_memo", 0)):
            DataAnalyzer.TAILLE_MEMO = taille_memo
            analyseur, durees[f"chargement_{libelle}"] = chronometre(
                DataAnalyzer, str(chemin)
            )
            _, durees[libelle] = chronometre(session, analyseur)
            kpis[libelle] = analyseur.kpis()

        if kpis["avec_memo"] != kpis["sans_memo"]:
            raise AssertionError(
                "la mémoïsation change les chiffres du tableau de bord !"
            )

        return {
            "nb_lignes": nb_lignes,
            "taille_mo": chemin.stat().st_size / 1_048_576,
            "appels_api": 1 + len(NAVIGATION),
            "taille_memo": taille_initiale,
            "gain": durees["sans_memo"] / max(durees["avec_memo"], 1e-9),
            **durees,
        }
    finally:
        DataAnalyzer.TAILLE_MEMO = taille_initiale
        shutil.rmtree(dossier, ignore_errors=True)


def main() -> None:
    # Console Windows par défaut en cp1252 : on force UTF-8 pour les accents.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    nb_lignes = int(sys.argv[1]) if len(sys.argv) > 1 else 300_000

    print(f"Génération de {nb_lignes:,} lignes…".replace(",", " "), flush=True)
    r = mesurer(nb_lignes)

    print(
        f"Fichier : {r['taille_mo']:.1f} Mo — "
        f"{r['appels_api']} appels à /api/donnees rejoués\n"
    )
    print(f"Chargement de l'analyseur (hors mémoïsation)  {r['chargement_sans_memo']:7.2f} s")
    print("Séquence complète du tableau de bord")
    print(f"  avec mémoïsation (TAILLE_MEMO={r['taille_memo']:>2})       {r['avec_memo']:7.2f} s")
    print(f"  sans mémoïsation (TAILLE_MEMO= 0)        {r['sans_memo']:7.2f} s")
    print(f"  gain : x{r['gain']:.1f}")
    print("\n✔ les chiffres KPI sont identiques dans les deux cas")


if __name__ == "__main__":
    main()
