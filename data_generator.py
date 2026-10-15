"""
Génère un jeu de données de démonstration pour DataVision.

Crée data/sample_sales.csv avec 5 000 ventes sur 6 mois (janvier–juin 2026),
en injectant volontairement quelques doublons et valeurs manquantes
pour montrer le nettoyage automatique de l'application.
"""

import os
import random

import pandas as pd

random.seed(42)

# Produit -> (catégorie, prix unitaire de référence)
CATALOGUE = {
    "PC portable": ("Informatique", 1800),
    "Écran 24 pouces": ("Informatique", 220),
    "Imprimante laser": ("Informatique", 380),
    "Souris": ("Accessoires", 25),
    "Clavier": ("Accessoires", 45),
    "Casque audio": ("Accessoires", 80),
    "Chaise de bureau": ("Bureau", 320),
    "Bureau assis-debout": ("Bureau", 750),
    "Lampe LED": ("Bureau", 40),
    "Stylo premium": ("Bureau", 8),
}

POIDS = [3, 4, 2, 15, 12, 8, 5, 2, 6, 20]  # fréquence d'achat
POIDS_MOIS = [10, 12, 14, 16, 20, 22]  # tendance à la hausse sur la période


def generer(nb_lignes: int = 5000) -> pd.DataFrame:
    produits = list(CATALOGUE)
    lignes = []
    for _ in range(nb_lignes):
        produit = random.choices(produits, weights=POIDS)[0]
        categorie, prix = CATALOGUE[produit]
        mois = random.choices(range(1, 7), weights=POIDS_MOIS)[0]
        jour = pd.Timestamp(year=2026, month=mois, day=1) + pd.Timedelta(
            days=random.randint(0, 27)
        )
        lignes.append({
            "Date": jour.strftime("%d/%m/%Y"),
            "Produit": produit,
            "Catégorie": categorie,
            "Quantité": random.randint(1, 12),
            "Prix": round(prix * random.uniform(0.9, 1.1), 2),
        })
    df = pd.DataFrame(lignes)

    # Défauts volontaires (nettoyés automatiquement par DataVision) :
    df = pd.concat([df, df.sample(40, random_state=1)], ignore_index=True)  # doublons
    for idx in random.sample(range(len(df)), 25):  # valeurs manquantes
        df.at[idx, "Catégorie"] = None
    return df


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    donnees = generer()
    donnees.to_csv("data/sample_sales.csv", index=False, encoding="utf-8-sig")
    print(f"Jeu de données créé : {len(donnees)} lignes -> data/sample_sales.csv")
