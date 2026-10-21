from flask import Flask, send_file
from pathlib import Path
import map

app = Flask(__name__)

@app.route("/")
def home():
    html_file = Path(__file__).parent / "mahalla_map.html"

    if not html_file.exists():
        map.main()

    return send_file(html_file)

map.main()