# ui_gui.py
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

from assistant import new_state, process_user_input


def launch_app():
    root = tk.Tk()
    root.title("AutoTurbo IA - GUI (Texte)")
    root.geometry("780x540")
    root.minsize(650, 450)

    # --- Zone chat (historique) ---
    chat = ScrolledText(root, wrap=tk.WORD, font=("Segoe UI", 10))
    chat.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
    chat.configure(state="normal")
    chat.insert(tk.END, "🤖 AutoTurbo IA (GUI)\n")
    chat.insert(tk.END, "💡 Tape 'autre voiture' ou 'nouvelle demande' pour recommencer.\n")
    chat.insert(tk.END, "👋 Exemple: turbo Renault Clio 4 2017\n\n")
    chat.configure(state="disabled")

    # --- Barre du bas (input + bouton) ---
    bottom = tk.Frame(root)
    bottom.pack(fill=tk.X, padx=12, pady=(0, 12))

    entry = tk.Entry(bottom, font=("Segoe UI", 12))
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    btn_send = tk.Button(bottom, text="Envoyer", font=("Segoe UI", 11))
    btn_send.pack(side=tk.LEFT, padx=(10, 0))

    # --- Mémoire conversationnelle ---
    state = new_state()

    def ui_write(line: str):
        chat.configure(state="normal")
        chat.insert(tk.END, line + "\n")
        chat.configure(state="disabled")
        chat.see(tk.END)

    def send():
        nonlocal state
        text = entry.get().strip()
        if not text:
            return

        entry.delete(0, tk.END)
        ui_write(f"Client > {text}")

        # Feedback visuel (Ollama peut être lent)
        ui_write("IA > ...")
        root.update_idletasks()

        answer, state = process_user_input(text, state)

        if answer:
            ui_write(f"IA > {answer}\n")
        else:
            ui_write("IA > (aucune réponse)\n")

    btn_send.config(command=send)
    entry.bind("<Return>", lambda e: send())
    entry.focus()

    root.mainloop()
