# assistant.py
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

State = Dict[str, Optional[Any]]


# ---------- NORMALISATION ----------

def normalize_text(text: str) -> str:
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


# ---------- MÉMOIRE ----------

def new_state() -> State:
    return {"piece": None, "marque": None, "modele": None, "annee": None}


def update_state(state: State, text: str) -> None:
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
    missing = missing_fields(state)
    if not missing:
        return ""
    return f"Pouvez-vous préciser {missing[0]} ?"


# ---------- LLM ----------

def llm_reply(user_text: str, fiche_stock: Optional[str] = None) -> str:
    messages = [{"role": "system", "content": SYSTEM}]
    if fiche_stock is not None:
        messages.append({"role": "system", "content": fiche_stock})
    messages.append({"role": "user", "content": user_text})

    resp = ollama.chat(
        model=MODEL,
        messages=messages,
        options={"temperature": 0.1, "num_predict": 240},
    )

    # dict ou objet (Message)
    if isinstance(resp, dict):
        msg = resp.get("message")
        if isinstance(msg, dict):
            content = (msg.get("content") or "").strip()
            thinking = (msg.get("thinking") or "").strip()
        else:
            content, thinking = "", ""
    else:
        msg = getattr(resp, "message", None)
        content = (getattr(msg, "content", "") or "").strip() if msg else ""
        thinking = (getattr(msg, "thinking", "") or "").strip() if msg else ""

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


# ---------- MODE C (reset) + API UNIQUE POUR GUI ----------

RESET_WORDS = {"reset", "recommencer", "vider"}
RESET_PHRASES = {"nouvelle demande", "autre voiture", "nouveau véhicule"}


def process_user_input(raw: str, state: State) -> tuple[str, State]:
    """
    Entrée: texte client + état mémoire
    Sortie: réponse IA + nouvel état mémoire
    (Parfait pour GUI / Voice)
    """
    if not raw or not raw.strip():
        return "", state

    user = normalize_text(raw)
    u = user.lower()

    # ===============================
    # SALUTATION / PRÉSENTATION
    # ===============================
    greetings = {
        "salut", "bonjour", "bonsoir", "hello", "hi", "salam"
    }

    if u in greetings:
        return (
            "Bonjour 👋 Je suis AutoTurbo, votre assistant spécialisé en pièces auto.\n"
            "Dites-moi la pièce recherchée, la marque, le modèle et l’année du véhicule.",
            state
        )

    # ===============================
    # MODE C : RESET SUR COMMANDE
    # ===============================
    if u in RESET_WORDS or any(p in u for p in RESET_PHRASES):
        state = new_state()
        return (
            "D’accord ✅ Nouvelle demande.\n"
            "Indiquez la pièce, la marque, le modèle et l’année.",
            state
        )

    # ===============================
    # MISE À JOUR MÉMOIRE
    # ===============================
    update_state(state, user)

    # ===============================
    # QUESTIONS SI INFOS MANQUANTES
    # ===============================
    if missing_fields(state):
        return ask_next_question(state), state

    # ===============================
    # RECHERCHE DANS LE STOCK
    # ===============================
    row = rechercher_piece(
        state["piece"],
        state["marque"],
        state["modele"],
        state["annee"]
    )

    if row:
        fiche = build_fiche_stock(row)
        answer = llm_reply(
            "Réponds au client avec disponibilité, prix, stock, et propose un lien de commande en option.",
            fiche_stock=fiche
        )
        return answer, state

    # ===============================
    # PIÈCE NON TROUVÉE
    # ===============================
    answer = llm_reply(
        "La pièce demandée n'est pas disponible dans le stock. "
        "Réponds poliment sans inventer et propose de vérifier avec un vendeur."
    )
    return answer, state
