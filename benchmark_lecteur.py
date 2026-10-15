"""Mesure le gain de vitesse du lecteur CSV rapide (moteur C).

Usage :
    python benchmark_lecteur.py [nombre_de_lignes]

Le banc génère un CSV propre de N lignes, le lit avec les deux moteurs de
Pandas, puis vérifie que les deux chemins donnent exactement le même
dataframe (et la même erreur, si besoin).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyzer import DataAnalyzer  # noqa: E402


def generer_csv(chemin: Path, n: int) -> None:
    """Écrit un CSV propre et réaliste : dates, libellés, montants."""
    produits = ["Vis", "Boulon", "Rondelle", "Écrou", "Clou"]
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write("Date,Produit,Quantite,Prix,Region\n")
        for i in range(n):
            f.write(
                f"{1 + i % 28:02d}/{1 + (i % 12):02d}/2026,"
                f"{produits[i % 5]},{i % 97 + 1},{(i % 5000) / 100 + 1:.2f},"
                f"{'Tunis' if i % 2 else 'Sfax'}\n"
            )


def chronometre(fonction, *args, **kwargs):
    debut = time.perf_counter()
    resultat = fonction(*args, **kwargs)
    return resultat, time.perf_counter() - debut


def main() -> None:
    # Console Windows par défaut en cp1252 : on force UTF-8 pour les ✔ et accents.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300_000

    dossier = tempfile.mkdtemp(prefix="datavision-bench-")
    chemin = Path(dossier) / "benchmark.csv"

    print(f"Génération de {n:,} lignes…".replace(",", " "), flush=True)
    generer_csv(chemin, n)
    taille = chemin.stat().st_size / 1_048_576
    print(f"Fichier : {taille:.1f} Mo\n")

    separateur = DataAnalyzer._detecter_separateur(str(chemin), "utf-8-sig")

    # --- Lecture brute des deux moteurs Pandas -------------------------
    df_lent, t_lent = chronometre(
        pd.read_csv, chemin, sep=separateur, engine="python",
        on_bad_lines="skip", nrows=500_000,
    )
    df_rapide, t_rapide = chronometre(
        pd.read_csv, chemin, sep=separateur, engine="c",
        low_memory=False, nrows=500_000,
    )

    # --- Lecteurs du projet -------------------------------------------
    df_robuste, t_robuste = chronometre(
        DataAnalyzer._lire_csv, str(chemin), "utf-8-sig", separateur
    )
    df_c, t_c = chronometre(
        DataAnalyzer._lire_csv_rapide, str(chemin), "utf-8-sig", separateur
    )

    print("Lecture Pandas seule (hors nettoyage)")
    print(f"  moteur Python          {t_lent:7.3f} s")
    print(f"  moteur C               {t_rapide:7.3f} s")
    print(f"  gain x{t_lent / max(t_rapide, 1e-9):.1f}\n")

    print("Lecteurs DataVision (avec attrs de troncature)")
    print(f"  _lire_csv   (robuste)  {t_robuste:7.3f} s")
    print(f"  _lire_csv_rapide       {t_c:7.3f} s")
    print(f"  gain x{t_robuste / max(t_c, 1e-9):.1f}\n")

    # --- Équivalence stricte ------------------------------------------
    pd.testing.assert_frame_equal(df_lent, df_rapide)
    pd.testing.assert_frame_equal(df_robuste, df_c)
    print("✔ les deux chemins produisent exactement le même dataframe")

    # --- Fichier mal formé : le comptage doit rester exact ------------
    sale = Path(dossier) / "sale.csv"
    with open(sale, "w", encoding="utf-8") as f:
        f.write("Date,Produit,Prix\n")
        for i in range(1, 200):
            if i in (7, 50, 150):
                f.write("01/01/2026,PC,10,SUPERFLU\n")
            else:
                f.write(f"01/01/2026,PC,{i}\n")

    sep_sale, regulier = DataAnalyzer._diagnostiquer_entete(str(sale), "utf-8-sig")
    df_sale = DataAnalyzer._charger(str(sale))
    print(
        f"✔ fichier mal formé : échantillon régulier={regulier}, "
        f"{df_sale.attrs['lignes_ignorees']} lignes ignorées sur 3 attendues"
    )
    assert df_sale.attrs["lignes_ignorees"] == 3, "comptage inexact"

    os.remove(chemin)
    os.remove(sale)
    os.rmdir(dossier)


if __name__ == "__main__":
    main()
