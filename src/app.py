import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import random
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
import json

# --- PATH CONFIGURATION (NEW) ---
# Get the base directory (the 'src' folder)
basedir = os.path.abspath(os.path.dirname(__file__))

# Point to the .env file in the parent directory (root)
load_dotenv(os.path.join(basedir, '../.env'))

app = Flask(__name__)

# --- CONFIG UPDATES ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Create the database in the ROOT folder (../study.db), not inside src
# This keeps your code separate from your data
db_path = os.path.join(basedir, '../study.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path

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

@app.route('/stats')
@login_required
def stats():
    # --- CHART 1: DAILY (Current Week: Mon-Sun) ---
    today = datetime.now().date()
    # Find the most recent Monday (start of the week)
    start_of_week = today - timedelta(days=today.weekday())

    # Initialize 7 buckets for Mon-Sun
    week_days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    daily_values = [0] * 7 # [0, 0, 0, 0, 0, 0, 0]

    # Get data from this Monday onwards
    current_week_sessions = StudySession.query.filter(
        StudySession.user_id == current_user.id,
        StudySession.date >= start_of_week
    ).all()

    # Fill the buckets
    for session in current_week_sessions:
        # session.date.weekday() returns 0 for Mon, 1 for Tue, etc.
        day_index = session.date.weekday()
        daily_values[day_index] += session.hours

    # --- CHART 2: WEEKLY (Last 4 Weeks) ---
    # We want 4 bars representing the last 4 weeks
    weekly_labels = []
    weekly_values = []

    for i in range(4):
        # Calculate start/end of the "week window" looking back
        # We go in reverse: Current Week (0), Last Week (1), etc.
        week_start = start_of_week - timedelta(weeks=3-i) # Start from 4 weeks ago
        week_end = week_start + timedelta(days=6)

        # Label: "Jan 01 - Jan 07"
        label = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}"
        weekly_labels.append(label)

        # Sum hours for this specific date range
        week_total = 0
        sessions = StudySession.query.filter(
            StudySession.user_id == current_user.id,
            StudySession.date >= week_start,
            StudySession.date <= datetime.combine(week_end, datetime.max.time())
        ).all()

        week_total = sum(s.hours for s in sessions)
        weekly_values.append(week_total)

    # --- CHART 3: SUBJECTS (Existing Logic) ---
    all_sessions = StudySession.query.filter_by(user_id=current_user.id).all()
    subject_data = {}
    for s in all_sessions:
        subject_data[s.subject] = subject_data.get(s.subject, 0) + s.hours

    return render_template('stats.html',
                           user=current_user,
                           # Daily Data
                           daily_labels=json.dumps(week_days),
                           daily_values=json.dumps(daily_values),
                           # Weekly Data (NEW)
                           weekly_labels=json.dumps(weekly_labels),
                           weekly_values=json.dumps(weekly_values),
                           # Subject Data
                           subject_labels=json.dumps(list(subject_data.keys())),
                           subject_values=json.dumps(list(subject_data.values())))

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