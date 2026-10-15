"""Tests du lecteur CSV rapide (Bloc B).

Deux points sont vérifiés :
1. le fichier régulier part sur le moteur C, cinq fois plus rapide ;
2. quel que soit le chemin emprunté, le comptage des lignes mal formées
   reste exact — c'est le contrat que la bascule de moteur ne doit pas casser.
"""

import pandas as pd
import pytest

import analyzer
from analyzer import DataAnalyzer


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

def _ecrire(chemin, lignes):
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return chemin


@pytest.fixture
def fichier_propre(tmp_path):
    """Même nombre de champs sur toutes les lignes : chemin rapide."""
    lignes = ["Date,Produit,Quantite,Prix"] + [
        f"{i:02d}/01/2026,PC,{i % 7 + 1},{100 + i}" for i in range(1, 61)
    ]
    return _ecrire(tmp_path / "propre.csv", lignes)


@pytest.fixture
def fichier_sale_tard(tmp_path):
    """Deux lignes mal formées, hors de l'échantillon de 20 lignes.

    L'en-tête paraît régulier : le lecteur rapide est tenté, échoue, et doit
    basculer sur le lecteur robuste qui compte les deux lignes.
    """
    lignes = ["Date,Produit,Quantite,Prix"]
    for i in range(1, 61):
        if i in (40, 50):
            lignes.append(f"{i:02d}/01/2026,PC,1,100,SUPERFLU,AUSSI")
        else:
            lignes.append(f"{i:02d}/01/2026,PC,{i % 7 + 1},{100 + i}")
    return _ecrire(tmp_path / "sale_tard.csv", lignes)


@pytest.fixture
def fichier_sale_tot(tmp_path):
    """Ligne mal formée dès la 5ᵉ ligne : l'échantillon est irrégulier."""
    lignes = ["Date,Produit,Quantite,Prix"]
    for i in range(1, 61):
        if i == 5:
            lignes.append(f"{i:02d}/01/2026,PC,1,100,SUPERFLU,AUSSI")
        else:
            lignes.append(f"{i:02d}/01/2026,PC,{i % 7 + 1},{100 + i}")
    return _ecrire(tmp_path / "sale_tot.csv", lignes)


@pytest.fixture
def appels(monkeypatch):
    """Enregistre quel lecteur est appelé, sans changer leur comportement."""
    trace = []
    rapide_reel = DataAnalyzer._lire_csv_rapide
    robuste_reel = DataAnalyzer._lire_csv

    def rapide(*args, **kwargs):
        trace.append("rapide")
        return rapide_reel(*args, **kwargs)

    def robuste(*args, **kwargs):
        trace.append("robuste")
        return robuste_reel(*args, **kwargs)

    monkeypatch.setattr(DataAnalyzer, "_lire_csv_rapide", rapide)
    monkeypatch.setattr(DataAnalyzer, "_lire_csv", robuste)
    return trace


# ----------------------------------------------------------------------
# Diagnostic d'en-tête
# ----------------------------------------------------------------------

def test_entete_propre_signale_un_fichier_regulier(fichier_propre):
    separateur, regulier = DataAnalyzer._diagnostiquer_entete(
        str(fichier_propre), "utf-8-sig"
    )
    assert separateur == ","
    assert regulier is True


def test_entete_avec_ligne_tardive_paraît_encore_regulier(fichier_sale_tard):
    """Les 20 premières lignes sont propres : le diagnostic reste optimiste."""
    separateur, regulier = DataAnalyzer._diagnostiquer_entete(
        str(fichier_sale_tard), "utf-8-sig"
    )
    assert separateur == ","
    assert regulier is True


def test_entete_irregulier_est_detecte(fichier_sale_tot):
    _, regulier = DataAnalyzer._diagnostiquer_entete(str(fichier_sale_tot), "utf-8-sig")
    assert regulier is False


def test_detecter_separateur_point_virgule(tmp_path):
    """Le diagnostic reste capable de choisir le bon séparateur."""
    fichier = _ecrire(
        tmp_path / "sc.csv",
        ["Date;Produit;Prix"] + [f"{i:02d}/01/2026;PC;{i}" for i in range(1, 15)],
    )
    assert DataAnalyzer._detecter_separateur(str(fichier), "utf-8-sig") == ";"


def test_fichier_inexistant_ou_vide_ne_plante_pas(tmp_path):
    """OSError ou fichier sans ligne → séparateur par défaut, pas d'exception."""
    assert DataAnalyzer._detecter_separateur(str(tmp_path / "absent.csv"), "utf-8") == ","
    vide = _ecrire(tmp_path / "vide.csv", [])
    assert DataAnalyzer._detecter_separateur(str(vide), "utf-8") == ","


# ----------------------------------------------------------------------
# Choix du chemin de lecture
# ----------------------------------------------------------------------

def test_fichier_propre_passe_par_le_moteur_rapide(fichier_propre, appels):
    df = DataAnalyzer._charger(str(fichier_propre))

    assert appels == ["rapide"], "un fichier régulier ne doit pas payer le moteur lent"
    assert len(df) == 60
    assert df.attrs["lignes_ignorees"] == 0
    assert df.attrs["tronque"] is False


def test_ligne_tardive_provoque_le_repli(fichier_sale_tard, appels):
    df = DataAnalyzer._charger(str(fichier_sale_tard))

    assert appels == ["rapide", "robuste"], "le lecteur rapide doit céder la place"
    assert len(df) == 58
    assert df.attrs["lignes_ignorees"] == 2


def test_entete_irregulier_evite_essai_inutile(fichier_sale_tot, appels):
    df = DataAnalyzer._charger(str(fichier_sale_tot))

    assert appels == ["robuste"], "savoir que l'échantillon est sale suffit à éviter" \
        " un essai voué à l'échec"
    assert len(df) == 59
    assert df.attrs["lignes_ignorees"] == 1


def test_deux_memeurs_produisent_le_meme_dataframe(fichier_propre):
    """La bascule de moteur ne doit pas changer le résultat affiché."""
    robuste = DataAnalyzer._lire_csv(str(fichier_propre), "utf-8-sig", ",")
    rapide = DataAnalyzer._lire_csv_rapide(str(fichier_propre), "utf-8-sig", ",")

    pd.testing.assert_frame_equal(robuste, rapide)
    assert list(rapide.columns) == ["Date", "Produit", "Quantite", "Prix"]


# ----------------------------------------------------------------------
# Contrats du lecteur rapide
# ----------------------------------------------------------------------

def test_lecteur_rapide_signale_zero_ligne_ignoree(fichier_propre):
    df = DataAnalyzer._lire_csv_rapide(str(fichier_propre), "utf-8-sig", ",")
    # Le moteur C lèverait une erreur sur une ligne mal formée : zéro est exact.
    assert df.attrs["lignes_ignorees"] == 0


def test_lecteur_rapide_respecte_la_limite(monkeypatch, tmp_path):
    monkeypatch.setattr(analyzer, "LIMITE_LIGNES", 4)
    fichier = _ecrire(
        tmp_path / "gros.csv",
        ["Date,Produit,Prix"]
        + [f"0{i}/01/2026,PC,100" for i in range(1, 10)],
    )

    df = DataAnalyzer._lire_csv_rapide(str(fichier), "utf-8-sig", ",")
    assert len(df) == 4
    assert df.attrs["tronque"] is True


def test_lecteur_rapide_avec_separateur_point_virgule(tmp_path):
    fichier = _ecrire(
        tmp_path / "sc.csv",
        ["Date;Produit;Prix"] + [f"{i:02d}/01/2026;PC;{i}" for i in range(1, 15)],
    )
    df = DataAnalyzer._lire_csv_rapide(str(fichier), "utf-8-sig", ";")
    assert len(df) == 14


# ----------------------------------------------------------------------
# Régression : message d'erreur sur fichier vide
# ----------------------------------------------------------------------

def test_fichier_vide_leve_un_message_lisible(tmp_path):
    """Un fichier vide doit dire « Le fichier est vide. » et non lever NameError.

    (Le `from exc` du bloc EmptyDataError désignait une variable déjà purgée.)
    """
    fichier = _ecrire(tmp_path / "vide.csv", [])
    with pytest.raises(ValueError, match="fichier est vide"):
        DataAnalyzer._charger(str(fichier))


def test_fichier_sans_separateur_lit_une_seule_colonne(tmp_path):
    """Un fichier sans aucun séparateur reste lisible : une colonne, 3 lignes."""
    fichier = _ecrire(tmp_path / "une_colonne.csv", ["uniquement", "une", "colonne"])
    df = DataAnalyzer._charger(str(fichier))

    assert list(df.columns) == ["uniquement"]
    # La première ligne sert d'en-tête.
    assert list(df["uniquement"]) == ["une", "colonne"]
