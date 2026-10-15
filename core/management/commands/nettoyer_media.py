"""Commande : retire de `media/` les fichiers plus rattachés à aucune analyse.

Après des suppressions de comptes, des imports avortés ou d'anciens tests,
des fichiers restent sur le disque sans plus être servis par personne : ils
pèsent dans la sauvegarde du site sans jamais apparaître dans l'interface.

    python manage.py nettoyer_media                    # audit seul (dry-run)
    python manage.py nettoyer_media --appliquer        # supprime réellement
    python manage.py nettoyer_media --appliquer --age-minimum 0
    python manage.py nettoyer_media --appliquer --conserver Nabeul

Quatre garde-fous, par ordre d'importance :

1. **Dry-run par défaut** : sans `--appliquer`, la commande se contente de
   décrire ce qu'elle supprimerait — relancer est toujours sans risque.
2. **Aucun fichier référencé** : tout fichier porté par un `Projet` est
   écarté, quel qu'en soit l'âge ou l'emplacement. C'est la garantie
   centrale : les analyses en place ne perdent jamais leur CSV.
3. **`--age-minimum` (24 h par défaut)** : un fichier écrit à l'instant est
   peut-être un import en cours (le fichier est enregistré sur disque avant
   l'enregistrement du projet en base) — on n'y touche pas. `--age-minimum 0`
   désactive cette garde.
4. **`--conserver FRAGMENT`** (répétable) : garde les fichiers dont le nom
   contient FRAGMENT (insensible à la casse), même orphelins et même vieux.
   Sert à préserver un CSV déposé à la main dans `media/` et jamais importé.
"""

import os
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Projet

# Nombre de chemins imprimés en détail avant de simplement résumer.
LIGNES_DETAIL = 20


def _taille(octets: int) -> str:
    """Taille lisible en français : « 812 o », « 1,4 Mo », « 2,1 Go »."""
    valeur = float(octets)
    unite = "o"
    while valeur >= 1024 and unite != "Go":
        valeur /= 1024
        unite = {"o": "Ko", "Ko": "Mo", "Mo": "Go"}[unite]
    texte = f"{valeur:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{texte} {unite}"


class Command(BaseCommand):
    help = (
        "Répertorie les fichiers de media/ plus rattachés à aucune analyse "
        "(dry-run par défaut) ; --appliquer les supprime réellement."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--appliquer",
            action="store_true",
            help="Supprime réellement les fichiers (sinon : audit seul).",
        )
        parser.add_argument(
            "--age-minimum",
            type=int,
            default=24,
            metavar="HEURES",
            help="Ignore les fichiers plus jeunes que HEURES heures "
                 "(défaut : %(default)s ; 0 désactive la garde).",
        )
        parser.add_argument(
            "--conserver",
            action="append",
            default=[],
            metavar="FRAGMENT",
            help="Garde les fichiers dont le nom contient FRAGMENT "
                 "(insensible à la casse). Répétable.",
        )

    # ------------------------------------------------------------------
    # Sources de vérité
    # ------------------------------------------------------------------

    @staticmethod
    def _references() -> set:
        """Chemins (au format POSIX, relatifs à MEDIA_ROOT) portés par une analyse."""
        return {
            projet.fichier.name.replace(os.sep, "/")
            for projet in Projet.objects.exclude(fichier="").only("fichier")
            if projet.fichier.name
        }

    @staticmethod
    def _vider_dossiers(racine: Path) -> list:
        """Retire les dossiers devenus vides (du plus profond au moins profond).

        Un dossier parent ne peut devenir vide qu'après ses enfants, et
        l'ordre lexicographique décroissant garantit justement que les
        chemins les plus profonds passent en premier. `rmdir` ne supprime
        que les dossiers réellement vides : rien d'autre n'est touché.
        """
        vides = []
        for dossier in sorted(
            (p for p in racine.rglob("*") if p.is_dir()), reverse=True
        ):
            try:
                dossier.rmdir()
            except OSError:
                continue  # non vide, ou supprimé entre-temps
            vides.append(dossier)
        return vides

    # ------------------------------------------------------------------
    # Exécution
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        racine = Path(settings.MEDIA_ROOT)
        appliquer = options["appliquer"]
        age_minimum = max(options["age_minimum"], 0)

        if not racine.exists():
            self.stdout.write(
                f"Dossier media/ introuvable ({racine}) : rien à nettoyer."
            )
            return

        references = self._references()
        conservees = [fragment.lower() for fragment in options["conserver"] if fragment]
        limite_age = time.time() - age_minimum * 3600

        en_usage: list[str] = []
        sur_demande: list[str] = []
        trop_recents: list[str] = []
        a_supprimer: list[tuple[Path, int]] = []

        for chemin in sorted(racine.rglob("*")):
            if not chemin.is_file():
                continue
            relatif = chemin.relative_to(racine).as_posix()
            if relatif in references:
                en_usage.append(relatif)
                continue
            if any(frag in relatif.lower() for frag in conservees):
                sur_demande.append(relatif)
                continue
            try:
                taille = chemin.stat().st_size
                ancien = chemin.stat().st_mtime < limite_age
            except OSError:
                continue  # fichier disparu entre-temps : rien à signaler
            if ancien:
                a_supprimer.append((chemin, taille))
            else:
                trop_recents.append(relatif)

        total = len(en_usage) + len(sur_demande) + len(trop_recents) + len(a_supprimer)
        self.stdout.write(f"media/ : {total} fichier(s) examiné(s)")
        self.stdout.write(f"  - {len(en_usage)} en usage (rattachés à une analyse)")
        if sur_demande:
            self.stdout.write(
                f"  - {len(sur_demande)} conservé(s) sur demande (--conserver)"
            )
        if conservees and not sur_demande:
            self.stdout.write(self.style.WARNING(
                "Aucun fichier ne correspond à --conserver : vérifie l'orthographe."
            ))
        if trop_recents:
            self.stdout.write(
                f"  - {len(trop_recents)} orphelin(s) plus jeunes que "
                f"{age_minimum} h : conservés"
            )
        if not a_supprimer:
            self.stdout.write(self.style.SUCCESS("Aucun fichier à supprimer."))
            return

        poids = sum(taille for _, taille in a_supprimer)
        etat = (
            "candidat(s) à la suppression"
            if not appliquer
            else "à supprimer"
        )
        self.stdout.write(
            f"  - {len(a_supprimer)} orphelin(s), {_taille(poids)} : {etat}"
        )
        for chemin, _ in a_supprimer[:LIGNES_DETAIL]:
            self.stdout.write(f"      {chemin.relative_to(racine).as_posix()}")
        if len(a_supprimer) > LIGNES_DETAIL:
            self.stdout.write(
                f"      … et {len(a_supprimer) - LIGNES_DETAIL} autre(s)"
            )

        if not appliquer:
            self.stdout.write(self.style.WARNING(
                "Dry-run : rien n'a été supprimé. "
                "Relance avec --appliquer pour agir."
            ))
            return

        self._supprimer(a_supprimer)
        vides = self._vider_dossiers(racine)
        if vides:
            self.stdout.write(f"{len(vides)} dossier(s) vide(s) retiré(s).")

    def _supprimer(self, a_supprimer: list) -> None:
        """Supprime les fichiers un par un, en poursuivant malgré les échecs."""
        supprimes = 0
        liberes = 0
        echecs = []
        for chemin, taille in a_supprimer:
            try:
                chemin.unlink()
                supprimes += 1
                liberes += taille
            except OSError as exc:
                echecs.append((chemin, exc))

        if supprimes:
            self.stdout.write(self.style.SUCCESS(
                f"{supprimes} fichier(s) supprimé(s), {_taille(liberes)} libéré(s)."
            ))
        for chemin, exc in echecs:
            self.stderr.write(self.style.ERROR(
                f"Échec de suppression : {chemin} ({exc})"
            ))
