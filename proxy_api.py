from flask import Flask, request, jsonify
import requests

app = Flask(__name__)
SURAT_URL = "https://api01.suratkargo.com.tr/api/OrtakBarkodOlustur"

@app.route("/etiket", methods=["POST"])
def etiket_proxy():
    try:
        data = request.json
        response = requests.post(SURAT_URL, json=data, timeout=25)
        return (response.text, response.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
