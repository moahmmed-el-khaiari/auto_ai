import csv
from typing import Union

CSV_PATH = "data/stock.csv"

def rechercher_piece(
    piece: str,
    marque: str,
    modele: str,
    annee: Union[int, str]   # 👈 accepte int OU str
):
    piece = piece.strip().lower()
    marque = marque.strip().lower()
    modele = modele.strip().lower()
    annee = str(annee).strip()   # 👈 normalisation OK

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (
                row["piece"].strip().lower() == piece
                and row["marque"].strip().lower() == marque
                and row["modele"].strip().lower() == modele
                and row["annee"].strip() == annee
            ):
                return row
    return None
