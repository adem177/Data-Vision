"""Note de l'analyste et source des données (champ éditorial).

Règle empruntée à Datawrapper : une visualisation porte sa lecture (note)
et son origine (source) partout où elle voyage — page, export PNG, PDF.
La route n'ouvre rien à qui n'est pas propriétaire, la longueur est
coupée net, et le texte utilisateur n'est jamais rendu cru.
"""

import base64
import re
import zlib

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.models import Projet

MOT_DE_PASSE = "MotDePasse-2026"
CONTENU = (
    "Date,Produit,Catégorie,Quantité,Prix\n"
    "05/01/2026,Vis,Info,2,10\n"
    "06/01/2026,Boulon,Info,3,5\n"
)


@pytest.fixture
def client_connecte():
    User.objects.create_user("lectrice", password=MOT_DE_PASSE)
    client = Client(enforce_csrf_checks=False)
    client.login(username="lectrice", password=MOT_DE_PASSE)
    return client


@pytest.fixture
def projet(client_connecte):
    client_connecte.post("/upload", {
        "fichier": SimpleUploadedFile(
            "ventes.csv", CONTENU.encode("utf-8"), "text/csv"
        ),
    })
    return Projet.objects.get()


# ----------------------------------------------------------------------
# Enregistrement
# ----------------------------------------------------------------------


def test_post_enregistre_et_redirige_vers_le_dashboard(client_connecte, projet):
    reponse = client_connecte.post(f"/projet/{projet.pk}/note", {
        "note": "Le CA progresse nettement en janvier.",
        "source": "Enquete interne 2026",
    })

    assert reponse.status_code == 302
    assert reponse.url == f"/dashboard/{projet.pk}"
    projet.refresh_from_db()
    assert projet.note_analyste == "Le CA progresse nettement en janvier."
    assert projet.source_donnees == "Enquete interne 2026"


def test_get_ne_change_rien(client_connecte, projet):
    """Une visite en GET sur la route ne doit rien écrire."""
    reponse = client_connecte.get(f"/projet/{projet.pk}/note")

    assert reponse.status_code == 302
    projet.refresh_from_db()
    assert projet.note_analyste == ""
    assert projet.source_donnees == ""


def test_une_autre_utilisateur_ne_peut_pas_toucher_la_note(client_connecte, projet):
    User.objects.create_user("intruse", password=MOT_DE_PASSE)
    autre = Client(enforce_csrf_checks=False)
    autre.login(username="intruse", password=MOT_DE_PASSE)

    reponse = autre.post(f"/projet/{projet.pk}/note", {"note": "piratage"})

    assert reponse.status_code == 404
    projet.refresh_from_db()
    assert projet.note_analyste == ""


@pytest.mark.parametrize(
    ("champ", "trop_long", "message"),
    [
        ("note", "x" * 1001, "1000 caractères maximum"),
        ("source", "x" * 301, "300 caractères maximum"),
    ],
)
def test_une_valeur_trop_longue_est_refusee(
    client_connecte, projet, champ, trop_long, message
):
    reponse = client_connecte.post(
        f"/projet/{projet.pk}/note", {champ: trop_long}
    )

    assert reponse.status_code == 302
    projet.refresh_from_db()
    assert projet.note_analyste == ""
    assert projet.source_donnees == ""
    # Le message d'erreur est rendu sur le dashboard, après la redirection.
    page = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()
    assert message in page


# ----------------------------------------------------------------------
# Affichage
# ----------------------------------------------------------------------


def test_le_dashboard_affiche_la_note_et_la_source(client_connecte, projet):
    client_connecte.post(f"/projet/{projet.pk}/note", {
        "note": "Les ventes grimpent, portées par l'Info.",
        "source": "Enquete interne 2026",
    })

    texte = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    # L'apostrophe est rendue `&#x27;` : c'est la preuve que le texte
    # traverse l'échappement de Django avant d'arriver au navigateur.
    assert "Les ventes grimpent, portées par l&#x27;Info." in texte
    assert "Enquete interne 2026" in texte
    assert "Source :" in texte


def test_sans_note_lediteur_reste_accessible(client_connecte, projet):
    texte = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    assert "Ajouter une note et une source" in texte
    assert 'name="note"' in texte
    assert 'name="source"' in texte


def test_une_note_malveillante_est_echappee(client_connecte, projet):
    client_connecte.post(f"/projet/{projet.pk}/note", {
        "note": "<script>alert(1)</script>",
        "source": "<img src=x onerror=alert(2)>",
    })

    texte = client_connecte.get(f"/dashboard/{projet.pk}").content.decode()

    assert "<script>alert(1)</script>" not in texte
    assert "<img src=x onerror=alert(2)>" not in texte
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in texte


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------


def _decoder(flux: bytes) -> bytes:
    """Décode un flux reportlab : brut, Flate, ou ASCII85+Flate."""
    flux = flux.rstrip(b"\r\n")
    try:
        return zlib.decompress(flux)
    except zlib.error:
        pass
    try:
        brut = flux.strip()
        if brut.endswith(b"~>"):
            brut = brut[:-2]
        return zlib.decompress(base64.a85decode(brut, ignorechars=b" \t\r\n"))
    except (ValueError, zlib.error):
        return flux  # flux non compressé : on garde les octets tels quels


def _texte_pdf(octets: bytes) -> str:
    """Texte contenu dans un PDF (reportlab compresse en ASCII85 + Flate)."""
    morceaux = [
        _decoder(m.group(1))
        for m in re.finditer(rb"(?<!end)stream\r?\n(.*?)endstream", octets, re.S)
    ]
    # Les flux décodés ET les octets bruts : le test ne dépend pas du
    # réglage de compression de reportlab.
    return (b"\n".join(morceaux) + b"\n" + octets).decode("latin-1", "replace")


def test_le_pdf_porte_la_note_et_la_source(client_connecte, projet):
    client_connecte.post(f"/projet/{projet.pk}/note", {
        "note": "Les ventes bondissent en janvier.",
        "source": "Enquete interne 2026",
    })

    reponse = client_connecte.get(f"/projet/{projet.pk}/rapport")

    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"
    texte = _texte_pdf(reponse.content)
    assert "bondissent" in texte
    assert "Enquete interne 2026" in texte


def test_le_pdf_sans_note_reste_valide(client_connecte, projet):
    reponse = client_connecte.get(f"/projet/{projet.pk}/rapport")

    assert reponse.status_code == 200
    assert reponse.content[:5] == b"%PDF-"
    assert "Note de l" not in _texte_pdf(reponse.content)
