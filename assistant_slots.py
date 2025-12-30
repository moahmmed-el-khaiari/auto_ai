# assistant_slots.py
import re
from typing import Dict, Optional

import ollama
from pieces import rechercher_piece

MODEL = "deepseek-r1:7b"

SYSTEM = """
Tu es un assistant professionnel de magasin de pièces auto.
Tu réponds TOUJOURS en français.
IMPORTANT :
- Réponds UNIQUEMENT par la phrase finale à dire au client.
- AUCUNE explication.
- AUCUN raisonnement.
- UNE seule phrase courte (max 20 mots).
- Ton poli et professionnel.
"""

# -----------------------------
# CONFIG
# -----------------------------
GREETINGS = {"salut", "bonjour", "bonsoir", "hello", "salam", "hi"}
NO_INFO_WORDS = {
    "je ne l ai pas", "je ne l'ai pas", "non", "pas disponible",
    "aucune", "je sais pas", "je ne sais pas", "nn", "nop", "j ai pas", "jai pas"
}

PIECES_KNOWN = {
    "turbo": "turbo",
    "filtre huile": "filtre huile",
    "filtre d'huile": "filtre huile",
    "plaquettes": "plaquettes frein",
    "plaquettes frein": "plaquettes frein",
    "disques": "disques",
}

TYPE_WORDS = ["neuf", "occasion", "original", "adaptable", "avant", "arrière", "arriere"]

# -----------------------------
# SLOTS
# -----------------------------
def new_slots() -> Dict[str, Optional[str]]:
    return {
        "_step": 0,
        "motif": None,
        "immat": None,
        "chassis": None,
        "piece": None,
        "type_piece": None,
        "marque": None,
        "modele": None,
        "annee": None,
        "coordonnees": None,
    }

# -----------------------------
# OLLAMA (anti vide + retry)
# -----------------------------
def _clean_text(s: str) -> str:
    s = (s or "").strip()

    # supprime préfixes courants
    s = re.sub(r"^question\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"^réponse\s*:\s*", "", s, flags=re.I)

    # enlève guillemets et espaces
    s = s.strip().strip("“”\"' ")

    # prend la meilleure ligne "courte"
    lines = [l.strip() for l in s.splitlines() if l.strip()]
    for l in reversed(lines):
        l = l.strip("“”\"' ")
        # évite les phrases en anglais de reasoning
        if "okay" in l.lower() or "i need" in l.lower():
            continue
        if 3 <= len(l) <= 220:
            return l

    return ""

def llm_say(instruction: str, fallback: str) -> str:
    """
    Appelle Ollama et garantit une sortie non vide.
    fallback = phrase brute si le modèle renvoie vide.
    """
    prompt = (
        "Réponds par UNE seule phrase courte en français (max 20 mots).\n"
        "Sans explication, sans raisonnement.\n"
        f"{instruction}"
    )

    # 2 tentatives
    for _ in range(2):
        try:
            resp = ollama.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                options={
                    "temperature": 0.1,
                    "num_predict": 80,
                    # ⚠️ IMPORTANT: ne pas mettre "\n\n" ici
                    "stop": ["Okay", "I need", "Reason", "Réflexion", "Thinking:"],
                },
            )

            msg = resp.get("message", {}) if isinstance(resp, dict) else {}
            content = (msg.get("content") or "").strip()
            thinking = (msg.get("thinking") or "").strip()

            out = _clean_text(content) or _clean_text(thinking)
            if out:
                return out
        except Exception:
            pass

    # si toujours vide => fallback
    return fallback

# -----------------------------
# EXTRACTIONS
# -----------------------------
def extract_immat(text: str):
    m = re.search(r"\b\d{1,4}[-\s]?[A-Z][- \s]?\d{1,3}\b", text.upper())
    return m.group(0) if m else None

def extract_vin(text: str):
    m = re.search(r"\b[A-HJ-NPR-Z0-9]{17}\b", text.upper())
    return m.group(0) if m else None

def extract_year(text: str):
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if m:
        y = int(m.group(1))
        return y if 1980 <= y <= 2030 else None
    return None

def extract_contact(text: str):
    tel = re.search(r"\b0\d{9}\b", text)
    email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    if tel or email:
        return f"Téléphone: {tel.group(0) if tel else '—'} | Email: {email.group(0) if email else '—'}"
    return None

def extract_piece(text: str):
    t = text.lower()
    for k, v in PIECES_KNOWN.items():
        if k in t:
            return v
    return None

def extract_type_piece(text: str):
    t = text.lower()
    return text if any(w in t for w in TYPE_WORDS) else None

# -----------------------------
# FLOW (avec pointeur _step)
# -----------------------------
FLOW = [
    ("motif", "Commande, suivi de commande, ou SAV ?"),
    ("immat", "Avez-vous l’immatriculation du véhicule ?"),
    ("chassis", "Avez-vous le numéro de châssis (VIN) ?"),
    ("piece", "De quelle pièce avez-vous besoin ?"),
    ("type_piece", "Quel type de pièce souhaitez-vous ? (neuf/original/occasion/avant/arrière)"),
    ("marque", "Quelle est la marque du véhicule ?"),
    ("modele", "Quel est le modèle du véhicule ?"),
    ("annee", "Quelle est l’année du véhicule ?"),
    ("coordonnees", "Pouvez-vous me donner votre téléphone ou email ?"),
]

def next_question(slots):
    step = int(slots.get("_step", 0) or 0)
    step = max(0, step)
    if step >= len(FLOW):
        return None
    return FLOW[step][1]

# -----------------------------
# UPDATE SLOTS (par étape)
# -----------------------------
def update_slots(slots, text):
    raw = text.strip()
    t = raw.lower()
    step = int(slots.get("_step", 0) or 0)
    step = max(0, step)

    if step == 0:
        if "commande" in t:
            slots["motif"] = "commande"; slots["_step"] = 1
        elif "suivi" in t:
            slots["motif"] = "suivi"; slots["_step"] = 1
        elif "sav" in t:
            slots["motif"] = "sav"; slots["_step"] = 1
        return

    if step == 1:
        if t in NO_INFO_WORDS:
            slots["immat"] = "UNKNOWN"; slots["_step"] = 2; return
        imm = extract_immat(raw)
        if imm:
            slots["immat"] = imm; slots["_step"] = 2
        return

    if step == 2:
        if t in NO_INFO_WORDS:
            slots["chassis"] = "UNKNOWN"; slots["_step"] = 3; return
        vin = extract_vin(raw)
        if vin:
            slots["chassis"] = vin; slots["_step"] = 3
        return

    if step == 3:
        p = extract_piece(raw)
        if p:
            slots["piece"] = p; slots["_step"] = 4
        return

    if step == 4:
        if t in NO_INFO_WORDS:
            slots["type_piece"] = "UNKNOWN"; slots["_step"] = 5; return
        tp = extract_type_piece(raw)
        if tp:
            slots["type_piece"] = tp; slots["_step"] = 5
        return

    if step == 5:
        if len(raw.split()) <= 2 and raw[:1].isalpha():
            slots["marque"] = raw.title(); slots["_step"] = 6
        return

    if step == 6:
        if any(c.isalpha() for c in raw) and any(c.isdigit() for c in raw):
            slots["modele"] = raw; slots["_step"] = 7
        return

    if step == 7:
        y = extract_year(raw)
        if y:
            slots["annee"] = y; slots["_step"] = 8
        return

    if step == 8:
        c = extract_contact(raw)
        if c:
            slots["coordonnees"] = c; slots["_step"] = 9
        return

# -----------------------------
# FINAL ANSWER
# -----------------------------
def final_answer(slots):
    row = rechercher_piece(slots["piece"], slots["marque"], slots["modele"], slots["annee"])
    if not row:
        return "La pièce n’est pas disponible, voulez-vous une alternative ou une vérification vendeur ?"

    return (
        f"Pièce {row['piece']} disponible pour {row['marque']} {row['modele']} {row['annee']}, "
        f"prix {row['prix']} DH, stock {row['stock']} unités."
    )

# -----------------------------
# API
# -----------------------------
def process_message(text, slots):
    raw = (text or "").strip()
    if not raw:
        return "Écrivez votre demande, s’il vous plaît.", slots

    # sécurité: si session ancienne
    if "_step" not in slots:
        slots = new_slots()

    t = raw.lower()

    # reset
    if t in {"reset", "recommencer", "nouvelle demande"}:
        slots = new_slots()
        msg = llm_say("Dis: Mémoire réinitialisée. Commande, suivi de commande, ou SAV ?", "✅ Mémoire réinitialisée. Commande, suivi de commande, ou SAV ?")
        return msg, slots

    # salut
    if t in GREETINGS:
        msg = llm_say(
            "Présente-toi brièvement et demande: commande, suivi de commande, ou SAV ?",
            "Bonjour 👋 Commande, suivi de commande, ou SAV ?"
        )
        return msg, slots

    # update
    update_slots(slots, raw)

    # question suivante
    q = next_question(slots)
    if q:
        msg = llm_say(q, q)
        return msg, slots

    # réponse finale
    base = final_answer(slots)
    msg = llm_say(base, base)
    return msg, slots
