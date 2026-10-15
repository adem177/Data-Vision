"""
DataVision — moteur d'analyse de données.

Lit un fichier CSV ou Excel, nettoie automatiquement les données
(doublons, valeurs manquantes, formats de date) puis produit les
indicateurs et agrégations utilisés par le dashboard.
"""

from __future__ import annotations

import os
import unicodedata
from io import BytesIO

import numpy as np
import pandas as pd

# Valeurs considérées comme « manquantes » dans les colonnes texte
MARQUEURS_MANQUANTS = ["", "na", "n/a", "nan", "null", "none", "-", "--"]

# Nombre maximal de lignes analysées. Au-delà, le fichier est tronqué et
# l'utilisateur est prévenu : on évite ainsi de saturer la mémoire avec un
# fichier géant. Ajustable via la variable d'environnement DATAVISION_MAX_ROWS.
LIMITE_LIGNES = int(os.environ.get("DATAVISION_MAX_ROWS", "500000"))


def _norm(texte) -> str:
    """Normalise un nom de colonne : 'Catégorie' -> 'categorie'."""
    texte = unicodedata.normalize("NFKD", str(texte))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return texte.lower().strip()


class DataAnalyzer:
    """Analyse un fichier tabulaire et produit les indicateurs du dashboard."""

    # Rôle -> mots-clés possibles dans le nom de la colonne
    ROLES = {
        "date": ["date", "jour", "datetime", "temps", "time", "mois"],
        "produit": ["produit", "product", "article", "designation", "libelle", "nom"],
        "categorie": ["categorie", "category", "famille", "segment", "type", "service"],
        "quantite": ["quantite", "qte", "quantity", "nombre", "nb", "unite", "vendus"],
        "prix": ["prix", "price", "pu", "tarif", "montant", "cout", "cost"],
    }

    ROLES_AFFICHAGES = {
        "date": "Colonne de date",
        "produit": "Colonne de produit",
        "categorie": "Colonne de catégorie",
        "quantite": "Colonne de quantité",
        "prix": "Colonne de prix",
    }

    # Nombre d'entrées conservées dans les mémoïsations (filtres et
    # agrégations) : assez pour couvrir les filtres d'une session de travail,
    # sans que les dictionnaires croissent indéfiniment.
    TAILLE_MEMO = 32

    def __init__(self, filepath: str | None = None, df: pd.DataFrame | None = None):
        if df is not None:
            self.df = df.copy()
        elif filepath:
            self.df = self._charger(filepath)
        else:
            raise ValueError("Aucune donnée fournie.")
        self.chemin = filepath
        # Mémoïsations : voir `_agreger()` et `filtrer()`. Initialisées avant
        # `_construire_ca()`, qu'un `appliquer_mapping()` peut invalider.
        self._memo_filtres: dict = {}
        self._memo_agregations: dict = {}
        self.lignes_ignorees = int(self.df.attrs.get("lignes_ignorees", 0))
        # Vrai si le fichier dépassait LIMITE_LIGNES : seules les premières
        # lignes ont été analysées (protection mémoire).
        self.tronque = bool(self.df.attrs.get("tronque", False))
        self.nb_doublons = int(self.df.duplicated().sum())
        self.df = self._nettoyer(self.df)
        self.colonnes = self._detecter_colonnes()
        self._construire_ca()

    def appliquer_mapping(self, mapping: dict | None) -> None:
        """Remplace la détection auto par le choix manuel de l'utilisateur.

        `mapping` = {"date": "Date d'achat", "prix": "Montant", ...}
        Les rôles absents ou pointant vers une colonne inexistante sont ignorés
        (on garde alors la détection automatique pour ce rôle).
        """
        if not mapping:
            return
        colonnes_valides = set(self.df.columns)
        for role, colonne in mapping.items():
            if role in self.colonnes and colonne in colonnes_valides:
                self.colonnes[role] = colonne
        self._construire_ca()
        # La colonne CA vient de changer de sens : tout ce qui en découle
        # (KPIs, séries, classements) est périmé.
        self._vider_memo()

    # ------------------------------------------------------------------
    # Mémoïsation des filtres et des agrégations
    # ------------------------------------------------------------------
    #
    # `/api/donnees` recalcule à chaque appel l'évolution, les catégories, le
    # classement, les corrélations et les anomalies. Sur un fichier de
    # 500 000 lignes, chaque changement de filtre — et surtout chaque clic de
    # pagination — repaie ce coût alors que les données d'entrée n'ont pas
    # bougé. On conserve donc le résultat, indexé sur le filtre appliqué.
    #
    # Les objets renvoyés sont **partagés** : tout appelant doit les traiter
    # en lecture seule (aucun ne les modifie aujourd'hui).

    def _vider_memo(self) -> None:
        """Oublie filtres et agrégations mémorisés.

        Les deux dictionnaires sont toujours vidés ensemble : les agrégations
        sont indexées sur l'identité des dataframes filtrés, et un débordement
        qui libérerait un dataframe pourrait faire réutiliser son adresse par
        un autre — d'où une entrée périmée. Vider les deux supprime ce risque.
        """
        self._memo_filtres.clear()
        self._memo_agregations.clear()

    def _agreger(self, cle: str, df: pd.DataFrame, parametres: tuple, calcul):
        """Renvoie l'agrégation `cle` pour ce filtre, en ne la calculant qu'une fois."""
        index = (cle, parametres, id(df))
        if index not in self._memo_agregations:
            if len(self._memo_agregations) >= self.TAILLE_MEMO:
                self._vider_memo()
            self._memo_agregations[index] = calcul()
        return self._memo_agregations[index]

    def options_mapping(self) -> list:
        """Renvoie les rôles, la colonne retenue et la liste des choix possibles."""
        disponibles = [c for c in self.df.columns if c != "CA"]
        return [
            {
                "role": role,
                "libelle": self.ROLES_AFFICHAGES.get(role, role),
                "actuel": self.colonnes.get(role, ""),
                "disponibles": disponibles,
            }
            for role in self.ROLES_AFFICHAGES
        ]

    # ------------------------------------------------------------------
    # Chargement et nettoyage
    # ------------------------------------------------------------------

    SEPARATEURS_CANDIDATS = [",", ";", "\t", "|"]

    @staticmethod
    def _echantillon_entete(filepath: str, encodage: str, n: int = 20) -> list[str]:
        """Les n premières lignes non vides du fichier, sans saut de ligne."""
        try:
            with open(filepath, "r", encoding=encodage, errors="replace") as f:
                lignes = [next(f, "") for _ in range(n)]
        except OSError:
            return []
        return [ligne.rstrip("\r\n") for ligne in lignes if ligne.strip()]

    @staticmethod
    def _diagnostiquer_entete(filepath: str, encodage: str) -> tuple[str, bool]:
        """Retourne ``(séparateur, fichier_régulier)``.

        Le séparateur est celui qui donne le même nombre de champs sur la
        majorité des lignes d'aperçu.

        « Régulier » signifie que les lignes d'aperçu comptent toutes le même
        nombre de champs avec ce séparateur : un fichier propre de bout en
        bout peut alors être lu d'un trait par le moteur C de Pandas, cinq à
        vingt fois plus rapide que le moteur Python. Un échantillon
        irrégulier fait au contraire basculer directement sur le lecteur
        lent, seul capable de compter les lignes mal formées.
        """
        lignes = DataAnalyzer._echantillon_entete(filepath, encodage)
        if not lignes:
            return ",", False

        meilleur, meilleur_score = ",", -1.0
        for sep in DataAnalyzer.SEPARATEURS_CANDIDATS:
            comptes = [ligne.count(sep) for ligne in lignes]
            if max(comptes, default=0) == 0:
                continue
            plus_frequent = max(set(comptes), key=comptes.count)
            regularite = comptes.count(plus_frequent) / len(comptes)
            score = regularite * plus_frequent
            if score > meilleur_score:
                meilleur, meilleur_score = sep, score

        if meilleur_score <= 0:
            return ",", False

        champs = {ligne.count(meilleur) for ligne in lignes}
        return meilleur, len(champs) == 1

    @staticmethod
    def _detecter_separateur(filepath: str, encodage: str) -> str:
        """Devine le séparateur (virgule, point-virgule, tabulation…)."""
        return DataAnalyzer._diagnostiquer_entete(filepath, encodage)[0]

    @staticmethod
    def _preparer_attrs(df: pd.DataFrame) -> pd.DataFrame:
        df.attrs["tronque"] = len(df) >= LIMITE_LIGNES
        return df

    @staticmethod
    def _lire_csv(filepath: str, encodage: str, separateur: str) -> pd.DataFrame:
        """Lecture robuste (moteur Python) : lent mais tolérant.

        Les lignes mal formées sont comptées une à une puis sautées, ce qui
        donne à l'utilisateur un avertissement exact.

        Seules les LIMITE_LIGNES premières lignes sont conservées : au-delà,
        le dataframe est marqué « tronqué » afin de ne jamais saturer la
        mémoire sur un fichier géant.
        """
        lignes_ignorees = 0

        def collecter(_ligne):
            nonlocal lignes_ignorees
            lignes_ignorees += 1
            return None  # None => pandas ignore cette ligne

        df = pd.read_csv(
            filepath,
            encoding=encodage,
            sep=separateur,
            engine="python",
            on_bad_lines=collecter,
            skip_blank_lines=True,
            nrows=LIMITE_LIGNES,
        )
        df.attrs["lignes_ignorees"] = lignes_ignorees
        return DataAnalyzer._preparer_attrs(df)

    @staticmethod
    def _lire_csv_rapide(filepath: str, encodage: str, separateur: str) -> pd.DataFrame:
        """Lecture rapide (moteur C de Pandas, écrit en C).

        Le moteur C lève ``ParserError`` à la première ligne mal formée, donc
        s'il réussit on sait qu'il n'y en avait aucune : le comptage exact est
        préservé, sans payer le coût du moteur Python.

        ``low_memory=False`` force une seule interprétation de type et évite
        les avertissements DtypeWarning sur les colonnes hétérogènes.
        """
        df = pd.read_csv(
            filepath,
            encoding=encodage,
            sep=separateur,
            engine="c",
            low_memory=False,
            skip_blank_lines=True,
            nrows=LIMITE_LIGNES,
        )
        # Aucune ligne mal formée : le moteur C les aurait signalées.
        df.attrs["lignes_ignorees"] = 0
        return DataAnalyzer._preparer_attrs(df)

    @staticmethod
    def _charger(filepath: str) -> pd.DataFrame:
        """Charge un CSV ou Excel en tolérant encodage, séparateur et lignes hétérogènes."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(filepath, nrows=LIMITE_LIGNES)
            df.attrs["lignes_ignorees"] = 0
            return DataAnalyzer._preparer_attrs(df)

        erreurs = []
        for encodage in ("utf-8-sig", "latin-1"):
            separateur, regulier = DataAnalyzer._diagnostiquer_entete(filepath, encodage)

            # Échantillon régulier : on tente d'abord le moteur C, cinq à
            # vingt fois plus rapide. S'il bute sur une ligne mal formée, on
            # bascule sur le lecteur robuste, seul à pouvoir les compter
            # exactement. Échantillon irrégulier : on ne gaspille pas un essai.
            lecteurs = (
                [DataAnalyzer._lire_csv_rapide, DataAnalyzer._lire_csv]
                if regulier
                else [DataAnalyzer._lire_csv]
            )

            for lecteur in lecteurs:
                rapide = lecteur is DataAnalyzer._lire_csv_rapide
                try:
                    return lecteur(filepath, encodage, separateur)
                except UnicodeDecodeError as exc:
                    # Même encodage : passer au suivant, inutile de réessayer.
                    erreurs.append(f"{encodage} : {exc}")
                    break
                except pd.errors.EmptyDataError as exc:
                    raise ValueError("Le fichier est vide.") from exc
                except pd.errors.ParserError as exc:
                    if rapide:
                        # Le moteur C refuse la ligne : le lecteur Python la
                        # sautera en la comptant. On repart avec lui seul.
                        erreurs.append(f"{encodage}, moteur C : {exc}")
                        continue
                    erreurs.append(f"{encodage}, séparateur « {separateur} » : {exc}")
                except Exception as exc:  # noqa: BLE001 — on tente l'encodage suivant
                    erreurs.append(f"{encodage}, séparateur « {separateur} » : {exc}")
                    break

        raise ValueError("Fichier illisible. Détails : " + " | ".join(erreurs))

    @staticmethod
    def _nettoyer(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        df = df.drop_duplicates()
        # Remplace les marqueurs de valeurs manquantes par de vraies NaN
        texte = df.select_dtypes(include=["object", "str"])
        if not texte.empty:
            df[texte.columns] = texte.replace({m: np.nan for m in MARQUEURS_MANQUANTS})
        # Convertit les colonnes de date (formats JJ/MM/AAAA inclus)
        for col in df.columns:
            if _norm(col) in ("date", "jour"):
                df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
        return df

    # ------------------------------------------------------------------
    # Détection automatique des colonnes (peu importe la casse / accents)
    # ------------------------------------------------------------------

    def _detecter_colonnes(self) -> dict:
        trouve: dict = {}
        noms_norm = {_norm(c): c for c in self.df.columns}
        for role, mots in self.ROLES.items():
            for mot in mots:
                for nom_norm, nom_reel in noms_norm.items():
                    if nom_norm == mot or mot in nom_norm.split():
                        trouve.setdefault(role, nom_reel)
        # Date : toute colonne déjà convertie en datetime
        if "date" not in trouve:
            for col in self.df.columns:
                if pd.api.types.is_datetime64_any_dtype(self.df[col]):
                    trouve["date"] = col
                    break
        # Colonnes numériques : heuristique de secours quantité / prix
        numeriques = [
            c for c in self.df.columns
            if pd.api.types.is_numeric_dtype(self.df[c]) and _norm(c) not in ("id", "index")
        ]
        if len(numeriques) >= 2:
            moyennes = {c: self.df[c].abs().mean() for c in numeriques}
            tri = sorted(moyennes, key=moyennes.get)  # petit = quantité, gros = prix
            trouve.setdefault("quantite", tri[0])
            trouve.setdefault("prix", tri[-1])
        elif len(numeriques) == 1:
            trouve.setdefault("prix", numeriques[0])
        return trouve

    def _construire_ca(self) -> None:
        """Colonne calculée CA = Quantité × Prix (repli sur Prix seul)."""
        q, p = self.colonnes.get("quantite"), self.colonnes.get("prix")
        if q and p:
            self.df["CA"] = self.df[q].fillna(0) * self.df[p].fillna(0)
        elif p:
            self.df["CA"] = self.df[p].fillna(0)
        else:
            self.df["CA"] = np.nan

    @property
    def ca_disponible(self) -> bool:
        return bool(self.df["CA"].notna().any())

    # ------------------------------------------------------------------
    # Indicateurs
    # ------------------------------------------------------------------

    def kpis(self, df: pd.DataFrame | None = None) -> dict:
        df = self.df if df is None else df
        return self._agreger("kpis", df, (), lambda: self._kpis(df))

    def _kpis(self, df: pd.DataFrame) -> dict:
        ca = float(df["CA"].sum()) if self.ca_disponible else None
        nb = len(df)
        q = self.colonnes.get("quantite")
        p = self.colonnes.get("produit")
        c = self.colonnes.get("categorie")
        return {
            "ca_total": round(ca, 2) if ca is not None else None,
            "nb_ventes": int(nb),
            "panier_moyen": round(ca / nb, 2) if ca is not None and nb else None,
            "produits_vendus": int(df[q].sum()) if q else None,
            "nb_produits_uniques": int(df[p].nunique()) if p else None,
            "nb_categories": int(df[c].nunique()) if c else None,
            "valeurs_manquantes": int(df.isna().sum().sum()),
            "doublons_supprimes": self.nb_doublons,
            "lignes_ignorees": self.lignes_ignorees,
            "tronque": self.tronque,
            "limite_lignes": LIMITE_LIGNES,
            "colonnes": list(self.df.columns.drop("CA")),
            "roles": self.colonnes,
        }

    def evolution_mensuelle(self, df: pd.DataFrame | None = None) -> pd.Series:
        df = self.df if df is None else df
        return self._agreger("evolution", df, (), lambda: self._evolution_mensuelle(df))

    def _evolution_mensuelle(self, df: pd.DataFrame) -> pd.Series:
        if not self.ca_disponible or df.empty:
            return pd.Series(dtype=float)
        d = self.colonnes.get("date")
        if d and df[d].notna().any():
            serie = df.groupby(df[d].dt.to_period("M"))["CA"].sum()
            serie.index = serie.index.astype(str)
            return serie
        # Repli sans colonne date : découpe en 10 tranches
        n = min(10, max(1, len(df)))
        temp = df.copy()
        temp["tranche"] = np.linspace(0, n - 1, len(temp)).astype(int)
        serie = temp.groupby("tranche")["CA"].sum()
        serie.index = [f"Part {i + 1}" for i in serie.index]
        return serie

    def par_categorie(self, df: pd.DataFrame | None = None) -> pd.Series:
        df = self.df if df is None else df
        return self._agreger("categories", df, (), lambda: self._par_categorie(df))

    def _par_categorie(self, df: pd.DataFrame) -> pd.Series:
        c = self.colonnes.get("categorie")
        if not (self.ca_disponible and c) or df.empty:
            return pd.Series(dtype=float)
        return df.groupby(c, dropna=True)["CA"].sum().sort_values(ascending=False)

    def top_produits(self, n: int = 5, df: pd.DataFrame | None = None) -> pd.Series:
        df = self.df if df is None else df
        return self._agreger("top", df, (n,), lambda: self._top_produits(n, df))

    def _top_produits(self, n: int, df: pd.DataFrame) -> pd.Series:
        p = self.colonnes.get("produit")
        if not p or df.empty:
            return pd.Series(dtype=float)
        if self.ca_disponible:
            return df.groupby(p)["CA"].sum().nlargest(n)
        q = self.colonnes.get("quantite")
        if q:
            return df.groupby(p)[q].sum().nlargest(n)
        return pd.Series(dtype=float)

    def classement_produits(self, n: int = 5, df: pd.DataFrame | None = None) -> dict:
        """Top et Flop des produits : les meilleurs ET les moins performants.

        Ne se contenter de montrer les meilleurs masque les produits à
        retirer du catalogue — le Flop est souvent plus actionnable.
        """
        df = self.df if df is None else df
        return self._agreger(
            "classement", df, (n,), lambda: self._classement_produits(n, df)
        )

    def _classement_produits(self, n: int, df: pd.DataFrame) -> dict:
        vide = {
            "top_labels": [], "top_valeurs": [],
            "flop_labels": [], "flop_valeurs": [], "metrique": None,
            "raison": None,
        }
        p = self.colonnes.get("produit")
        if not p or df.empty:
            return {**vide, "raison": "sans_produit"}

        q = self.colonnes.get("quantite")
        if self.ca_disponible:
            metrique, serie = "CA", df.groupby(p)["CA"].sum()
        elif q:
            metrique, serie = "Quantité", df.groupby(p)[q].sum()
        else:
            return {**vide, "raison": "sans_produit"}

        base = {**vide, "metrique": metrique}
        serie = serie.dropna()
        if len(serie) < 2:
            return {**base, "raison": "un_seul_produit"}
        # Tous les produits au même score : le classement serait arbitraire.
        if serie.nunique() < 2:
            return {**base, "raison": "scores_identiques"}

        top, flop = serie.nlargest(n), serie.nsmallest(n)
        return {
            "top_labels": [str(i) for i in top.index],
            "top_valeurs": [round(float(v), 2) for v in top.values],
            "flop_labels": [str(i) for i in flop.index],
            "flop_valeurs": [round(float(v), 2) for v in flop.values],
            "metrique": metrique,
            "raison": None,
        }

    def prevoir_tendance(self, df: pd.DataFrame | None = None, horizon: int = 3) -> dict:
        """Projection par régression linéaire sur l'évolution du CA.

        Ajuste la droite y = a·x + b par moindres carrés sur la série
        mensuelle, mesure sa qualité (R²) puis extrapole sur `horizon`
        mois. Un R² faible signale une série trop irrégulière pour être
        projetée honnêtement.
        """
        vide = {
            "disponible": False, "pente": None, "r2": None, "unite": None,
            "sens": "stable", "projection_labels": [], "projection_valeurs": [],
        }
        serie = self.evolution_mensuelle(df)
        # Il faut au moins 3 points pour qu'une droite ait un sens.
        if len(serie) < 3:
            return vide

        valeurs = serie.values.astype(float)
        if not np.isfinite(valeurs).all() or np.ptp(valeurs) == 0:
            return vide

        # Axe numérique : vrais mois si l'index le permet, sinon les tranches.
        try:
            x = pd.PeriodIndex(serie.index, freq="M").asi8.astype(float)
            unite = "mois"
            etiquette = lambda i: str(pd.Period(ordinal=int(i), freq="M"))  # noqa: E731
        except (ValueError, TypeError):
            x = np.arange(len(serie), dtype=float)
            unite = "tranches"
            etiquette = lambda i: f"Part {int(i) + 1}"  # noqa: E731

        if np.ptp(x) == 0:
            return vide

        # Moindres carrés via lstsq (plus stable que polyfit, sans avertissement).
        matrice = np.vstack([x, np.ones_like(x)]).T
        (pente, ordonnee), *_ = np.linalg.lstsq(matrice, valeurs, rcond=None)

        predictions = matrice @ np.array([pente, ordonnee])
        ss_res = float(((valeurs - predictions) ** 2).sum())
        ss_tot = float(((valeurs - valeurs.mean()) ** 2).sum())
        r2 = 0.0 if ss_tot == 0 else 1 - ss_res / ss_tot
        r2 = float(min(max(r2, 0.0), 1.0))

        x_proj = x[-1] + np.arange(1, horizon + 1)
        projete = pente * x_proj + ordonnee

        return {
            "disponible": True,
            "pente": round(float(pente), 2),
            "r2": round(r2, 4),
            "unite": unite,
            "sens": "hausse" if pente > 0 else "baisse" if pente < 0 else "stable",
            "projection_labels": [etiquette(v) for v in x_proj],
            "projection_valeurs": [round(float(v), 2) for v in projete],
        }

    def correlations(self, df: pd.DataFrame | None = None, n: int = 4) -> dict:
        """Corrélations de Pearson entre les colonnes numériques.

        Met en évidence les liens cachés du jeu de données, par exemple
        « plus la quantité vendue monte, plus le CA monte » ou
        « les remises font baisser le panier moyen ».
        """
        df = self.df if df is None else df
        return self._agreger("correlations", df, (n,), lambda: self._correlations(df, n))

    def _correlations(self, df: pd.DataFrame, n: int) -> dict:
        vide = {"paires": [], "colonnes": []}
        numeriques = df.select_dtypes(include="number").dropna(axis=1, how="all")
        if df.empty or numeriques.shape[1] < 2:
            return vide

        matrice = numeriques.corr(method="pearson")
        colonnes = list(matrice.columns)
        paires = []
        for i, a in enumerate(colonnes):
            for b in colonnes[i + 1:]:
                r = matrice.loc[a, b]
                if pd.isna(r):
                    continue
                paires.append({
                    "a": str(a),
                    "b": str(b),
                    "valeur": round(float(r), 3),
                    "force": self._forcer_correlation(r),
                    "sens": "direct" if r >= 0 else "inverse",
                })
        paires.sort(key=lambda p: abs(p["valeur"]), reverse=True)
        return {"paires": paires[:n], "colonnes": [str(c) for c in colonnes]}

    @staticmethod
    def _forcer_correlation(r: float) -> str:
        """Qualificatif lisible d'un coefficient de Pearson."""
        a = abs(r)
        if a >= 0.7:
            return "forte"
        if a >= 0.4:
            return "modérée"
        if a >= 0.2:
            return "faible"
        return "négligeable"

    # ------------------------------------------------------------------
    # Dispersion (nuage de points)
    # ------------------------------------------------------------------

    def nuage_points(
        self, df: pd.DataFrame | None = None, max_points: int = 600
    ) -> dict:
        """Nuage de points de la paire de colonnes la plus corrélée.

        Le couple est choisi sur toute la matrice de corrélation, **hors
        « CA »** : comme il vaut prix × quantité, le corréler à l'un de ses
        facteurs ne dirait qu'une tautologie. Le coefficient r est calculé
        sur la totalité des couples exploitables, la droite de régression
        sur l'échantillon affiché.
        """
        df = self.df if df is None else df
        return self._agreger(
            "nuage", df, (max_points,), lambda: self._nuage_points(df, max_points)
        )

    def _nuage_points(self, df: pd.DataFrame, max_points: int = 600) -> dict:
        vide = {
            "disponible": False, "x_nom": "", "y_nom": "",
            "x": [], "y": [], "r": None, "force": "négligeable",
            "pente": None, "droite": None, "x_min": None, "x_max": None,
            "total": 0, "echantillon": 0,
        }
        numeriques = df.select_dtypes(include="number")
        candidats = [
            c for c in numeriques.columns
            if str(c).upper() != "CA" and int(numeriques[c].notna().sum()) >= 4
        ]
        if len(candidats) < 2:
            return dict(vide)

        matrice = numeriques[candidats].corr(method="pearson")
        meilleure = None
        for i, a in enumerate(candidats):
            for b in candidats[i + 1:]:
                r = matrice.loc[a, b]
                if pd.isna(r):
                    continue
                if meilleure is None or abs(float(r)) > abs(meilleure[2]):
                    meilleure = (a, b, float(r))
        if meilleure is None:
            return dict(vide)

        a, b, r = meilleure
        couples = df[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
        total = int(len(couples))
        if total < 3:
            return dict(vide)
        if total > max_points:
            # Échantillonnage systématique : un pas régulier parcourt toute
            # la plage — un simple `iloc[:max_points]` ne montrerait que le
            # début du fichier.
            pas = total / max_points
            couples = couples.iloc[[int(i * pas) for i in range(max_points)]]

        x = couples[a].to_numpy(dtype=float)
        y = couples[b].to_numpy(dtype=float)
        resultat = dict(vide)
        resultat.update({
            "disponible": True,
            "x_nom": str(a), "y_nom": str(b),
            "x": [round(float(v), 3) for v in x],
            "y": [round(float(v), 3) for v in y],
            "r": round(r, 3),
            "force": self._forcer_correlation(r),
            "x_min": round(float(x.min()), 3),
            "x_max": round(float(x.max()), 3),
            "total": total,
            "echantillon": int(len(x)),
        })

        # Droite de régression (moindres carrés) : sans variation de x,
        # il n'y a pas de droite à tracer.
        if np.ptp(x) > 0:
            matrice_x = np.vstack([x, np.ones_like(x)]).T
            (pente, ordonnee), *_ = np.linalg.lstsq(matrice_x, y, rcond=None)
            resultat["pente"] = round(float(pente), 3)
            resultat["droite"] = [
                round(float(pente * resultat["x_min"] + ordonnee), 3),
                round(float(pente * resultat["x_max"] + ordonnee), 3),
            ]
        return resultat

    def detecter_anomalies(self, df: pd.DataFrame | None = None) -> dict:
        """Valeurs aberrantes sur le CA (règle IQR : 1,5 × écart interquartile)."""
        df = self.df if df is None else df
        return self._agreger("anomalies", df, (), lambda: self._detecter_anomalies(df))

    def _detecter_anomalies(self, df: pd.DataFrame) -> dict:
        if not self.ca_disponible or len(df) < 4:
            return {"total": 0, "colonnes": [], "lignes": []}
        q1, q3 = df["CA"].quantile([0.25, 0.75])
        iqr = q3 - q1
        suspect = df[(df["CA"] < q1 - 1.5 * iqr) | (df["CA"] > q3 + 1.5 * iqr)]
        apercu = self.apercu(suspect.sort_values("CA", ascending=False), n=6)
        apercu["total"] = int(len(suspect))
        return apercu

    # ------------------------------------------------------------------
    # Synthèse en langage naturel
    # ------------------------------------------------------------------

    def resume(self, df: pd.DataFrame | None = None) -> str:
        """Raconte les données en 3 à 6 phrases lisibles (langage naturel).

        Plutôt que d'aligner des chiffres, le résumé dit ce qui compte :
        le niveau général, la tendance, la catégorie et le produit qui
        tirent le jeu, puis les points à surveiller. Chaque phrase n'est
        produite que si l'information existe réellement : un fichier sans
        date n'évoque pas de tendance, un fichier sans catégorie n'en
        parle pas. Le résultat tient compte du filtre appliqué.
        """
        df = self.df if df is None else df

        def nombre(v, decimales: int = 0) -> str:
            """Formatage français : 12 345,6 (espace de millier, virgule)."""
            texte = f"{v:,.{decimales}f}"
            return texte.replace(",", " ").replace(".", ",")

        if df.empty:
            return "Aucune ligne ne correspond à ces filtres."

        k = self.kpis(df)
        phrases: list[str] = []

        # --- 1. Le niveau général ---
        if k["ca_total"] is not None:
            phrase = (
                f"Sur {nombre(k['nb_ventes'])} ventes, le chiffre d'affaires atteint "
                f"{nombre(k['ca_total'], 2)} DT"
            )
            if k["panier_moyen"]:
                phrase += f", pour un panier moyen de {nombre(k['panier_moyen'], 2)} DT"
            phrases.append(phrase + ".")
        else:
            phrases.append(
                f"{nombre(k['nb_ventes'])} lignes analysées, mais aucun chiffre d'affaires "
                "calculable : aucune colonne de prix exploitable n'a été détectée."
            )

        # --- 2. La période couverte (calculée sur les lignes retenues) ---
        d = self.colonnes.get("date")
        if d and df[d].notna().any():
            debut = df[d].min().strftime("%d/%m/%Y")
            fin = df[d].max().strftime("%d/%m/%Y")
            phrases.append(f"La période couverte s'étend du {debut} au {fin}.")

        # --- 3. La tendance et sa fiabilité ---
        tendance = self.prevoir_tendance(df)
        if tendance["disponible"]:
            ouverture = {
                "hausse": "La tendance est à la hausse",
                "baisse": "La tendance est à la baisse",
                "stable": "Le chiffre d'affaires reste stable",
            }[tendance["sens"]]
            dernier = tendance["projection_valeurs"][-1]
            horizon = (
                "les trois prochains mois" if tendance["unite"] == "mois"
                else "les tranches à venir"
            )
            phrase = f"{ouverture} : à cette allure, {horizon} devraient atteindre {nombre(dernier, 2)} DT"
            r2 = tendance["r2"]
            if r2 is not None:
                jugement = (
                    "solide" if r2 >= 0.7
                    else "à confirmer" if r2 >= 0.4
                    else "trop irrégulière pour être sûre"
                )
                phrase += f", avec une fiabilité {jugement} (R² = {nombre(r2, 2)})"
            phrases.append(phrase + ".")

        # --- 4. Les catégories qui tirent le jeu ---
        categories = self.par_categorie(df)
        total_cat = float(categories.sum())
        if len(categories) >= 2 and total_cat > 0:
            part = float(categories.iloc[0]) / total_cat * 100
            phrases.append(
                f"La catégorie « {categories.index[0]} » domine avec {nombre(part)} % du "
                f"chiffre d'affaires, devant « {categories.index[-1]} » qui ferme la marche."
            )
        elif len(categories) == 1:
            phrases.append(f"Le fichier ne contient qu'une seule catégorie : « {categories.index[0]} ».")

        # --- 5. Le produit star et le retardataire ---
        classement = self.classement_produits(1, df)
        top = self.top_produits(1, df)
        if len(top):
            metrique = classement.get("metrique") or "CA"
            unite = "DT" if metrique == "CA" else "unités"
            valeur = nombre(float(top.iloc[0]), 2) if metrique == "CA" else nombre(int(top.iloc[0]))
            phrases.append(f"Le produit star est « {top.index[0]} » avec {valeur} {unite}.")
        if classement.get("raison") is None and classement["flop_labels"]:
            phrases.append(
                f"À l'inverse, « {classement['flop_labels'][0]} » ferme la marche : "
                "c'est le premier candidat à revoir."
            )

        # --- 6. Les anomalies à surveiller ---
        anomalies = self.detecter_anomalies(df)
        if anomalies["total"]:
            n = anomalies["total"]
            phrases.append(
                f"{n} opération{'s' if n > 1 else ''} {'sortent' if n > 1 else 'sort'} nettement "
                "de l'habitude et méritent un coup d'œil."
            )

        # --- 7. Le caractère partiel de l'analyse ---
        if self.tronque:
            phrases.append(
                f"Attention : le fichier dépasse la limite analysable, seules les "
                f"{nombre(LIMITE_LIGNES)} premières lignes ont été prises en compte."
            )

        return " ".join(phrases)

    # ------------------------------------------------------------------
    # Filtrage, aperçu, export
    # ------------------------------------------------------------------

    @staticmethod
    def _date_souple(valeur) -> pd.Timestamp | None:
        """Interprète une date venue de l'utilisateur sans jamais lever.

        `debut` et `fin` arrivent d'une requête HTTP : une saisie erronée
        (« pasunedate », un tableau, un nombre…) ne doit pas planter l'API.
        La borne est alors ignorée, comme si elle n'avait pas été fournie.
        """
        if not valeur:
            return None
        try:
            date = pd.to_datetime(valeur, errors="coerce")
        except (TypeError, ValueError, OverflowError):
            return None
        # Hors scalaire (liste, Series) : on ne sait pas comparer, on ignore.
        if not isinstance(date, pd.Timestamp):
            return None
        return None if pd.isna(date) else date

    def filtrer(self, categorie: str | None = None,
                debut: str | None = None, fin: str | None = None) -> pd.DataFrame:
        """Sous-ensemble du dataframe correspondant à ces filtres (mémorisé).

        Le dashboard rappelle `filtrer()` avec les mêmes paramètres à chaque
        clic de pagination : inutile de reconstruire le dataframe à chaque fois.
        Le dataframe renvoyé est partagé — à traiter en lecture seule.
        """
        cle = (categorie or "", debut or "", fin or "")
        try:
            df = self._memo_filtres.get(cle)
        except TypeError:
            # Paramètre non hachable (?debut=a&debut=b remonte une liste) :
            # pas de mémoïsation possible, mais le filtrage doit marcher.
            return self._filtrer_brut(categorie, debut, fin)
        if df is None:
            df = self._filtrer_brut(categorie, debut, fin)
            if len(self._memo_filtres) >= self.TAILLE_MEMO:
                self._vider_memo()
            self._memo_filtres[cle] = df
        return df

    def _filtrer_brut(self, categorie: str | None,
                      debut: str | None, fin: str | None) -> pd.DataFrame:
        df = self.df
        c = self.colonnes.get("categorie")
        if c and categorie and categorie != "Toutes":
            # `astype(str)` transforme chaque NaN en la chaîne « nan » : sans
            # l'exclusion des valeurs manquantes, une catégorie nommée « nan »
            # (ou demandée dans l'URL) attraperait toutes les lignes vides.
            serie = df[c]
            df = df[serie.notna() & serie.astype(str).eq(categorie)]
        d = self.colonnes.get("date")
        if d:
            borne_debut = self._date_souple(debut)
            borne_fin = self._date_souple(fin)
            if borne_debut is not None:
                df = df[df[d] >= borne_debut]
            if borne_fin is not None:
                df = df[df[d] <= borne_fin]
        return df

    def apercu(self, df: pd.DataFrame | None = None, n: int = 12, page: int = 1) -> dict:
        """Aperçu paginé : `n` lignes à partir de la page `page` (1-indexée).

        Renvoie aussi la position courante pour que l'interface puisse
        afficher « Page 2 sur 7 » et désactiver les boutons aux extrémités.
        """
        df = self.df if df is None else df
        total = len(df)
        pages = max(1, -(-total // n))  # division entière arrondie vers le haut
        page = min(max(1, int(page)), pages)

        vue = df.iloc[(page - 1) * n: page * n].copy()
        for col in vue.columns:
            if pd.api.types.is_datetime64_any_dtype(vue[col]):
                vue[col] = vue[col].dt.strftime("%d/%m/%Y")
        vue = vue.astype(object).where(vue.notna(), "—")
        return {
            "colonnes": list(vue.columns),
            "lignes": vue.values.tolist(),
            "page": page,
            "pages": pages,
            "total": int(total),
        }

    def comparer_periodes(self, p1_debut, p1_fin, p2_debut, p2_fin, categorie=None) -> dict:
        """Compare deux périodes : CA, ventes et panier moyen, avec variation en %.

        Les deux périodes doivent faire la même durée pour être comparables ;
        un avertissement est renvoyé sinon.
        """
        k1 = self.kpis(self.filtrer(categorie=categorie, debut=p1_debut, fin=p1_fin))
        k2 = self.kpis(self.filtrer(categorie=categorie, debut=p2_debut, fin=p2_fin))

        def variation(a, b):
            """Variation de a vers b en %. None si indéfini."""
            if a in (None, 0) or b is None:
                return None
            return round((b - a) / a * 100, 1)

        d1 = self._date_souple(p1_debut)
        d2 = self._date_souple(p2_debut)
        f1 = self._date_souple(p1_fin)
        f2 = self._date_souple(p2_fin)
        duree1 = (f1 - d1).days if d1 is not None and f1 is not None else None
        duree2 = (f2 - d2).days if d2 is not None and f2 is not None else None

        # Deux mois n'ont jamais le même nombre de jours : on n'exige donc pas
        # une durée identique, seulement qu'elles ne soient pas très différentes.
        comparable = False
        if duree1 is not None and duree2 is not None:
            ecart = abs(duree1 - duree2)
            plus_courte = max(1, min(duree1, duree2))
            comparable = ecart <= 7 or ecart / plus_courte <= 0.15

        # Une saisie illisible est ignorée par le filtrage : on n'en renvoie
        # donc rien (sinon le navigateur afficherait « Invalid Date »).
        def echo(valeur, analyse):
            return str(valeur) if analyse is not None else ""

        return {
            "periode_1": {
                "debut": echo(p1_debut, d1), "fin": echo(p1_fin, f1),
                "ca": k1["ca_total"], "ventes": k1["nb_ventes"],
                "panier": k1["panier_moyen"], "lignes": duree1,
            },
            "periode_2": {
                "debut": echo(p2_debut, d2), "fin": echo(p2_fin, f2),
                "ca": k2["ca_total"], "ventes": k2["nb_ventes"],
                "panier": k2["panier_moyen"], "lignes": duree2,
            },
            "variations": {
                "ca": variation(k1["ca_total"], k2["ca_total"]),
                "ventes": variation(k1["nb_ventes"], k2["nb_ventes"]),
                "panier": variation(k1["panier_moyen"], k2["panier_moyen"]),
            },
            "comparable": comparable,
        }

    def date_rapport(self) -> str:
        """Date du jour formatée en français pour les rapports."""
        from datetime import date

        mois = [
            "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre",
        ]
        dujour = date.today()
        return f"{dujour.day} {mois[dujour.month - 1]} {dujour.year}"

    def options_filtres(self) -> dict:
        c = self.colonnes.get("categorie")
        d = self.colonnes.get("date")
        categories = sorted(self.df[c].dropna().astype(str).unique().tolist()) if c else []
        plage = None
        if d and self.df[d].notna().any():
            plage = {
                "debut": self.df[d].min().strftime("%Y-%m-%d"),
                "fin": self.df[d].max().strftime("%Y-%m-%d"),
            }
        return {"categories": categories, "plage": plage}

    def export(self, df: pd.DataFrame | None = None, fmt: str = "csv") -> BytesIO:
        df = (self.df if df is None else df).copy()
        buf = BytesIO()
        if fmt == "excel":
            df.to_excel(buf, index=False)
        else:
            df.to_csv(buf, index=False, encoding="utf-8-sig")
        buf.seek(0)
        return buf
