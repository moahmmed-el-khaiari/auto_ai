# main.py
from assistant import new_state, process_user_input

def main():
    print("🤖 AutoTurbo IA (mémoire active - Mode C) — tape 'exit' pour quitter.\n")
    print("💡 Astuce: tape 'autre voiture' ou 'nouvelle demande' pour recommencer.\n")

    state = new_state()

    while True:
        raw = input("Client > ").strip()
        if not raw:
            continue
        if raw.lower() == "exit":
            break

        answer, state = process_user_input(raw, state)

        if answer:
            print("IA >", answer, "\n")

if __name__ == "__main__":
    main()
