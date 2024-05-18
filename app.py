from flask import Flask, render_template, request, session, redirect, url_for, flash
from flask_login import LoginManager, login_required, login_user, UserMixin
from flask_mysqldb import MySQL
from functools import wraps
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FloatField
from wtforms.validators import InputRequired, Length, NumberRange
import MySQLdb.cursors
import re
import pickle
import numpy as np
import pandas as pd
from werkzeug.utils import secure_filename
import os
import csv

app = Flask(__name__)

app.secret_key = 'xyzsdfg'

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'study-hub'

mysql = MySQL(app)
login_manager = LoginManager()
login_manager.init_app(app)


class User(UserMixin):
    def __init__(self, id):
        self.id = id


class AddBookForm(FlaskForm):
    isbn = StringField('ISBN', validators=[InputRequired()])
    title = StringField('Title', validators=[InputRequired(), Length(max=255)])
    author = StringField('Author', validators=[InputRequired(), Length(max=255)])
    image_url = StringField('Image URL', validators=[InputRequired(), Length(max=255)])
    votes = IntegerField('Votes', validators=[InputRequired(), NumberRange(min=0)])
    rating = FloatField('Rating', validators=[InputRequired(), NumberRange(min=0, max=5)])


@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


ALLOWED_EXTENSIONS = {'csv'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


popular_df = pickle.load(open('popular.pkl', 'rb'))
pt = pickle.load(open('pt.pkl', 'rb'))
books = pickle.load(open('books.pkl', 'rb'))
similarity_scores = pickle.load(open('similarity_scores.pkl', 'rb'))
search = pickle.load(open('search.pkl', 'rb'))

# Load 'books' DataFrame from pickle file if it exists; otherwise, initialize it as an empty DataFrame
if os.path.exists('books.pkl'):
    with open('books.pkl', 'rb') as pickle_file:
        books = pickle.load(pickle_file)
else:
    books = pd.DataFrame(columns=['isbn', 'title', 'author', 'image_url', 'votes', 'rating'])


# Define the function to append data to a CSV file
def append_to_csv(csv_file_path, new_data):
    try:
        with open(csv_file_path, 'a', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(new_data)
        flash('Data appended to CSV file successfully!', 'success')
    except Exception as e:
        flash(f'Error appending data to CSV file: {str(e)}', 'error')


@app.route('/', methods=['GET', 'POST'])
def login():
    message = ''
    if request.method == 'POST' and 'email' in request.form and 'password' in request.form:
        email = request.form['email']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM user WHERE email = % s', (email,))
        user = cursor.fetchone()
        if user and (user['password'], password):
            user_obj = User(user['id'])
            login_user(user_obj)
            message = 'Logged in Successfully!'
            return redirect('/index')
        else:
            message = 'Please enter correct email / password!'
            return render_template('login.html', message=message)
    return render_template('login.html', message=message)


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    message = ''
    if request.method == 'POST' and 'name' in request.form and 'password' in request.form and 'email' in request.form:
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM user WHERE email = % s', (email,))
        account = cursor.fetchone()

        if account:
            message = 'Account already exists!'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            message = 'Invalid email address!'
        elif not name or not password or not email:
            message = 'Please fill out the form!'
        else:
            cursor.execute('INSERT INTO user VALUES(NULL, %s, %s, %s)', (name, email, password,))
            mysql.connection.commit()
            message = 'You have successfully registered!'
    elif request.method == 'POST':
        message = 'Please fill out the form!'
    return render_template('register.html', message=message)


@app.route('/index')
@login_required
def index_ui():
    book_data = {
        'book_name': popular_df['Book-Title'].values.tolist(),
        'author': popular_df['Book-Author'].values.tolist(),
        'image': popular_df['Image-URL-M'].values.tolist(),
        'votes': popular_df['num_ratings'].values.tolist(),
        'rating': popular_df['avg_rating'].values.tolist()
    }

    return render_template('index.html', **book_data)


@app.route('/recommend')
@login_required
def recommend_ui():
    return render_template('recommend.html')


@app.route('/recommend_books', methods=['POST'])
def recommend():
    try:
        user_input = request.form.get('user_input')
        if user_input is None or user_input not in pt.index:
            error_message = f"No results found for '{user_input}'. Please check the book title and try again."
            return render_template('recommend.html', error_message=error_message)

        index = np.where(pt.index == user_input)[0][0]
        similar_items = sorted(list(enumerate(similarity_scores[index])), key=lambda x: x[1], reverse=True)[1:5]
        similar_items = sorted(list(enumerate(similarity_scores[index])), key=lambda x: x[1], reverse=True)[1:9]

        data = []
        for i in similar_items:
            item = []
            temp_df = books[books['Book-Title'] == pt.index[i[0]]]
            item.extend(temp_df.drop_duplicates('Book-Title')['Book-Title'].to_list())
            item.extend(temp_df.drop_duplicates('Book-Title')['Book-Author'].to_list())
            item.extend(temp_df.drop_duplicates('Book-Title')['Image-URL-M'].to_list())
            data.append(item)
        print(data)

        # Returning the recommendation data to the 'recommend.html' template
        return render_template('recommend.html', data=data, user_input=user_input)

    except Exception as e:
        # Log the exception for debugging purposes
        print(f"Error occurred during recommendation: {e}")
        # Provide user-friendly error message
        error_message = "An error occurred during the recommendation process. Please try again later."
        return render_template('recommend.html', error_message=error_message)


@app.route('/search')
@login_required
def search_ui():
    return render_template('search.html')


@app.route('/search', methods=['GET', 'POST'])
def search_books():
    user_search = ""

    if request.method == 'POST':
        user_search = request.form.get('user_search', '').strip()

        if user_search:
            # Query the database for books matching the user search input
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            query = "SELECT * FROM books WHERE title LIKE %s"
            cursor.execute(query, ('%' + user_search + '%',))
            name_data = cursor.fetchall()

            if not name_data:
                # If no results are found in the database, fall back to using preloaded dataset
                crt_names = search[search['Book-Title'].str.contains(user_search, case=False)].head(8)
                name_data = crt_names.values.tolist()

                if not name_data:
                    error_message = f"No results found for '{user_search}'. Please check the book name and try again."
                else:
                    error_message = None
            else:
                error_message = None
        else:
            name_data = []
            error_message = None
    else:
        name_data = []
        error_message = None

    return render_template('search.html', name_data=name_data, error_message=error_message, user_search=user_search)


@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    message = ''
    if request.method == 'POST' and 'email' in request.form and 'password' in request.form:
        email = request.form['email']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM admin WHERE email = % s', (email,))
        user = cursor.fetchone()
        if user and (user['password'], password):
            user_obj = User(user['id'])
            login_user(user_obj)
            message = 'Logged in Successfully!'
            return redirect('/add_book')
        else:
            message = 'Please enter correct email / password!'
            return render_template('admin_login.html', message=message)
    return render_template('admin_login.html', message=message)


@app.route('/add_book', methods=['GET', 'POST'])
@login_required
def add_book():
    form = AddBookForm()

    if request.method == 'POST':
        if 'csv_file' in request.files:
            # Handle CSV file upload
            csv_file = request.files['csv_file']
            if csv_file and allowed_file(csv_file.filename):
                filename = secure_filename(csv_file.filename)
                csv_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                csv_file.save(csv_file_path)
                process_csv(csv_file_path)  # Call the CSV processing function
                flash('CSV file processed and books added successfully!', 'success')
                return redirect(url_for('add_book'))
        else:
            # Process individual book entry
            if form.validate_on_submit():
                isbn = form.isbn.data
                title = form.title.data
                author = form.author.data
                image_url = form.image_url.data
                votes = form.votes.data
                rating = form.rating.data

                cursor = mysql.connection.cursor()
                cursor.execute(
                    'INSERT INTO books (isbn, title, author, image_url, votes, rating) '
                    'VALUES (%s, %s, %s, %s, %s, %s)',
                    (isbn, title, author, image_url, votes, rating))
                mysql.connection.commit()
                cursor.close()

                flash('Book added successfully!', 'success')
                session['book_added'] = 'Book added successfully!'
                return redirect(url_for('add_book'))

    return render_template('add_book.html', form=form)


@app.route('/admin_search_books', methods=['GET', 'POST'])
@login_required
def admin_search_books():
    user_search = ""

    if request.method == 'POST':
        user_search = request.form.get('user_search', '').strip()

        if user_search:
            # Query the database for books matching the user search input
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            query = "SELECT * FROM books WHERE title LIKE %s"
            cursor.execute(query, ('%' + user_search + '%',))
            name_data = cursor.fetchall()

            if not name_data:
                # If no results are found in the database, fall back to using preloaded dataset
                crt_names = search[search['Book-Title'].str.contains(user_search, case=False)].head(8)
                name_data = crt_names.values.tolist()

                if not name_data:
                    error_message = f"No results found for '{user_search}'. Please check the book name and try again."
                else:
                    error_message = None
            else:
                error_message = None
        else:
            name_data = []
            error_message = None
    else:
        name_data = []
        error_message = None

    return render_template('search_books.html', name_data=name_data, error_message=error_message,
                           user_search=user_search)


if __name__ == '__main__':
    app.run(debug=True)
