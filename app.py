from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import random
import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

app = Flask(__name__)

# use os.getenv to read the invisible file
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect here if not logged in

# --- Database Models ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    # In a real app, store a hash or use Redis for OTPs with expiry
    current_otp = db.Column(db.String(6), nullable=True)

class StudySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    hours = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    # Link session to a specific user
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']

        # Check if user exists, if not create them (Auto-Register)
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email)
            db.session.add(user)
            db.session.commit()

        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))
        user.current_otp = otp
        db.session.commit()

        # SIMULATION: Print OTP to Console (Instead of sending email)
        print(f"------------------------------------------")
        print(f"EMAIL SENT TO {email}: YOUR OTP IS {otp}")
        print(f"------------------------------------------")

        # Store email in session strictly for the verify step
        session['pending_email'] = email
        return redirect(url_for('verify'))

    return render_template('login.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        entered_otp = request.form['otp']
        email = session.get('pending_email')

        user = User.query.filter_by(email=email).first()

        if user and user.current_otp == entered_otp:
            # OTP Matches! Log them in.
            login_user(user)
            # Clear the OTP for security
            user.current_otp = None
            db.session.commit()
            return redirect(url_for('index'))
        else:
            flash('Invalid OTP. Please try again.')

    return render_template('verify.html')

@app.route('/', methods=['GET', 'POST'])
@login_required # Protects this route
def index():
    if request.method == 'POST':
        subject = request.form['subject']
        hours = request.form['hours']

        # Attach the current logged-in user's ID
        new_session = StudySession(subject=subject, hours=hours, user_id=current_user.id)
        db.session.add(new_session)
        db.session.commit()
        return redirect('/')

    # Filter: Show ONLY the current user's data
    sessions = StudySession.query.filter_by(user_id=current_user.id).order_by(StudySession.date.desc()).all()
    total_hours = sum(session.hours for session in sessions)

    return render_template('index.html', sessions=sessions, total_hours=total_hours, user=current_user)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    # Ensure user can only delete THEIR OWN sessions
    session_to_delete = StudySession.query.get_or_404(id)
    if session_to_delete.user_id == current_user.id:
        db.session.delete(session_to_delete)
        db.session.commit()
    return redirect('/')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)