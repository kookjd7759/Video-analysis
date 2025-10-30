from flask import Flask, Response

app = Flask(__name__)

@app.route("/")
def hello():
    return "Cloudflare success !"

@app.route("/stream")
def stream():
    def generate():
        count = 0
        while True:
            yield f"data: HI! {count}\n\n"
            count += 1

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
