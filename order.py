import csv
import os
import uuid
from datetime import datetime
from typing import Dict, Any

LEADS_CSV = os.path.join("data", "leads.csv")

FIELDS = [
    "lead_id",
    "created_at",
    "motif",
    "immat",
    "chassis",
    "piece",
    "type_piece",
    "marque",
    "modele",
    "annee",
    "coordonnees",
    "status"
]

def ensure_file():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(LEADS_CSV):
        with open(LEADS_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()

def save_lead(slots: Dict[str, Any]) -> str:
    """
    Enregistre une demande et retourne lead_id
    """
    ensure_file()
    lead_id = uuid.uuid4().hex[:10]  # court et unique

    row = {
        "lead_id": lead_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "motif": slots.get("motif") or "",
        "immat": slots.get("immat") or "",
        "chassis": slots.get("chassis") or "",
        "piece": slots.get("piece") or "",
        "type_piece": slots.get("type_piece") or "",
        "marque": slots.get("marque") or "",
        "modele": slots.get("modele") or "",
        "annee": str(slots.get("annee") or ""),
        "coordonnees": slots.get("coordonnees") or "",
        "status": "NEW"
    }

    with open(LEADS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writerow(row)

    return lead_id
