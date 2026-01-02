import re
from typing import Dict, Optional

import ollama
from pieces import rechercher_piece
from order import save_lead

MODEL = "deepseek-r1:7b"

SYSTEM = """
Tu es AutoTurbo, assistant professionnel de magasin de pièces auto.
Tu réponds TOUJOURS en français.
Règles STRICTES :
- 1 seule phrase courte (max 14 mots).
- Pas d’explication, pas de raisonnement, pas de guillemets.
- Ton poli, direct, style vendeur pro.
- Si l'utilisateur n’a pas l’info : accepte et passe à l’étape suivante.
- Tes questions doivent être claires et orientées action.
"""

GREETINGS = {"salut", "bonjour", "bonsoir", "hello", "salam", "hi"}
RESET_WORDS = {"reset", "recommencer", "nouvelle demande", "vider"}

NO_INFO_WORDS = {
    "je ne l ai pas", "je ne l'ai pas", "non", "aucune", "pas disponible",
    "je sais pas", "je ne sais pas", "nn", "nop", "j ai pas", "jai pas"
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

FLOW = [
    ("motif", "Demande le motif : commande, suivi de commande, ou SAV."),
    ("immat", "Demande l’immatriculation du véhicule, ou accepte “je ne l’ai pas”."),
    ("chassis", "Demande le numéro de châssis (VIN), ou accepte “je ne l’ai pas”."),
    ("piece", "Demande la pièce recherchée (ex: turbo, filtre huile, plaquettes frein)."),
    ("type_piece", "Demande le type de pièce (neuf/original/occasion/avant/arrière) ou accepte “je ne sais pas”."),
    ("marque", "Demande la marque du véhicule."),
    ("modele", "Demande le modèle du véhicule."),
    ("annee", "Demande l’année du véhicule."),
    ("coordonnees", "Demande téléphone ou email pour rappel et suivi."),
]

def new_slots() -> Dict[str, Optional[str | int | bool]]:
    return {
        "_step": 0,
        "_lead_saved": False,
        "_lead_id": None,
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

# ---------- OLLAMA (100% réponses) ----------
def _clean_one_sentence(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^question\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"^réponse\s*:\s*", "", s, flags=re.I)
    s = s.strip().strip("“”\"' ")

    # garde la dernière ligne non vide
    lines = [l.strip() for l in s.splitlines() if l.strip()]
    if not lines:
        return ""

    out = lines[-1].strip().strip("“”\"' ")
    # coupe si trop long
    if len(out) > 160:
        out = out[:160].rsplit(" ", 1)[0]
    return out

import time

def llm_say(instruction: str, slots: dict) -> str:
    """
    100% Ollama si possible.
    Si Ollama ne répond pas (erreur / vide / timeout), on renvoie un message FIXE (pas Ollama).
    """
    ctx = {
        "step": slots.get("_step"),
        "motif": slots.get("motif"),
        "immat": slots.get("immat"),
        "chassis": slots.get("chassis"),
        "piece": slots.get("piece"),
        "type_piece": slots.get("type_piece"),
        "marque": slots.get("marque"),
        "modele": slots.get("modele"),
        "annee": slots.get("annee"),
        "coordonnees": slots.get("coordonnees"),
    }

    prompt = (
        "Réponds avec UNE seule phrase (max 14 mots), style vendeur pro.\n"
        "Aucune explication.\n"
        f"Contexte: {ctx}\n"
        f"Instruction: {instruction}"
    )

    fallback_fixed = "Désolé, service IA indisponible. Réessayez dans un instant."

    start = time.time()
    timeout_sec = 6  # ✅ tu peux mettre 4..10

    while True:
        # ✅ Timeout global
        if time.time() - start > timeout_sec:
            return fallback_fixed

        try:
            resp = ollama.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                options={
                    "temperature": 0.1,
                    "num_predict": 60,
                    "stop": ["Okay", "I need", "Reason", "Réflexion", "Thinking:"],
                },
            )

            msg = resp.get("message", {}) if isinstance(resp, dict) else {}
            content = (msg.get("content") or "").strip()
            thinking = (msg.get("thinking") or "").strip()

            out = _clean_one_sentence(content) or _clean_one_sentence(thinking)

            # ✅ si vide => retente jusqu’au timeout
            if out:
                return out

        except Exception:
            # ✅ si erreur => retente jusqu’au timeout
            continue


# ---------- Extract / update ----------
def extract_year(text: str) -> Optional[int]:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if not m:
        return None
    y = int(m.group(1))
    return y if 1980 <= y <= 2030 else None

def extract_piece(text: str) -> Optional[str]:
    t = text.lower()
    for k, v in PIECES_KNOWN.items():
        if k in t:
            return v
    return None

def extract_type_piece(text: str) -> Optional[str]:
    t = text.lower()
    return text.strip() if any(w in t for w in TYPE_WORDS) else None

def extract_contact(text: str) -> Optional[str]:
    tel = re.search(r"\b0\d{9}\b", text)
    email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    if tel or email:
        return text.strip()
    return None

def next_key(slots: dict) -> Optional[str]:
    step = int(slots.get("_step", 0) or 0)
    if step < 0:
        step = 0
    if step >= len(FLOW):
        return None
    return FLOW[step][0]

def update_slots(slots: dict, raw_text: str) -> None:
    raw = raw_text.strip()
    t = raw.lower()
    step = int(slots.get("_step", 0) or 0)
    key = next_key(slots)

    if key == "motif":
        if "commande" in t:
            slots["motif"] = "commande"; slots["_step"] += 1
        elif "suivi" in t:
            slots["motif"] = "suivi"; slots["_step"] += 1
        elif "sav" in t:
            slots["motif"] = "sav"; slots["_step"] += 1
        return

    if key == "immat":
        slots["immat"] = "UNKNOWN" if t in NO_INFO_WORDS else raw
        slots["_step"] += 1
        return

    if key == "chassis":
        slots["chassis"] = "UNKNOWN" if t in NO_INFO_WORDS else raw
        slots["_step"] += 1
        return

    if key == "piece":
        p = extract_piece(raw)
        if p:
            slots["piece"] = p; slots["_step"] += 1
        return

    if key == "type_piece":
        if t in NO_INFO_WORDS:
            slots["type_piece"] = "UNKNOWN"; slots["_step"] += 1
            return
        tp = extract_type_piece(raw)
        if tp:
            slots["type_piece"] = tp; slots["_step"] += 1
        return

    if key == "marque":
        if len(raw.split()) <= 2:
            slots["marque"] = raw.title(); slots["_step"] += 1
        return

    if key == "modele":
        if any(c.isdigit() for c in raw):
            slots["modele"] = raw; slots["_step"] += 1
        return

    if key == "annee":
        y = extract_year(raw)
        if y:
            slots["annee"] = y; slots["_step"] += 1
        return

    if key == "coordonnees":
        c = extract_contact(raw)
        if c:
            slots["coordonnees"] = c; slots["_step"] += 1
        return

def is_complete(slots: dict) -> bool:
    required = ["motif", "piece", "marque", "modele", "annee", "coordonnees"]
    return all(slots.get(k) not in (None, "") for k in required)

def finish_url(lead_id: str) -> str:
    return f"http://127.0.0.1:5000/checkout/{lead_id}"

def final_stock_sentence(slots: dict) -> str:
    row = rechercher_piece(slots["piece"], slots["marque"], slots["modele"], slots["annee"])
    if not row:
        return "Annonce l’indisponibilité et propose un appel vendeur."
    return "Annonce dispo + prix + stock, très court."

def process_message(text: str, slots: dict):
    raw = (text or "").strip()
    if not isinstance(slots, dict) or "_step" not in slots:
        slots = new_slots()

    t = raw.lower()

    # RESET (100% Ollama)
    if t in RESET_WORDS:
        slots = new_slots()
        return llm_say("Confirme la réinitialisation et demande le motif.", slots), slots

    # GREETING (100% Ollama)
    if t in GREETINGS:
        return llm_say("Salue brièvement et demande le motif.", slots), slots

    # Update
    update_slots(slots, raw)

    # Next question (100% Ollama)
    key = next_key(slots)
    if key is not None:
        instr = dict(FLOW).get(key, "Pose la prochaine question.")
        return llm_say(instr, slots), slots

    # Complete => save lead then give link (100% Ollama)
    if is_complete(slots):
        if not slots.get("_lead_saved"):
            lead_id = save_lead(slots)
            slots["_lead_saved"] = True
            slots["_lead_id"] = str(lead_id)

        url = finish_url(slots["_lead_id"])
        return llm_say(f"Confirme l’enregistrement et donne ce lien: {url}", slots), slots

    # Stock response (100% Ollama)
    return llm_say(final_stock_sentence(slots), slots), slots
