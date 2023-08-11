from flask import Flask, render_template
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API token value from environment variable
token = os.getenv("BOT_TOKEN")

app = Flask(__name__)


@app.route('/')
def index():
    return render_template("index.html", title="Budget control - Home page")


@app.route('/auth')
def auth():
    return render_template("auth.html", title="Budget control - Authorization")


@app.route('/household')
def household():
    return render_template("household.html", title="Budget control - Household")


if __name__ == "__main__":
    app.run(debug=True)  # change on False before upload on server