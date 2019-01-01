# server.py
from datetime import datetime
import os
import random

from flask import Flask, render_template, jsonify, url_for, redirect, request, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

from dotenv import load_dotenv
load_dotenv(verbose=True, 
            dotenv_path=os.path.join(
                            os.path.dirname(
                            os.path.dirname(
                            os.path.abspath(__file__))), '.env'))

import stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# create and configure Flask application object
app = Flask(__name__)
app.config.update(
    DEBUG=True,
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URI'),
    SQLALCHEMY_TRACK_MODIFICATIONS=True,
    SECRET_KEY=os.getenv('APP_SECRET_KEY')
)

# create Flask-SQLAlchmey ORM object
db = SQLAlchemy(app)

# create Login-Manager object, assign a view function for login,
# and create a utility function for it to use to lookup users by id
login = LoginManager(app)
login.login_view = 'login'
@login.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Custom authentication error exception
class InvalidCredentialsException(Exception):
    '''custom auth exception'''

    def __init__(self):
        Exception.__init__(self, 'Invalid authentication credentials')

# models
class User(UserMixin, db.Model):
    '''users registered with the app'''
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    account_type = db.Column(db.String(50), default='credits')
    account_credits = db.Column(db.Integer, default=0)
    stripe_id = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    purchases = db.relationship('Purchase', backref='user', lazy=True)
    numbers = db.relationship('Number', backref='user', lazy=True)

    def __init__(self, email, password):
        self.email = email
        self.password = generate_password_hash(password)

    @classmethod
    def authenticate(cls, email, password):
        user = cls.query.filter_by(email=email).first()
        if not user:
            raise InvalidCredentialsException()
        if not check_password_hash(user.password, password):
            raise InvalidCredentialsException()
        login_user(user)
        return user


class Purchase(db.Model):
    '''purchases in mapped to stripe charges'''
    __tablename__ = 'purchases'

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.String(200))
    payer_id = db.Column(db.String(200))
    service_package = db.Column(db.String(50), default='credits')
    amount = db.Column(db.Numeric(asdecimal=False, decimal_return_scale=None), default=1.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

class Number(db.Model):
    '''Numbers a user has generated'''
    __tablename__ = 'numbers'

    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

# view functions
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register')
def show_register():
    return render_template('register.html')

@app.route('/register', methods=['POST'])
def register():
    password = request.form.get('password')
    password_check = request.form.get('passwordcheck')
    if not password or password != password_check:
        return redirect(url_for('login'))
    
    email = request.form.get('email')
    if not email:
        return redirect(url_for('login'))

    user = User(email=email, password=password)
    user.account_credits = 3
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return render_template('home.html', user=user)

@app.route('/login')
def show_login():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    try:
        user = User.authenticate(email, password)
    except InvalidCredentialsException as e:
        print(e)
        return redirect(url_for('login'))
    return render_template('home.html', user=user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/user-profile')
@login_required
def user_profile():
    purchases = Purchase.query.filter_by(user_id=current_user.id).all()
    return render_template('user_profile.html', purchases=purchases, user=current_user)

@app.route('/api/v1/number/')
@login_required
def random_number():
    if current_user.account_credits > 0:
        number = Number(value=random.randrange(0, 9), user_id=current_user.id)
        current_user.account_credits -= 1
        db.session.add(number)
        db.session.commit()
        return jsonify({'number': number.value, 'status': 'SUCCESS'})
    return jsonify({'status': 'FAILURE'})

@app.route('/buy-credits')
@login_required
def show_buy_credits():
    return render_template('buy_credits_custom.html', stripe_key=os.getenv('STRIPE_PUB_KEY'))

@app.route('/buy-credits', methods=('POST',))
@login_required
def buy_credits():
    customer = None
    if current_user.stripe_id:
        try:
            customer = stripe.Customer.retrieve(current_user.stripe_id)
        except:
            print(f'Error fetching stripe customer {current_user.email}')

    if not customer:
        try:
            customer = stripe.Customer.create(
                email=request.form['stripeEmail'],
                source=request.form['stripeToken'])
            current_user.stripe_id = customer.id
        except:
            print(f'Error creating stripe customer {current_user.email}')
            return abort(404)

    try:
        amount = int(request.form['credits']) * 1.00
        charge =  stripe.Charge.create(customer=customer.id,
                              amount=int(amount * 100), # stripe deals with money in cents
                              currency='usd',
                              description='Random number credits')
        purchase = Purchase(payment_id=charge.id,
                            payer_id=customer.id,
                            service_package='credits',
                            amount=amount,
                            user_id=current_user.id)
        db.session.add(purchase)
        current_user.account_credits += purchase.amount
        db.session.commit()
    except:
        print(f'Error creating stripe charge for user {current_user.email}')
        return abort(404)

    return redirect(url_for('user_profile'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5577)
