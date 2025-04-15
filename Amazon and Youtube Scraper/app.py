from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import os
from werkzeug.security import generate_password_hash, check_password_hash
from scrapers.youtube_scraper import scrape_youtube_videos
from scrapers.amazon_scraper import AmazonScraper
import csv
import sqlite3
import functools
import json
import pandas as pd
import shutil

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database initialization
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT)''')
    conn.commit()
    conn.close()

init_db()

def clear_output_directory():
    """Clear all files in the output directory"""
    if os.path.exists('output'):
        for filename in os.listdir('output'):
            file_path = os.path.join('output', filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

def check_file_has_data(file_path):
    if not os.path.exists(file_path):
        return False
    
    try:
        if file_path.endswith('.csv'):
            with open(file_path, 'r', encoding='utf-8') as f:
                csv_reader = csv.reader(f)
                # Skip header row
                next(csv_reader, None)
                # Check if there's at least one data row
                return bool(next(csv_reader, None))
        elif file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path)
            return len(df) > 0
        elif file_path.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return bool(data)
    except Exception as e:
        print(f"Error checking file {file_path}: {str(e)}")
        return False
    return False

# Login required decorator
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            clear_output_directory()  # Clear data when session expires
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    clear_output_directory()  # Clear data when accessing root without session
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('signup'))
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        c.execute('SELECT username FROM users WHERE username = ?', (username,))
        if c.fetchone() is not None:
            conn.close()
            flash('Username already exists', 'error')
            return redirect(url_for('signup'))
        
        hashed_password = generate_password_hash(password)
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                 (username, hashed_password))
        conn.commit()
        conn.close()
        
        flash('Account created successfully', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Clear any existing data when accessing login page
    clear_output_directory()
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT password FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[0], password):
            session['username'] = username
            flash('Logged in successfully', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    clear_output_directory()  # Clear data on logout
    session.pop('username', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    
    youtube_files = {
        'csv': check_file_has_data('output/youtube_videos.csv'),
        'excel': check_file_has_data('output/youtube_videos.xlsx'),
        'json': check_file_has_data('output/youtube_videos.json')
    }
    amazon_files = {
        'csv': check_file_has_data('output/amazon_products.csv'),
        'excel': check_file_has_data('output/amazon_products.xlsx'),
        'json': check_file_has_data('output/amazon_products.json')
    }
    return render_template('dashboard.html', youtube_files=youtube_files, amazon_files=amazon_files)

@app.route('/blog')
@login_required
def blog():
    return render_template('blog.html')

@app.route('/download/<scraper>/<format>')
@login_required
def download_file(scraper, format):
    if scraper not in ['youtube', 'amazon'] or format not in ['csv', 'excel', 'json']:
        flash('Invalid download request', 'error')
        return redirect(url_for('dashboard'))
    
    filename = f"{scraper}_{'videos' if scraper == 'youtube' else 'products'}.{format}"
    if format == 'excel':
        filename = filename.replace('excel', 'xlsx')
    
    file_path = os.path.join('output', filename)
    
    if not os.path.exists(file_path) or not check_file_has_data(file_path):
        flash('No data available for download', 'error')
        return redirect(url_for('dashboard'))
    
    return send_file(file_path, as_attachment=True)

@app.route('/clear/<scraper>', methods=['POST'])
@login_required
def clear_data(scraper):
    if scraper not in ['youtube', 'amazon']:
        flash('Invalid scraper specified', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        # Clear files for the specified scraper
        for ext in ['csv', 'xlsx', 'json']:
            file_path = f'output/{scraper}_{"videos" if scraper == "youtube" else "products"}.{ext}'
            if os.path.exists(file_path):
                os.remove(file_path)
        
        flash(f'{scraper.title()} data cleared successfully', 'success')
    except Exception as e:
        flash(f'Error clearing {scraper} data: {str(e)}', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/scrape/youtube', methods=['POST'])
@login_required
def scrape_youtube():
    query = request.form.get('query', '')
    try:
        # Clear previous data
        for ext in ['csv', 'xlsx', 'json']:
            file_path = f'output/youtube_videos.{ext}'
            if os.path.exists(file_path):
                os.remove(file_path)
                
        videos = scrape_youtube_videos(query)
        
        if not videos:
            flash('No videos found', 'error')
            return redirect(url_for('dashboard'))
        
        # Ensure output directory exists
        os.makedirs('output', exist_ok=True)
        
        # Save as CSV
        with open('output/youtube_videos.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['title', 'views', 'upload_date'])
            writer.writeheader()
            writer.writerows(videos)
        
        # Save as Excel
        df = pd.DataFrame(videos)
        df.to_excel('output/youtube_videos.xlsx', index=False)
        
        # Save as JSON
        with open('output/youtube_videos.json', 'w', encoding='utf-8') as f:
            json.dump(videos, f, indent=2)
            
        flash('YouTube data scraped successfully', 'success')
    except Exception as e:
        flash(f'Error scraping YouTube data: {str(e)}', 'error')
    return redirect(url_for('dashboard'))

@app.route('/scrape/amazon', methods=['POST'])
@login_required
def scrape_amazon():
    query = request.form.get('query', '')
    max_pages = min(int(request.form.get('max_pages', 1)), 20)  # Limit to 20 pages
    
    try:
        # Clear previous data
        for ext in ['csv', 'xlsx', 'json']:
            file_path = f'output/amazon_products.{ext}'
            if os.path.exists(file_path):
                os.remove(file_path)
                
        scraper = AmazonScraper()
        products = scraper.scrape_amazon(query, max_pages)
        
        if not products:
            flash('No products found', 'error')
            return redirect(url_for('dashboard'))
            
        # Save as CSV
        df = pd.DataFrame([p.__dict__ for p in products])
        df.to_csv('output/amazon_products.csv', index=False)
        
        # Save as Excel
        df.to_excel('output/amazon_products.xlsx', index=False)
        
        # Save as JSON
        with open('output/amazon_products.json', 'w', encoding='utf-8') as f:
            json.dump([p.__dict__ for p in products], f, indent=2)
            
        flash(f'Amazon data scraped successfully. Found {len(products)} products.', 'success')
    except Exception as e:
        flash(f'Error scraping Amazon data: {str(e)}', 'error')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    app.run(debug=True)