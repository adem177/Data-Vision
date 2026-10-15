"""Commande de nettoyage de `media/` (`nettoyer_media`).

Contrat vérifié ici, par ordre d'importance :
1. rien n'est supprimé sans `--appliquer` ;
2. un fichier porté par une analyse n'est **jamais** supprimé ;
3. un fichier récent n'est supprimé que si `--age-minimum 0` est demandé.

Le `MEDIA_ROOT` est redirigé vers un dossier temporaire par la fixture
`_media_isole` de `conftest.py` : ces tests ne touchent jamais au vrai
`media/` du projet.
"""

import io
import os
import time
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management import call_command

from core.models import Projet

MOT_DE_PASSE = "MotDePasse-2026"


def _ecrire(relatif: str, contenu: bytes = b"Date,Produit\n01/01/2026,A\n",
            age_heures: float | None = None) -> Path:
    """Dépose un fichier dans le MEDIA_ROOT du test (et le vieillit si besoin)."""
    chemin = Path(settings.MEDIA_ROOT) / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    if age_heures is not None:
        moment = time.time() - age_heures * 3600
        os.utime(chemin, (moment, moment))
    return chemin


def _lancer(*arguments: str) -> tuple[str, str]:
    """Exécute la commande et renvoie (sortie, erreurs)."""
    sortie, erreurs = io.StringIO(), io.StringIO()
    call_command("nettoyer_media", *arguments, stdout=sortie, stderr=erreurs)
    return sortie.getvalue(), erreurs.getvalue()


def _rattacher(nom_fichier: str) -> Projet:
    """Crée une analyse dont le fichier existe réellement sur le disque."""
    utilisateur = User.objects.create_user("nettoyage", password=MOT_DE_PASSE)
    projet = Projet(nom="Analyse conservée", proprietaire=utilisateur)
    projet.fichier.save(nom_fichier, ContentFile(b"Date,Produit\n"), save=True)
    return projet


# ----------------------------------------------------------------------
# Dry-run (comportement par défaut)
# ----------------------------------------------------------------------

def test_dry_run_ne_supprime_rien():
    orphelin = _ecrire("uploads/orphelin.csv", age_heures=48)

    sortie, _ = _lancer()

    assert orphelin.exists()
    assert "Dry-run" in sortie
    assert "rien n'a été supprimé" in sortie
    assert "orphelin(s)" in sortie  # il est bien signalé


def test_dry_run_indique_comment_agir():
    _ecrire("uploads/orphelin.csv", age_heures=48)

    sortie, _ = _lancer()

    assert "--appliquer" in sortie


def test_aucun_fichier_message_clair():
    sortie, _ = _lancer()

    assert "0 fichier(s) examiné(s)" in sortie
    assert "Aucun fichier à supprimer." in sortie


def test_dossier_media_absent_ne_plante_pas():
    import shutil

    shutil.rmtree(settings.MEDIA_ROOT)

    sortie, _ = _lancer()

    assert "introuvable" in sortie


# ----------------------------------------------------------------------
# Garde-fou 1 : les fichiers rattachés sont intouchables
# ----------------------------------------------------------------------

def test_fichier_rattache_survit_a_appliquer():
    projet = _rattacher("rattache.csv")
    orphelin = _ecrire("uploads/orphelin.csv", age_heures=48)

    sortie, _ = _lancer("--appliquer")

    assert Path(settings.MEDIA_ROOT, projet.fichier.name).exists()
    assert not orphelin.exists()
    assert "1 en usage (rattachés à une analyse)" in sortie


def test_fichier_rattache_jeune_comme_vieux_est_conserve():
    """L'âge ne joue que pour les orphelins : un fichier en service ne l'est pas."""
    vieux = _rattacher("ancien-mais-utilise.csv")
    moment = time.time() - 48 * 3600
    chemin = Path(settings.MEDIA_ROOT, vieux.fichier.name)
    os.utime(chemin, (moment, moment))

    _lancer("--appliquer")

    assert chemin.exists()


# ----------------------------------------------------------------------
# Garde-fou 2 : âge minimum
# ----------------------------------------------------------------------

def test_fichier_recent_non_supprime_par_defaut():
    chaud = _ecrire("uploads/chaud.csv")  # créé à l'instant

    sortie, _ = _lancer("--appliquer")

    assert chaud.exists()
    assert "conservés" in sortie


def test_age_minimum_zero_desactive_la_garde():
    chaud = _ecrire("uploads/chaud.csv")

    _lancer("--appliquer", "--age-minimum", "0")

    assert not chaud.exists()


def test_age_minimum_negatif_est_ramene_a_zero():
    chaud = _ecrire("uploads/chaud.csv")

    _lancer("--appliquer", "--age-minimum", "-5")

    assert not chaud.exists()


# ----------------------------------------------------------------------
# Suppression effective
# ----------------------------------------------------------------------

def test_appliquer_supprime_les_orphelins_anciens():
    vieux = _ecrire("uploads/2026/10/vieux.csv", age_heures=48)

    sortie, _ = _lancer("--appliquer")

    assert not vieux.exists()
    assert "fichier(s) supprimé(s)" in sortie


def test_dossiers_devenus_vides_sont_retires():
    vieux = _ecrire("uploads/2026/10/vieux.csv", age_heures=48)
    dossier = vieux.parent

    sortie, _ = _lancer("--appliquer")

    assert not dossier.exists()
    assert "dossier(s) vide(s) retiré(s)" in sortie


def test_dossiers_non_vides_sont_gardes():
    """Un dossier qui abrite encore un fichier rattaché n'est pas retiré."""
    garde = _rattacher("garde.csv")  # déposé dans uploads/AAAA/MM/
    orphelin = _ecrire("uploads/2026/10/orphelin.csv", age_heures=48)

    _lancer("--appliquer")

    assert not orphelin.exists()
    chemin_garde = Path(settings.MEDIA_ROOT, garde.fichier.name)
    assert chemin_garde.exists()
    assert chemin_garde.parent.exists()


# ----------------------------------------------------------------------
# Comptes annoncés
# ----------------------------------------------------------------------

def test_comptes_exacts_des_trois_catégories():
    _rattacher("rattache.csv")
    _ecrire("uploads/vieux1.csv", age_heures=48)
    _ecrire("uploads/vieux2.csv", age_heures=48)
    _ecrire("uploads/chaud.csv")

    sortie, _ = _lancer()

    assert "1 en usage (rattachés à une analyse)" in sortie
    assert "1 orphelin(s) plus jeunes que 24 h : conservés" in sortie
    assert "2 orphelin(s)" in sortie


def test_le_detail_est_cadre():
    """Au-delà de 20 lignes, on résume plutôt que de noyer la sortie."""
    for i in range(25):
        _ecrire(f"uploads/fichier{i:02d}.csv", age_heures=48)

    sortie, _ = _lancer()

    assert "… et 5 autre(s)" in sortie


def test_taille_lisible_en_francais():
    from core.management.commands.nettoyer_media import _taille

    assert _taille(812) == "812 o"
    assert _taille(1400) == "1,4 Ko"
    assert _taille(5 * 1024 * 1024) == "5 Mo"


# ----------------------------------------------------------------------
# Option --conserver
# ----------------------------------------------------------------------

def test_conserver_protege_un_vrai_csv():
    """Un CSV déposé à la main et jamais importé doit pouvoir survivre."""
    vrai = _ecrire("uploads/ae4f7385_Societes_Nabeul_Tunis.csv", age_heures=48)
    artefact = _ecrire("uploads/ventes_aBcDeFg.csv", age_heures=48)

    sortie, _ = _lancer("--appliquer", "--age-minimum", "0",
                        "--conserver", "Societes_Nabeul")

    assert vrai.exists()
    assert not artefact.exists()
    assert "1 conservé(s) sur demande (--conserver)" in sortie


def test_conserver_insensible_a_la_casse():
    fichier = _ecrire("uploads/movies_lim_2023.csv", age_heures=72)

    _lancer("--appliquer", "--conserver", "MOVIES_LIM")

    assert fichier.exists()


def test_conserver_repete_garde_plusieurs_familles():
    premier = _ecrire("uploads/Societes_Nabeul.csv", age_heures=48)
    second = _ecrire("uploads/movies_lim.csv", age_heures=48)
    tue = _ecrire("uploads/ventes_zzzzzz.csv", age_heures=48)

    _lancer("--appliquer", "--age-minimum", "0",
            "--conserver", "Societes", "--conserver", "movies")

    assert premier.exists()
    assert second.exists()
    assert not tue.exists()


def test_conserver_sans_correspondance_prevenu():
    _ecrire("uploads/ventes_qqqqqq.csv", age_heures=48)

    sortie, _ = _lancer("--appliquer", "--conserver", "jamais-present")

    assert "Aucun fichier ne correspond à --conserver" in sortie
    assert not Path(settings.MEDIA_ROOT, "uploads/ventes_qqqqqq.csv").exists()
