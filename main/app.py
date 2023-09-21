from flask import Flask, render_template, request, session, redirect, url_for, flash, abort
import os
import re
from datetime import timedelta
from dotenv import load_dotenv
from password_hashing import getting_hash, get_salt

# Database
from database_control import get_db, close_db_g, create_table_group, FDataBase

# Validators
from validators.registration import registration_validator, token_validator
from validators.login import login_validator
from validators.input_number import input_number

# Logging
from logging.handlers import RotatingFileHandler
from logging import Formatter
import logging


load_dotenv()  # Load environment variables from .env file

os.makedirs("logs", exist_ok=True)  # Creating a directory for later storing application logs there.

app = Flask(__name__)
app.config.from_object(__name__)

# Get the secret key to encrypt the Flask session from an environment variable
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
db_path = os.getenv("DATABASE")

app.config.update(dict(DATABASE=os.path.join(app.root_path, db_path)))

app.teardown_appcontext(close_db_g)  # Disconnects the database connection after a query

# session lifetime in browser cookies
app.permanent_session_lifetime = timedelta(days=14)  # timedelta from datetime module

app.config.from_object('config.DevelopmentConfig')
# -----------------------------------------------------------------------------
# Enabling, disabling and rotating logs.
# -----------------------------------------------------------------------------
handler = RotatingFileHandler(app.config['LOGFILE'], maxBytes=1000000, backupCount=1)
handler.setLevel(logging.DEBUG)
handler.setFormatter(Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
# logging.disable(logging.CRITICAL)  # Termination of logs
app.logger.addHandler(handler)


@app.route('/')
def homepage():
    return render_template("homepage.html", title="Budget control - Home page")


@app.route('/registration', methods=["GET", "POST"])
def registration():
    if request.method == "POST":

        username: str = request.form["username"]
        psw: str = request.form["password"]
        telegram_id: str = request.form["telegram-id"]
        token: str = request.form["token"]

        # If the token field is empty
        if len(request.form['token']) == 0:  # user creates a new group
            if registration_validator(username, psw, telegram_id):

                telegram_id: int = int(telegram_id)  # # If registration_validator is passed, then it is int
                psw_salt: str = get_salt()
                dbase = FDataBase(get_db())

                if user_token := dbase.create_new_group(telegram_id):

                    group_id: int = token_validator(user_token)
                    create_table_group(f"budget_{group_id}")

                    if dbase.add_user_to_db(username, psw_salt, getting_hash(psw, psw_salt), group_id, telegram_id):
                        app.logger.info(f"Successful registration: {username}. New group created: id={group_id}.")
                        flash("Registration completed successfully!", category="success")
                        flash(f"{username}, your token: {user_token}", category="success_token")

        # User is added to an existing group
        if len(token) == 32:
            if registration_validator(username, psw, telegram_id):
                if group_id := token_validator(token):  # new variable "group_id" (int)

                    telegram_id: int = int(telegram_id)  # # If registration_validator is passed, then it is int
                    dbase = FDataBase(get_db())
                    psw_salt: str = get_salt()

                    if dbase.add_user_to_db(username, psw_salt, getting_hash(psw, psw_salt), group_id, telegram_id):

                        # redirecting the user to a personal account (he already has a group token)
                        session["userLogged"] = username
                        app.logger.info(f"Successful registration: {username}. Group: id={group_id}.")
                        return redirect(url_for("household", username=session["userLogged"], token="token"))

                    else:
                        app.logger.info(f"Failed authorization  attempt: username = {username}, token = {token}.")
                        flash("Error creating user. Please try again and if the problem persists, "
                              "contact technical support.", category="error")
                else:
                    app.logger.info(f"The user entered an incorrect token: username = {username}, token = {token}.")
                    flash("There is no group with this token, please check the correctness of the entered data!",
                          category="error")

        # User made a mistake when entering the token
        if len(token) > 0 and len(token) != 32:
            app.logger.info(f"The user entered a token of incorrect length: {token}.")
            flash("Error - token length must be 32 characters", category="error")

    return render_template("registration.html", title="Budget control - Registration")


@app.route('/login', methods=["GET", "POST"])  # send password in POST request and in hash
def login():
    session.permanent = True

    if "userLogged" in session:  # If the client has logged in before
        app.logger.info(f"Successful authorization (cookies): {session['userLogged']}.")
        return redirect(url_for("household", username=session["userLogged"]))

    # here the POST request is checked and the presence of the user in the database is checked
    if request.method == "POST":
        username: str = request.form["username"]
        psw: str = request.form["password"]
        token: str = request.form["token"]
        dbase = FDataBase(get_db())
        psw_salt: str = dbase.get_salt_by_username(username)

        if psw_salt and login_validator(username, getting_hash(psw, psw_salt), token):

            session["userLogged"] = username
            dbase.update_user_last_login(username)
            app.logger.info(f"Successful authorization: {username}.")
            return redirect(url_for("household", username=session["userLogged"]))

        else:
            flash("Error. Please try again.", category="error")
        # request.args - GET, request.form - POST

    return render_template("login.html", title="Budget control - Login")


@app.route('/household/<username>', methods=["GET", "POST"])  # user's personal account
def household(username):
    if "userLogged" not in session or session["userLogged"] != username:
        abort(401)

    dbase = FDataBase(get_db())
    token: str = dbase.get_token_by_username(username)
    group_id: int = dbase.get_group_id_by_token(token)  # if token = "" -> group_id = 0 -> data = []

    if request.method == "POST":

        if "submit-button-1" in request.form:  # Processing the "Add to table" button for form 1
            income: str = request.form.get("income")
            income: int | bool = input_number(income)

            if not income:
                app.logger.error(f"Error adding income to database (household): table: budget_{group_id}, "
                                 f"username: {username}, income: {income}.")
                flash("Error", category="error")

            else:
                description_1 = request.form.get("description-1")

                if dbase.add_monetary_transaction_to_db(group_id, username, income, description_1):
                    app.logger.info(f"Successfully adding data to database (household): table: budget_{group_id}, "
                                    f"username: {username}, income: {income}, description: {description_1}.")
                    flash("Data added successfully.", category="success")
                else:
                    app.logger.info(f"Error adding data to database (household): table: budget_{group_id}, "
                                    f"username: {username}, income: {income}, description: {description_1}.")
                    flash("Error adding data to database.", category="error")

        elif "submit-button-2" in request.form:  # Processing the "Add to table" button for form 2
            expense: str = request.form.get("expense")
            expense: int | bool = input_number(expense)

            if not expense:
                app.logger.error(f"Error adding income to database (household): table: budget_{group_id}, "
                                 f"username: {username}, income: {expense}.")
                flash("Error", category="error")

            else:
                description_2 = request.form.get("description-2")

                if dbase.add_monetary_transaction_to_db(group_id, username, expense*(-1), description_2):
                    app.logger.info(f"Successfully adding data to database (household): table: budget_{group_id}, "
                                    f"username: {username}, expense: {expense}, description: {description_2}.")
                    flash("Data added successfully.", category="success")
                else:
                    app.logger.info(f"Error adding data to database (household): table: budget_{group_id}, "
                                    f"username: {username}, expense: {expense}, description: {description_2}.")
                    flash("Error adding data to database.", category="error")

    headers: list[str] = ["№", "Total", "Username", "Transfer", "DateTime", "Description"]
    data: list = dbase.select_data_for_household_table(group_id, 15)  # In case of error group_id == 0 -> data = []

    return render_template("household.html", title=f"Budget control - {username}",
                           token=token, username=username, data=data, headers=headers)


@app.route('/logout', methods=['GET'])
def logout():
    app.logger.info(f"Successful logout: {session['userLogged']}.")
    session.pop("userLogged", None)  # removing the "userLogged" key from the session (browser cookies)
    return redirect(url_for('homepage'))  # redirecting the user to another page, such as the homepage


@app.errorhandler(401)
def page_not_found(error):
    return render_template("error401.html", title="UNAUTHORIZED"), 401


@app.errorhandler(404)
def page_not_found(error):
    return render_template("error404.html", title="PAGE NOT FOUND"), 404


if __name__ == "__main__":
    app.run(debug=True)  # change on False before upload on server
