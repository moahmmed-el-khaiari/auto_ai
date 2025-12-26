from flask import Flask, render_template, request, jsonify, session
from assistant import new_state, process_user_input

app = Flask(__name__)
app.secret_key = "autoturbo-secret-key-change-me"  # nécessaire pour session

@app.get("/")
def index():
    # init session state
    if "state" not in session:
        session["state"] = new_state()
    return render_template("index.html")

@app.post("/chat")
def chat():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()

    state = session.get("state") or new_state()
    answer, new_state_obj = process_user_input(text, state)

    # sauvegarde mémoire dans la session
    session["state"] = new_state_obj

    return jsonify({"answer": answer})

@app.post("/reset")
def reset():
    session["state"] = new_state()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
