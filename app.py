from flask import Flask, render_template, request, jsonify, session
from flask import redirect
from assistant_slots import new_slots, process_message

app = Flask(__name__)
app.secret_key = "autoturbo-secret-key-change-me"  # nécessaire pour session


@app.get("/")
def index():
    # init slots en session
    if "slots" not in session:
        session["slots"] = new_slots()
    return render_template("index.html")


@app.post("/chat")
def chat():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()

    slots = session.get("slots") or new_slots()
    answer, slots = process_message(text, slots)

    # sauvegarde mémoire (slots)
    session["slots"] = slots

    return jsonify({"answer": answer})

@app.get("/checkout/<lead_id>")
def checkout(lead_id):
    return render_template("checkout.html", lead_id=lead_id)

@app.post("/reset")
def reset():
    session["slots"] = new_slots()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
