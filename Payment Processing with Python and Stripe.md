# Payment Processing with Python and Stripe

In this article I am going to cover how to use the payment processing giant Stipe along with the Python programing language and Flask web framework to create online credit card charges for a fictitious Saas application called Rando Number. Stripe is a payment processing company that provides a superb platform for integrating payment processing in software applications of all sorts minimizing many of the complexities and risks associated with accepting payments.  

### Demo Application

As I alluded to earlier, the applicationt that I will be using to demonstrate Stripe's features for accepting credit card payments is going is one that generates random numbers on a pay as you go basis.  By implementing Stripe in this application user can purchase one or more credits to be used for generating a random number.  The technology stack for this application will be kept as simple as possble since the focus here is on learning how to interact with Stripe to collect online credit card payments.

To begin I create three directories, two of which are called randonumber, one inside the other along with the deepest one being named templates. Following this I create a Python 3.6 virtual environment called venv like sos.

```
mkdir -p randonumber/randonumber/templates
cd randonumber
python -m venv venv
source venv/bin/activate
```

Next up I install the following Python libraries inside a Python 3.6 virtual environment.

* Flask: this is the main Flask web framework library
* Flask-Script: Flask extension library that provides interactive shell commands
* Flask-Migrate: Flask extension that manages database schema migrations
* Flask-Login: Flask extension that provides common authentication functionality
* python-dotenv: simple library to utilize enviroment variables stored in a .env file
* stripe: Stripe SDK for interacting with Stripe API's

```
pip install Flask Flask-SQLAlchemy Flask-Migrate Flask-Script Flask-Login python-dotenv stripe
```

With the necessary tools installed I can now move on to building the app.  I'll begin with scaffolding out a server.py file to live at randonumber/randonumber/server.py and contain all the app's actual server code all in one modest size file (because Flask is amazing like that).

To start I'll describe the basic setup and model definition code then move onto the view functions after initializing the database.


```python
# server.py
from datetime import datetime
import os
import random

from flask import Flask, render_template, jsonify, url_for, redirect, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

from dotenv import load_dotenv
load_dotenv(verbose=True, 
            dotenv_path=os.path.join(
                            os.path.dirname(
                            os.path.dirname(
                            os.path.abspath(__file__))), '.env'))

# create and configure Flask application object
app = Flask(__name__)
app.config.update(
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

... more to follow
```

In the code above I have begun by importing a slew of modules that I'll be working with.  After that I created and configured the Flask, Flask-SQLAlchemy, and Flask-Login objects.  Before I too further I need to explain the significance of this bit of code.

```
from dotenv import load_dotenv
load_dotenv(verbose=True, 
            dotenv_path=os.path.join(
                            os.path.dirname(
                            os.path.dirname(
                            os.path.abspath(__file__))), '.env'))

```

This uses the python-dotenv library's load_dotenv function to parse a .env file located at randonumber/.env which is one directory above the server.py file.  It is in this file that I will place configurationsettings that will get loaded as environement variables accessable via the `os` module. These environment variables direct things like where and what the database will be called along with Stripe's API access keys that to be discussed in just a bit.

```
# .env

DATABASE_URI='sqlite:///randonumber.sqlite3'
APP_SECRET_KEY='mysecret'
STRIPE_SECRET_KEY='comingsoon'
STRIPE_PUB_KEY='comingsoon'
```

Now back to server.py, at the end there are three models that are defined: User, Purchase and Number. User is fairly straight forward and maintains data about registered users that are interacting with the randonumber app. Purchase will be a local mapping of Stripe charges that are created and, Number serves as a history of the random numbers a user generates.

For tranlating these models to a SQLite database I utilize the Flask-Script and Flask-Migrate extension libraries. Together I am able to initialize the database and setup tracking of the model changes using another custom Python module named manage.py that will live in randonumber/randonumber/manage.py as shown below.

```
# manage.py

from flask_script import Manager  
from flask_migrate import Migrate, MigrateCommand

from server import app, db, User, Purchase, Number

migrate = Migrate(app, db)  
manager = Manager(app)

# provide a migration utility command
manager.add_command('db', MigrateCommand)

# Python interpreter shell with application context
@manager.shell
def shell_ctx():  
    return dict(app=app,
                db=db,
                User=User,
                Purchase=Purchase,
                Number=Number)

if __name__ == '__main__':  
    manager.run()
```

Again the code is annotated with comments to indicate it intent such as adding a management command to handle migrations as well as a Python interpretter shell that will contain an application context which is great for experimenting with objects directly in the interpreter. 

Back at the command line, in the same directory as the manage.py script, I can initialize the migration tooling and database like so.

```sh
python manage.py db init
python manage.py db migrate
python manage.py db upgrade
```

With the models defined and mapped to a database I can move on with server.py and add the view functions for registering, authenticating, displaying a home page as well as a user profile page and, producing random numbers for users.

```
# server.py

... everything from above



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
    db.session.add(user)
    user.account_credits = 3
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
    return render_template('buy_credits_standard.html', stripe_key=os.getenv('STRIPE_PUB_KEY'))

@app.route('/buy-credits', methods=('POST',))
@login_required
def buy_credits():
    '''TODO:
       - call stripe api to lookup or create customer
       - call stripe api to create charge
       - map charge to purchase
    '''
    return redirect(url_for('user_profile'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5555)

```

Ok, the view functions (AKA controllers) above serve as the intermediary between the html views (to be described shortly) and the resources the application uses like the models just defined and the functionality provided by Stripe.

To start I will make a base.html layout template that loads some assets like CSS and JavaScript along with a navbar used ubiquitously throughout the application. All html views are going to live in a directory called templates located at randonumber/randonumber/templates

```
<!-- base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <title>Rando Number</title>
  <script src="https://www.paypalobjects.com/api/checkout.js"></script>
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css" integrity="sha384-Gn5384xqQ1aoWXA+058RXPxPg6fy4IWvTNh0E263XmFcJlSAwiGgFAW/dAiS6JXm" crossorigin="anonymous">
  <script
  src="https://code.jquery.com/jquery-3.3.1.min.js"
  integrity="sha256-FgpCb/KJQlLNfOu91ta32o/NMZxltwRo8QtmkMRdAu8="
  crossorigin="anonymous"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.12.9/umd/popper.min.js" integrity="sha384-ApNbgh9B+Y1QKtv3Rn7W3mgPxhU9K/ScQsAP7hUibX39j7fakFPskvXusvfa0b4Q" crossorigin="anonymous"></script>
  <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.min.js" integrity="sha384-JZR6Spejh4U02d8jOt6vLEHfe/JQGiRRSQQxSfFWpi1MquVdAyjUar5+76PVCmYl" crossorigin="anonymous"></script>
</head>
<body>
  <nav class="navbar navbar-expand-lg navbar-light bg-light">
    <a class="navbar-brand" href="{{ url_for('home') }}">
      Rando Number
    </a>
    <button class="navbar-toggler" data-toggle="collapse" data-target="#nav-supporting-links">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="nav-supporting-links">
      <div class="navbar mr-auto">
        <div class="d-flex justify-content-end">
          {% if current_user.is_authenticated %}
          <a href="{{ url_for('logout') }}" class="btn btn-primary my-2">Logout</a>
          {% endif %}
        </div>
      </div>
    </div>
  </nav>

  <div class="container">
    {% block content %}{% endblock %}
  </div>

</body>
</html>
```

The base.html view defines a navbar that shows a logout button if a user is authenticated. The base template file also pulls in the Bootstrap css framework and JQuery javascript library. The last major component defines a content block which is where the inheriting view's will inject their content.

Next up I add the home.html view that is served when visiting the base base / route served by the `home` view function.

```
<!-- home.html -->
{% extends 'base.html' %}

{% block content %}
<div class="jumbotron">
  <div class="container">
    <h1 class="display-4">Random Number Generator</h1>
    <p class="lead">This application creates the randomly generated numbers for all your life's needs.</p>

    <p class="lead">
      <p>
        {% if not current_user.is_authenticated %}
        <a class="btn btn-primary btn-lg" href="{{ url_for('login') }}">Sign In</a>
        <a class="btn btn-info btn-lg" href="{{ url_for('register') }}">Register</a>
        {% else %}
        <a href="{{ url_for('user_profile') }}" class="btn btn-primary btn-lg">User Profile</a>
        <a href="{{ url_for('show_buy_credits') }}" class="btn btn-info btn-lg" >Buy Credits</a>
        {% endif %}
      </p>
    </p>
  </div>
</div>

<div class="container" style="margin-top: 100px;">
  <div class="row justify-content-center">
    <div class="col-6">
      <div class="card text-center">
        <div class="card-header">Your Random Number</div>
        <div class="card-body">
          <h2 class="card-title" id="number" style="font-size: 60px; padding: 80px 50px;">###</h2>
        </div>
        <div class="card-footer text-muted">
          {% if not current_user.is_authenticated %}
          <a href="{{ url_for('login') }}" class="btn btn-primary">Login To Get Your Number</a>
          {% else %}
          <button class="btn btn-primary" id="getnumber">Get Your Number</button>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
</div>

<script>
  $(function(){
    $('#getnumber').click(function(){
      return $.ajax({
        method: 'get',
        url: '/api/v1/number/',
        dataType: 'json'
      })
      .then(function(response){
        if (response.status === 'SUCCESS') {
          $('#number').html(response.number)
        }
      })
    })
  })
</script>

{% endblock %}
```

This is essentially the main view of the application which provides links for loggin in or registering for non-authenicated users.  For authenticated users there are links to take them to their profile page or a page for purchasing "credits" for generating random numbers.

Towards the middle of home.html is a card component that displays an area where authenticated users with credits can generate random numbers or, in the case of non-authenticated users a link that takes them to a login screen.

The complete home page is shown below.

<!-- randonumber-home.png -->

Next up is the registration page which displays a simple form for collecting a user's email and password for later authenticating.

```
<!-- register.html -->

{% extends 'base.html' %}

{% block content %}

<div class="container" style="margin-top: 110px;">
  <div class="row justify-content-center">
    <div class="col-md-8">
      <h2>Login</h2>
      <form action="{{ url_for('register') }}" method="POST">
        <div class="form-group">
          <label for="email">Email</label>
          <input type="email" class="form-control" id="email" name="email" required>
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input type="password" class="form-control" id="password" name="password" required>
        </div>
        <div class="form-group">
            <label for="passwordcheck">Re-enter Password</label>
            <input type="password" class="form-control" id="passwordcheck" name="passwordcheck" required>
          </div>
        <button type="submit" class="btn btn-primary">Register</button>
      </form>
    </div>
  </div>
</div>

<script>
$(function(){
  $('form').onSubmit(function(evt){
    if ($('#password').val() !== $('#passwordcheck').val()) {
      evt.preventDefault()
      alert('Passwords do not match')
    }
  })
})
</script>

{% endblock %}
```

Here is the registeration page.

<!-- randonumber-register.png -->

Following the register.html page is the login.html page. Again, this is simply a form to collect email (username) and password to send to the server for authentication.

```
<!-- login.html -->
{% extends 'base.html' %}

{% block content %}

<div class="container" style="margin-top: 110px;">
  <div class="row justify-content-center">
    <div class="col-md-8">
      <h2>Login</h2>
      <form action="{{ url_for('login') }}" method="POST">
        <div class="form-group">
          <label for="email">Email</label>
          <input type="email" class="form-control" id="email" name="email" required>
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input type="password" class="form-control" id="password" name="password" required>
        </div>
        <button type="submit" class="btn btn-primary">Login</button>
        <a href="{{ url_for('register') }}" class="btn btn-info">Register</a>
      </form>
    </div>
  </div>
</div>

{% endblock %}
```

The login page.

<!-- randonumber-login.png -->

Now for the user profile page. This page will display the current credits balance of an authenticated user along with a history of their purchases.

```
<!-- user_profile.html -->

{% extends 'base.html' %}

{% block content %}

<div class="card">
  <h5 class="card-header">Credits Remaining</h5>
  <div class="card-body">
    <p class="card-text">{{ user.account_credits }}</p>
    <a href="#" class="btn btn-primary">Buy More Credits</a>
  </div>
</div>

<div class="card">
    <h5 class="card-header">Purchase History</h5>
    <div class="card-body">
      <table class="table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Amount</th>
          </tr>
        </thead>
        <tbody>
          {% for purchase in purchases %}
          <tr>
            <td>{{ purchase.created_at }}</td>
            <td>{{ purchase.amount }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

{% endblock %}
```

User profile page.

<!-- randonumber-user-profile.png -->

Ok, if you have been following along then at this point in time you should be able to fire up the local Flask development server and register a user to get a feel for the application. Note that in the view function for the /register url I have hard coded `user.account_credits = 3` so that newly registered users can have a go at generating a few random numbers before having to pay anything so, you should be able to generate a few random ones also.

To start the local dev server simply do use the following.

```
python server.py
 * Serving Flask app "server" (lazy loading)
 * Environment: production
   WARNING: Do not use the development server in a production environment.
   Use a production WSGI server instead.
 * Debug mode: off
 * Running on http://0.0.0.0:5577/ (Press CTRL+C to quit)
```

*** Don't worry I have not forgotten about the buy credits view and functionality.  That is coming up shortly.

### Setting Up Stripe Account and SDK

At this point I need to visit https://stripe.com and register for an account. Once logged in I click the link "Get your API keys" from the home page of the Stripe dashboard (being sure that I remain in the test data side). In the API keys page there are two rows of keys in the middle of the screen. One for client side usage named Publishable key and another for server side usage called Secret key as show below.

<!-- randonumber-stripe-access-keys.png -->

I unhide the secret key, copy it, then go to the .env file created previously and paste it's value for the environment variable named STRIPE_SECRET_KEY. I do the same for the publishable key. With the Stripe access keys set in the .env file I am able to import the stripe Python SDK into server.py and configure it immediatelys after the `load_dotenv(...)` function call. I will need to restart the dev server to reload the new settings in .env

```
# server.py

... ommitting other imports

import stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

... ommitting everything below
```

### Adding Standard Payment Handling

I begin with the client side of things using Stripe's checkout feature.  Stripe's checkout feature provides two methods for collecting a user's payment information. The first is to use Stripe's standard script tag with data-attributes that describe the qualities of the purchase while the second employs customized JavaScript handling.

To start I will cover the standard method by creating a view template inside the templates directorys calling it buy_credits_standard.html and code it up as shown below.

```
<!-- buy_credits_standard.html -->

{% extends 'base.html' %}

{% block content %}

<div class="container" style="margin-top: 110px;">
  <div class="row justify-content-center">
    <div class="col-md-8">
      <h2>Buy Credits</h2>

      <form action="{{ url_for('buy_credits') }}" method="POST">
        <script
          src="https://checkout.stripe.com/checkout.js" class="stripe-button"
          data-key="{{ stripe_key }}"
          data-amount="100"
          data-name="Rando Number"
          data-description="Random number credits"
          data-image="https://stripe.com/img/documentation/checkout/marketplace.png"
          data-locale="auto">
        </script>
      </form>

    </div>
  </div>
</div>

{% endblock %}
```

What this does is loads some JS from Stripe and places a rather nofrills button on the page that says Pay with Card. 

<!-- randonumber-stripe-standard-payment-button.png -->s

When clicked a popup is displayed that can be used to collect the user's email, credit card number, expiration date, and cv code. When the popup's Pay button is clicked an AJAX call is made to Stripe securely storing the user's payment data on their servers, verifying that it is a valid payment method then, returns a payment token in a post request to the url provided for the form's action attribute ('/buy-credits' in my case) all while shielding the randonumber app from the sensitive payment data.

<!-- randonumber-stripe-payment-popup.png -->

Now back in server.py I locate the `buy_credits` view function and modify it to handle executing the transaction on the server. The data that is posted to the server by the Stripe popup listed below. 

* stripeToken: this is the payment token that Stripe has associated with the customer and their payment data which I will use to create a Stripe Customer object with and execute the transaction
* stripeTokenType: in this case it will be of type card
* stripeEmail: this is the email the customer provided in the popup

I access the posted data via the `form` attribute of the Flask `request` object which I then use to update the users stripe ID, create the Stripe Customer object (if one does not already exist), then create a Stripe Charge object to execute the transaction. Once the transaction is executed I map it to a Purchase object and update the `User.account_credits` field as shown below.

```
# server.py

... ommitting other content


@app.route('/buy-credits', methods=('POST',))
@login_required
def buy_credits():
    customer = None
    if current_user.stripe_id:
        try:
            customer = stripe.Customer.retrieve(current_user.stripe_id)
        except:
            print(f'error fetching stripe customer {current_user.email}')

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
        charge =  stripe.Charge.create(customer=customer.id,
                              amount=100, # stripe deals with money in cents
                              currency='usd',
                              description='Random number credits')
        purchase = Purchase(payment_id=charge.id,
                            payer_id=customer.id,
                            service_package='credits',
                            amount=1.00,
                            user_id=current_user.id)
        db.session.add(purchase)
        current_user.account_credits += purchase.amount
        db.session.commit()
    except:
        print(f'Error creating stripe charge for user {current_user.email}')
        return abort(404)

    return redirect(url_for('user_profile'))
```

As you can see from the code above I am using the stripe SDK library's `Customer` and `Charge` classes. For the `stripe.Customer` class I am first checking to see if the local User object has a previously saved stripe_id. If `User.stripe_id` is truthy then I attempt to fetch an instance of `stripe.Customer` using the retrieve method with that ID.  If the fetch fails or the user object doesn't have a stripe_id then I use `stripe.Customer.create(...)` to generate a customer instance given the email and payment token posted by the Stripe popup.

Upon successful creation or fetching of the `stripe.Customer` object I proceed to generate a charge object with `stripe.Charge.create(...)`.  One thing worth mentioning here is the use of an `amount` value of 100 which is the purchase amount in cents.  Stripe requires charge amounts to be represented in cents in both the client script tag data-attribute `data-amount="100"` and the call to the `stripe.Charge.create(...)` method.

Upon successful return of a `stripe.Charge` object I create a `Purchase` object mapping the charge ID as well as the customer ID value and purchase amount to it before finally incrementing the `User.account_credits` field.

### Better Payment Handling with Custom JavaScript

While the functionality in the previous section works fine for many fixed price single item purchases it is at best a clunky experience for variable priced and / or variable unit purchases. For example, in our case it might be a reasonable idea to allow a user to purchase multiple credits at a time or charge different prices for credits depending on the quantity purchased. Such a feature would require some funky data-attribute swapping tied to user inputs that, quite frankly, I don't even want to demonstrate in fear someone will actually put it to use.  Instead, I will demonstrate how to use the checkout.js Stripe javascript library along with proper form inputs and AJAX methods to provide a much smoother user experience and coherent code set.

To begin I create a new html view file named buy_credits_custom.html and source the Stripe checkout.js library near to the top of the content block.  Then I add a form with the same POST action url along with a number input that allows the user to specify the quantity of credits to purchase complete with a Buy Now button. I want to point out that the Buy Now button has been placed outside of the form element so that the form is not submitted when clicked.

```
<!-- buy_credits_custom.html -->

{% extends 'base.html' %}

{% block content %}
<script src="https://checkout.stripe.com/checkout.js"></script>
<div class="container" style="margin-top: 110px;">
  <div class="row justify-content-center">
    <div class="col-md-8">
      <h2>Buy Credits</h2>

      <form action="{{ url_for('buy_credits') }}" method="POST">
        <div class="form-group">
          <label for="credits">Credits</label>
          <input type="number" class="form-control" id="credits" name="credits" required>
        </div>
        <input type="hidden" id='stripeToken' name='stripeToken' value=''>
        <input type="hidden" id='stripeEmail' name='stripeEmail' value=''>
      </form>
      <button class="btn btn-primary" id='stripe-checkout'>Buy Now</button>
    </div>
  </div>
</div>

<script>
var handler = StripeCheckout.configure({
  key: '{{ stripe_key }}',
  image: 'https://stripe.com/img/documentation/checkout/marketplace.png',
  locale: 'auto',
  token: function(token) {
    $('#stripeToken').val(token.id)
    $('#stripeEmail').val(token.email)
    $('form').submit()
  }
});

$('#stripe-checkout').click(function(e) {
  // Open Checkout with further options:
  handler.open({
    name: 'Rando Number',
    description: 'Random Number Credits',
    amount: $('#credits').val() * 100
  });
  e.preventDefault();
});

// Close Checkout on page navigation:
window.addEventListener('popstate', function() {
  handler.close();
});
</script>

{% endblock %}
```

At the bottom of the file I have added a script tag with some JS that controls the Stripe checkout.js workflow.  First a `StripeCheckout` object is configured and instantiated by specifying the publishable key which is passed down from the server via a Jinja template variable `stripe_key`, then the default Stripe checkout image is specified (this can be customized by adding another image is desired).  The `locale` is set to 'auto' indicating that it should be detected based off the browser. The last configuration is a callback function for the `token` field that is called after Stripe validates the payment method passing a object called `token` in this example.  I use the `token` object to set the payment token value of a hidden `stripeToken` input as well as a `stripeEmail` hidden input for the email then submit the form using JQuery.

Next I have configured a click event handler on the Buy Now button which calls the open method on the previously created `StripeCheckout` object which initiates the payment data collection popup. The final bit of code is a global event listener for the `popstate` event that the browser emits indicating that the url is changing which I use to signal to `StripeCheckout` that it should close it's popup.

Alright, that takes care of the client side handlinn so, I will move on to the server side changes.

Back in the `buy_credits` view function I need to add a line of code to grab the submitted credits form value, cast it to an integer. For the sake of clarity I multipy it by the price of one credit ($1.00).  Lastly, I need to update the amount parameter of the `stripe.Charge.create(...)` method call to multiply this amount by 100 to convert to cents again and cast that value to an int.

```
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
```

With these modifications in place users can now indicate the number of credits that they would like to buy when making a purchase.

### Conclusion

In this article I have demonstrated how to use the widely popular payment processor Stripe to accept one time charges with credit cards using the Stripe Python SDK and the Flask web framework with a touch of JavaScript.  If you would like to learn more about payment processing with Stripe please checkout my Udemy course [Payment Processing with Stripe and Python]().  In this course I cover additional topics like:

* managing payment sources by adding, updating and, deleting credit cards associated with a Stripe customer
* Creating a charges without reasking a customer to enter their payment details when they are already on file
* Creating recurring subscription payments with and without trial periods
* Upgrading, downgrading, and cancelling subscriptions
* Querying the String REST API to collect and report sales data

As always, thanks for reading and don't be shy about commenting or critiquing below.