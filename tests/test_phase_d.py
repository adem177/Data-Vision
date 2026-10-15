"""Tests de la Phase D : protection mémoire et cache partagé."""

import pandas as pd
import pytest

import analyzer
from analyzer import DataAnalyzer, LIMITE_LIGNES
from core import cache as cache_analyseurs


# ----------------------------------------------------------------------
# Protection mémoire (troncature des fichiers géants)
# ----------------------------------------------------------------------

@pytest.fixture
def gros_df():
    """20 lignes, suffisamment pour déclencher une troncature à 5."""
    return pd.DataFrame({
        "Date": [f"{i:02d}/01/2026" for i in range(1, 21)],
        "Produit": ["PC"] * 20,
        "Quantité": [1] * 20,
        "Prix": [100] * 20,
    })


def test_fichier_normal_non_tronque(gros_df):
    a = DataAnalyzer(df=gros_df)
    assert a.tronque is False
    assert len(a.df) == 20


def test_limite_activee(monkeypatch, gros_df):
    monkeypatch.setattr(analyzer, "LIMITE_LIGNES", 5)
    a = DataAnalyzer(df=gros_df.head(5))
    # Le drapeau vient de l'attrs posé par le lecteur de fichier
    a.tronque = True
    assert a.kpis()["tronque"] is True


def test_lire_csv_respecte_la_limite(monkeypatch, tmp_path):
    """Le lecteur ne charge jamais plus de lignes que la limite."""
    monkeypatch.setattr(analyzer, "LIMITE_LIGNES", 4)
    fichier = tmp_path / "gros.csv"
    contenu = "Date,Produit,Prix\n" + "".join(
        f"0{i}/01/2026,PC,100\n" for i in range(1, 10)
    )
    fichier.write_text(contenu, encoding="utf-8")

    df = DataAnalyzer._lire_csv(str(fichier), "utf-8-sig", ",")
    assert len(df) == 4
    assert df.attrs["tronque"] is True


def test_lire_csv_sans_limite(monkeypatch, tmp_path):
    """Un petit fichier n'est pas marqué tronqué."""
    monkeypatch.setattr(analyzer, "LIMITE_LIGNES", 100)
    fichier = tmp_path / "petit.csv"
    fichier.write_text("Date,Produit,Prix\n01/01/2026,PC,100\n", encoding="utf-8")

    df = DataAnalyzer._lire_csv(str(fichier), "utf-8-sig", ",")
    assert df.attrs["tronque"] is False


def test_limite_configurable_par_environnement(monkeypatch):
    """La constante se lit dans DATAVISION_MAX_ROWS."""
    assert isinstance(LIMITE_LIGNES, int)
    assert LIMITE_LIGNES > 0


def test_kpis_expose_la_limite():
    a = DataAnalyzer(df=pd.DataFrame({"Prix": [1, 2]}))
    k = a.kpis()
    assert k["limite_lignes"] == LIMITE_LIGNES
    assert k["tronque"] is False


# ----------------------------------------------------------------------
# Cache partagé des analyseurs
# ----------------------------------------------------------------------

@pytest.fixture
def petit_df():
    return pd.DataFrame({"Produit": ["PC", "Souris"], "Prix": [1800, 25]})


def test_cache_vide_au_debut():
    cache_analyseurs.vider()
    assert cache_analyseurs.charger(999999) is None


def test_cache_stocke_et_recharge(petit_df):
    cache_analyseurs.vider()
    a = DataAnalyzer(df=petit_df)
    cache_analyseurs.stocker(1, a)

    recharge = cache_analyseurs.charger(1)
    assert recharge is not None
    assert len(recharge.df) == 2


def test_cache_oublier(petit_df):
    cache_analyseurs.vider()
    cache_analyseurs.stocker(2, DataAnalyzer(df=petit_df))
    assert cache_analyseurs.charger(2) is not None

    cache_analyseurs.oublier(2)
    assert cache_analyseurs.charger(2) is None


def test_cache_vider_tout(petit_df):
    cache_analyseurs.vider()
    cache_analyseurs.stocker(3, DataAnalyzer(df=petit_df))
    cache_analyseurs.stocker(4, DataAnalyzer(df=petit_df))
    cache_analyseurs.vider()
    assert cache_analyseurs.charger(3) is None
    assert cache_analyseurs.charger(4) is None


def test_cache_survit_une_erreur(monkeypatch):
    """Une erreur de cache ne doit pas faire tomber l'analyse."""

    def lever_erreur(*_args, **_kwargs):
        raise RuntimeError("Redis est tombé")

    monkeypatch.setattr(cache_analyseurs.cache, "get", lever_erreur)
    assert cache_analyseurs.charger(1) is None


def test_cache_refuse_un_analyseur_trop_gros(monkeypatch, petit_df):
    """Un dataframe géant ne doit pas être sérialisé dans Redis.

    Mettre en cache coûte alors plus cher que de relire le fichier, et occupe
    une part de mémoire Redis proportionnelle au fichier importé.
    """
    cache_analyseurs.vider()
    monkeypatch.setattr(cache_analyseurs, "LIMITE_CACHE_LIGNES", 1)

    cache_analyseurs.stocker(5, DataAnalyzer(df=petit_df))  # 2 lignes > 1

    assert cache_analyseurs.charger(5) is None


def test_cache_accepte_un_analyseur_dans_la_limite(monkeypatch, petit_df):
    cache_analyseurs.vider()
    monkeypatch.setattr(cache_analyseurs, "LIMITE_CACHE_LIGNES", 10)

    cache_analyseurs.stocker(6, DataAnalyzer(df=petit_df))

    assert cache_analyseurs.charger(6) is not None


def test_cache_sans_limite_si_zero(monkeypatch, petit_df):
    """« 0 » désactive la limite : tout est mis en cache."""
    cache_analyseurs.vider()
    monkeypatch.setattr(cache_analyseurs, "LIMITE_CACHE_LIGNES", 0)

    cache_analyseurs.stocker(7, DataAnalyzer(df=petit_df))

    assert cache_analyseurs.charger(7) is not None


# ----------------------------------------------------------------------
# Intégration : l'alerte de troncature remonte jusqu'à l'utilisateur
# ----------------------------------------------------------------------

@pytest.fixture
def client_connecte():
    from django.contrib.auth.models import User
    from django.test import Client

    User.objects.create_user("lea", password="motdepasse123")
    client = Client()
    client.login(username="lea", password="motdepasse123")
    return client


@pytest.fixture
def donnees_csv():
    from django.core.files.uploadedfile import SimpleUploadedFile

    contenu = (
        "Date,Produit,Catégorie,Quantité,Prix\n"
        "01/09/2026,PC portable,Informatique,2,1800\n"
        "02/09/2026,Souris,Accessoires,10,25\n"
        "03/09/2026,Écran,Informatique,4,220\n"
    )
    return SimpleUploadedFile("ventes.csv", contenu.encode("utf-8"), "text/csv")


def test_dashboard_affiche_l_alerte_de_troncature(
    client_connecte, donnees_csv, monkeypatch
):
    """Au-delà de la limite, le dashboard prévient que les chiffres sont partiels."""
    monkeypatch.setattr(analyzer, "LIMITE_LIGNES", 2)

    client_connecte.post("/upload", {"fichier": donnees_csv})
    from core.models import Projet

    projet = Projet.objects.get()
    html = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    assert "Fichier volumineux" in html
    assert "partiels" in html


def test_dashboard_sans_troncature_pas_d_alerte(client_connecte, donnees_csv):
    """Un fichier normal n'affiche pas l'alerte de troncature."""
    client_connecte.post("/upload", {"fichier": donnees_csv})
    from core.models import Projet

    projet = Projet.objects.get()
    html = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    assert "Fichier volumineux" not in html


# ----------------------------------------------------------------------
# Garde de taille à l'upload
# ----------------------------------------------------------------------

def test_upload_refuse_un_fichier_trop_volumineux(
    client_connecte, donnees_csv, monkeypatch
):
    """Un fichier plus gros que TAILLE_MAX_UPLOAD est refusé proprement."""
    from django.conf import settings

    from core.models import Projet

    # Limite ramenée à 1 octet : tout fichier est alors trop gros.
    monkeypatch.setattr(settings, "TAILLE_MAX_UPLOAD", 1)

    reponse = client_connecte.post("/upload", {"fichier": donnees_csv}, follow=True)
    assert Projet.objects.count() == 0
    assert b"trop volumineux" in reponse.content


def test_upload_accepte_un_fichier_dans_la_limite(client_connecte, donnees_csv):
    """Un fichier dans la limite passe normalement."""
    from core.models import Projet

    client_connecte.post("/upload", {"fichier": donnees_csv})
    assert Projet.objects.count() == 1
