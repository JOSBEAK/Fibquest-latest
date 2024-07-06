from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
from flask_session import Session
import os
import json

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=["http://localhost:3000"])
app.secret_key = "231242451"

# Session configuration
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'fibquest_'
app.config['SESSION_COOKIE_NAME'] = 'fibquest_session'
app.config['SESSION_COOKIE_SECURE'] = True  # for HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config.update(SESSION_COOKIE_SAMESITE="None", SESSION_COOKIE_SECURE=True)
Session(app)

# MySQL Configuration
app.config['MYSQL_HOST'] = '127.0.0.1'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'drecothea'
app.config['MYSQL_DB'] = 'FibQuestDb'

mysql = MySQL(app)

@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(days=1)
    session.modified = True

# Function to fetch user by username
def get_user_by_username(username):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    if user:
        return {
            'id': user[0],
            'username': user[1],
            'password': user[2],
            'email': user[3]
        }
    return None

from datetime import date

def update_streak(user_id):
    cur = mysql.connection.cursor()
    
    # Get the last solved date
    cur.execute("SELECT MAX(solved_date) FROM questions WHERE user_id = %s", (user_id,))
    last_solved_date = cur.fetchone()[0]
    
    if last_solved_date is None:
        # No questions solved yet
        return
    
    today = date.today()
    
    if last_solved_date == today:
        # Solved a question today, increment streak
        cur.execute("UPDATE users SET current_streak = current_streak + 1 WHERE id = %s", (user_id,))
    elif last_solved_date == today - timedelta(days=1):
        # Solved a question yesterday, maintain streak
        pass
    else:
        # Streak broken, reset to 1
        cur.execute("UPDATE users SET current_streak = 1 WHERE id = %s", (user_id,))
    
    # Update max streak if necessary
    cur.execute("UPDATE users SET max_streak = GREATEST(max_streak, current_streak) WHERE id = %s", (user_id,))
    
    mysql.connection.commit()
    cur.close()

def get_user_streaks(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT current_streak, max_streak FROM users WHERE id = %s", (user_id,))
    streaks = cur.fetchone()
    cur.close()
    return streaks



# Function to fetch user by email
def get_user_by_email(email):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    return user

# Function to fetch user by user ID
def get_user_by_id(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    return user

# Function to fetch questions by user ID
def get_questions_by_user(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM questions WHERE user_id = %s", (user_id,))
    questions = cur.fetchall()
    cur.close()
    return questions

# Route to Fetch All Questions
@app.route('/all_questions', methods=['GET'])
def all_questions():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']

    cur = mysql.connection.cursor()
    cur.execute("SELECT link, question_name, description, tags, difficulty FROM questions WHERE user_id = %s", (user_id,))
    all_questions = [{'link': row[0], 'name': row[1], 'description': row[2], 'tags': json.loads(row[3]), 'difficulty': row[4]} for row in cur.fetchall()]
    cur.close()

    return jsonify({'all_questions': all_questions}), 200

# Signup Route
@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data['username']
    password = data['password']
    email = data['email']

    if get_user_by_username(username):
        return jsonify({'error': 'Username already exists'}), 400
    if get_user_by_email(email):
        return jsonify({'error': 'Email already registered'}), 400

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO users (username, password, email) VALUES (%s, %s, %s)", (username, password, email))
    mysql.connection.commit()
    cur.close()

    return jsonify({'message': 'Signup successful'}), 201

# Login Route
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data['username']
    password = data['password']
    print(username, password)
    user = get_user_by_username(username)
    print(user)
    if user and user['password'] == password:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session.permanent = True
        print(f"Session set: user_id={session['user_id']}, username={session['username']}")
        return jsonify({'message': 'Login successful'}), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401

# Logout Route
@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logout successful'}), 200

# Add Question Route
@app.route('/add_question', methods=['POST'])
def add_question():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    link = data['link']
    question_name = data['question_name']
    description = data.get('description', None)
    tags = data.get('tags', [])
    difficulty = data['difficulty']
    user_id = session['user_id']
    today = datetime.now().date()

    tags_json = json.dumps(tags)

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO questions (user_id, link, question_name, description, tags, difficulty, solved_date, next_due_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (user_id, link, question_name, description, tags_json, difficulty, today, next_fibonacci_day(today, 0)))
    mysql.connection.commit()
    cur.close()

    # Update streak
    update_streak(user_id)

    return jsonify({'message': 'Question added successfully'}), 201

# Fetch Due and Solved Questions for a Date
@app.route('/due_and_solved_on_date', methods=['POST'])
def due_and_solved_on_date():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    date = data['date']
    user_id = session['user_id']

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT link, question_name, description, tags, difficulty
        FROM questions
        WHERE user_id = %s AND DATE(solved_date) = %s
    """, (user_id, date))
    solved_today = [{
        'link': row[0],
        'name': row[1],
        'description': row[2],
        'tags': json.loads(row[3]),
        'difficulty': row[4]
    } for row in cur.fetchall()]

    cur.execute("""
        SELECT link, question_name, description, tags, difficulty
        FROM questions
        WHERE user_id = %s AND DATE(next_due_date) = %s
    """, (user_id, date))
    due_today = [{
        'link': row[0],
        'name': row[1],
        'description': row[2],
        'tags': json.loads(row[3]) if row[3] is not None else {},
        'difficulty': row[4]
    } for row in cur.fetchall()]

    cur.close()

    return jsonify({'due_today': due_today, 'solved_today': solved_today}), 200

# Route to check session
@app.route('/check_session', methods=['GET'])
def check_session():
    if 'user_id' in session:
        user_id = session['user_id']
        current_streak, max_streak = get_user_streaks(user_id)
        return jsonify({
            'logged_in': True,
            'user_id': user_id,
            'username': session.get('username'),
            'current_streak': current_streak,
            'max_streak': max_streak
        }), 200
    else:
        return jsonify({'logged_in': False}), 200
# Function to get Fibonacci days
def get_fibonacci_days(n):
    fib_days = [0, 1]
    while fib_days[-1] <= n:
        fib_days.append(fib_days[-1] + fib_days[-2])
    return fib_days[1:]

@app.route('/get_streaks', methods=['GET'])
def get_streaks():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    current_streak, max_streak = get_user_streaks(user_id)

    return jsonify({
        'current_streak': current_streak,
        'max_streak': max_streak
    }), 200
# Function to get the next Fibonacci day
def next_fibonacci_day(start_date, days_passed):
    fib_days = get_fibonacci_days(days_passed + 1)
    next_day_index = len([d for d in fib_days if d <= days_passed])
    return start_date + timedelta(days=fib_days[next_day_index])

if __name__ == '__main__':
    app.run(debug=True)
