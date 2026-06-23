from flask import Blueprint, render_template

ai_advice_bp = Blueprint("ai_advice", __name__)

@ai_advice_bp.route("/ai_advice")
def ai_advice():
    return render_template("ai_advice.html")
