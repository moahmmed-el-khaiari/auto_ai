import re
from typing import Optional, Dict, Any

import ollama
from pieces import rechercher_piece

MODEL = "deepseek-r1:7b"

SYSTEM = """
Tu es un vendeur professionnel de pièces auto.
Règles:
- Tu poses des questions courtes si une info manque (marque, modèle, année, pièce).
- Tu n'inventes jamais de prix ou de stock.
- Quand on te donne une FICHE_STOCK, tu réponds uniquement avec ces infos.
- Si la pièce n'est pas trouvée, tu dis que tu dois vérifier avec un vendeur humain.
Réponses en français, ton poli et direct.
"""

KNOWN_BRANDS = [
    "Renault", "Volkswagen", "Peugeot", "Dacia",
    "Toyota", "Ford", "Hyundai", "Kia", "BMW", "Mercedes"
]

KNOWN_MODELS = [
    "Clio 4", "Golf 6", "208", "Logan", "Sandero"
]


# ---------- NORMALISATION ----------

def normalize_text(text: str) -> str:
    # Support: "turbo,Renault,Clio_4,2017"
    text = text.strip()
    text = text.replace(",", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


# ---------- EXTRACTION ----------

def extract_year(text: str) -> Optional[int]:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    return int(m.group(1)) if m else None


def extract_brand(text: str) -> Optional[str]:
    for brand in KNOWN_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", text, flags=re.IGNORECASE):
            return brand
    return None


def extract_model(text: str) -> Optional[str]:
    for model in sorted(KNOWN_MODELS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(model)}\b", text, flags=re.IGNORECASE):
            return model

    m = re.search(r"\b(clio\s*\d)\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).title().replace("  ", " ")

    return None


def extract_piece(text: str) -> Optional[str]:
    t = text.lower()
    if "turbo" in t:
        return "turbo"
    if "filtre" in t and ("huile" in t or "d'huile" in t):
        return "filtre huile"
    if "plaquette" in t:
        return "plaquettes frein"
    return None


# ---------- MÉMOIRE CONVERSATIONNELLE (ÉTAPE 1) ----------

State = Dict[str, Optional[Any]]

def new_state() -> State:
    return {"piece": None, "marque": None, "modele": None, "annee": None}


def update_state(state: State, text: str) -> None:
    """Complète la mémoire avec les infos trouvées dans ce message."""
    p = extract_piece(text)
    b = extract_brand(text)
    m = extract_model(text)
    y = extract_year(text)

    if p is not None:
        state["piece"] = p
    if b is not None:
        state["marque"] = b
    if m is not None:
        state["modele"] = m
    if y is not None:
        state["annee"] = y


def missing_fields(state: State) -> list[str]:
    """Retourne la liste des infos manquantes."""
    missing = []
    if state["piece"] is None:
        missing.append("la pièce")
    if state["marque"] is None:
        missing.append("la marque")
    if state["modele"] is None:
        missing.append("le modèle")
    if state["annee"] is None:
        missing.append("l'année")
    return missing


def ask_next_question(state: State) -> str:
    """Pose UNE question courte sur l’info la plus importante manquante."""
    missing = missing_fields(state)
    if not missing:
        return ""

    # Une seule question à la fois (plus naturel)
    return f"Pouvez-vous préciser {missing[0]} ?"


# ---------- LLM (robuste pour deepseek-r1) ----------

def llm_reply(user_text: str, fiche_stock: Optional[str] = None) -> str:
    messages = [{"role": "system", "content": SYSTEM}]
    if fiche_stock is not None:
        messages.append({"role": "system", "content": fiche_stock})
    messages.append({"role": "user", "content": user_text})

    resp = ollama.chat(
        model=MODEL,
        messages=messages,
        options={
            "temperature": 0.1,
            "num_predict": 240,
        },
    )

    # Ollama python peut renvoyer dict ou objet (Message)
    if isinstance(resp, dict):
        msg = resp.get("message")
        if isinstance(msg, dict):
            content = (msg.get("content") or "").strip()
            thinking = (msg.get("thinking") or "").strip()
        else:
            content = ""
            thinking = ""
    else:
        msg = getattr(resp, "message", None)
        content = (getattr(msg, "content", "") or "").strip() if msg else ""
        thinking = (getattr(msg, "thinking", "") or "").strip() if msg else ""

    # Deepseek-r1 met parfois la réponse dans thinking
    return content if content else (thinking if thinking else "Je n’ai pas pu générer une réponse.")


def build_fiche_stock(row: dict) -> str:
    return (
        "FICHE_STOCK (source: stock.csv)\n"
        f"- piece: {row['piece']}\n"
        f"- marque: {row['marque']}\n"
        f"- modele: {row['modele']}\n"
        f"- annee: {row['annee']}\n"
        f"- prix_DH: {row['prix']}\n"
        f"- stock: {row['stock']}\n"
        "Règle: répondre uniquement à partir de FICHE_STOCK."
    )


# ---------- MAIN ----------

def main():
    print("🤖 AutoTurbo IA (mémoire active) — tape 'exit' pour quitter.\n")

    state = new_state()

    while True:
        raw = input("Client > ").strip()
        if not raw:
            continue
        if raw.lower() == "exit":
            break

        user = normalize_text(raw)

        # Mise à jour mémoire
        update_state(state, user)

        # Si manque des infos, poser la prochaine question
        if missing_fields(state):
            print("IA >", ask_next_question(state), "\n")
            continue

        # Toutes les infos sont prêtes => recherche stock
        row = rechercher_piece(state["piece"], state["marque"], state["modele"], state["annee"])

        if row:
            fiche = build_fiche_stock(row)
            answer = llm_reply(
                "Réponds au client avec disponibilité, prix, stock, et propose un lien de commande en option.",
                fiche_stock=fiche
            )
        else:
            answer = llm_reply(
                "La pièce demandée n'est pas disponible dans le stock. "
                "Réponds poliment sans inventer et propose de vérifier avec un vendeur."
            )

        print("IA >", answer, "\n")

        # OPTION : reset la mémoire après une réponse complète (pour une nouvelle demande)
        # Décommente si tu veux repartir à zéro après chaque réponse.
        # state = new_state()


if __name__ == "__main__":
    main()
