import os
import datetime
import random
import threading
import time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, Package, Vote, PypiQueue
from pypi_utils import process_and_get_package_details, fetch_simple_api_names
from rss_updater import fetch_rss_updates

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'smash_or_pass_secret_dev_key')
# Use a connection timeout of 30 seconds for SQLite to avoid locking issues
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///smashorpass.db?timeout=30')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

from sqlalchemy import event
from sqlalchemy.engine import Engine

# Set WAL mode and synchronous settings for sqlite connection to prevent locking
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Only execute on SQLite connections
    """Configure SQLite connections with WAL journaling and normal synchronous operation."""
    if type(dbapi_connection).__name__ == 'Connection' or 'sqlite' in str(type(dbapi_connection)).lower():
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        finally:
            cursor.close()

csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    """Load a user by their numeric identifier.
    
    Parameters:
    	user_id: The user's identifier.
    
    Returns:
    	User: The matching user, or None if no user exists with that identifier.
    """
    return User.query.get(int(user_id))

@app.context_processor
def inject_year():
    """Provide the current UTC year to template contexts.
    
    Returns:
        dict: A mapping containing the current UTC year under ``datetime_year``.
    """
    return {'datetime_year': datetime.datetime.utcnow().year}

# Helper to populate dynamic queue if empty
def seed_queue_if_empty():
    """
    Populate an empty package queue with popular seeds and additional package names fetched from PyPI.
    """
    if PypiQueue.query.count() == 0:
        # Seeding high-quality popular starting list first
        popular_seeds = [
            "requests", "numpy", "pandas", "django", "flask", "fastapi",
            "matplotlib", "scipy", "pytest", "black", "pydantic", "httpx",
            "sqlalchemy", "jinja2", "click", "uvicorn", "gunicorn", "scikit-learn"
        ]
        for name in popular_seeds:
            if not PypiQueue.query.filter_by(name=name).first():
                db.session.add(PypiQueue(name=name, status='pending'))
        db.session.commit()

        # Pull remaining package names from PyPI in background
        def bg_pull():
            with app.app_context():
                try:
                    print("Background Simple API seed started...")
                    names = fetch_simple_api_names()
                    if names:
                        existing = set(r[0] for r in db.session.query(PypiQueue.name).all())
                        new_names = [n for n in names if n not in existing]

                        # Bulk insert in batches of 5000 to keep memory low and fast
                        batch_size = 5000
                        for i in range(0, len(new_names), batch_size):
                            batch = new_names[i:i+batch_size]
                            objects = [PypiQueue(name=name, status='pending') for name in batch]
                            db.session.bulk_save_objects(objects)
                            db.session.commit()
                        print("Background Simple API seed completed successfully!")
                except Exception as e:
                    print(f"Background Simple API seed failed: {e}")

        threading.Thread(target=bg_pull, daemon=True).start()

# Background worker for package prefetching
def prefetch_packages_worker():
    """Background worker that prefetches packages from the queue."""
    while True:
        time.sleep(2)  # Check every 2 seconds for work
        with app.app_context():
            try:
                # Check if we need more prefetched packages (keep at least 10 ready)
                fetched_count = Package.query.count()
                pending_count = PypiQueue.query.filter_by(status='pending').count()

                if pending_count == 0:
                    continue

                # Process up to 5 packages per cycle
                for _ in range(min(5, pending_count)):
                    # Atomically claim a pending item by transitioning to processing
                    queue_item = PypiQueue.query.filter_by(status='pending').with_for_update(skip_locked=True).first()
                    if not queue_item:
                        break

                    queue_item.status = 'processing'
                    db.session.commit()

                    # Try fetching details with attempt limit
                    max_attempts = 5
                    attempt = 0
                    success = False

                    while attempt < max_attempts and not success:
                        attempt += 1
                        try:
                            details = process_and_get_package_details(queue_item.name)
                            if details:
                                new_pkg = Package(
                                    name=details["name"],
                                    author=details["author"],
                                    version=details["version"],
                                    description=details["description"],
                                    github_url=details["github_url"],
                                    pypi_url=details["pypi_url"],
                                    total_downloads=details["total_downloads"],
                                    github_stars=details["github_stars"],
                                    license=details["license"]
                                )
                                db.session.add(new_pkg)
                                queue_item.status = 'fetched'
                                db.session.commit()
                                success = True
                            else:
                                # Low quality, mark rejected
                                queue_item.status = 'rejected'
                                db.session.commit()
                                success = True
                        except Exception as e:
                            print(f"Error processing {queue_item.name} (attempt {attempt}): {e}")
                            if attempt >= max_attempts:
                                queue_item.status = 'rejected'
                                db.session.commit()
                            time.sleep(1)

            except Exception as e:
                print(f"Background prefetch error: {e}")
                try:
                    db.session.rollback()
                except:
                    pass

# Scheduler for RSS Updates (Polls feed every 10 mins)
def start_scheduler():
    """Start daemon threads for RSS updates and package prefetching."""
    def rss_loop():
        while True:
            time.sleep(600) # every 10 mins
            with app.app_context():
                try:
                    fetch_rss_updates()
                except Exception as e:
                    print(f"Background RSS fetch error: {e}")

    threading.Thread(target=rss_loop, daemon=True).start()
    threading.Thread(target=prefetch_packages_worker, daemon=True).start()

# Core logic: Find next package for current user / guest session
def get_next_voting_package():
    # If authenticated, avoid previously voted packages
    """
    Selects an eligible package for the next vote.
    
    For authenticated users, packages they have already voted on are excluded. If no existing package is eligible, retrieves and persists a package from the pending queue.
    
    Returns:
        Package: The selected package.
        None: If no package is available.
    """
    # Try to find an existing high-quality package that wasn't voted on
    query = Package.query
    if current_user.is_authenticated:
        # Use a subquery to avoid SQLite variable limit
        voted_subquery = db.session.query(Vote.package_id).filter(Vote.user_id == current_user.id).subquery()
        query = query.filter(~Package.id.in_(voted_subquery))

    # Use database-specific random ordering with a single row limit
    package = query.order_by(db.func.random()).first()
    return package

# Routes
@app.route('/')
def index():
    """Render the voting page with the next available package.
    
    Returns:
        The rendered voting page.
    """
    package = get_next_voting_package()
    return render_template('vote.html', package=package)

@app.route('/vote/<int:package_id>', methods=['POST'])
def vote(package_id):
    """
    Record an authenticated user's vote for a package and redirect to the voting page.

    Parameters:
        package_id (int): Identifier of the package being voted on.

    Returns:
        Response: A redirect response to the index page.
    """
    action = request.form.get('action')
    if action not in ['smash', 'pass']:
        flash('Invalid action.', 'error')
        return redirect(url_for('index'))

    # Validate that package_id exists
    package = Package.query.get(package_id)
    if not package:
        flash('Invalid package.', 'error')
        return redirect(url_for('index'))

    is_smash = (action == 'smash')

    if current_user.is_authenticated:
        # Check if already voted
        existing_vote = Vote.query.filter_by(user_id=current_user.id, package_id=package_id).first()
        if existing_vote:
            flash('You have already voted on this package.', 'info')
        else:
            v = Vote(user_id=current_user.id, package_id=package_id, is_smash=is_smash)
            db.session.add(v)
            db.session.commit()
            flash('Logged your vote for package!', 'success')
    else:
        # Store vote in guest session or just redirect (as guest votes aren't saved to DB)
        flash('Vote recorded as Guest! Log in to save it permanently.', 'info')

    return redirect(url_for('index'))

@app.route('/leaderboard')
def leaderboard():
    # Sort packages by score (smash_ratio desc)
    # To do this in Python since smash_ratio is a @property:
    """
    Display the leaderboard of packages ranked by voting ratio, download count, and GitHub stars.
    
    Returns:
        The rendered leaderboard page containing the top 100 packages and summary statistics.
    """
    all_packages = Package.query.all()
    # Sort by ratio (descending), then total downloads (descending), then stars (descending)
    sorted_packages = sorted(all_packages, key=lambda p: (p.smash_ratio, p.total_downloads or 0, p.github_stars or 0), reverse=True)

    # Calculate some summary stats
    stats = {
        'total_packages': Package.query.count(),
        'total_votes': Vote.query.count()
    }
    return render_template('leaderboard.html', packages=sorted_packages[:100], stats=stats)

@app.route('/package/<package_name>')
def package_detail(package_name):
    # Lookup by name
    """Render the detail page for a package identified by name.
    
    Parameters:
        package_name (str): The exact package name to look up.
    
    Returns:
        Response: The rendered package detail page.
    """
    package = Package.query.filter_by(name=package_name).first_or_404()
    return render_template('detail.html', package=package)

@app.route('/history')
@login_required
def history():
    """Display the authenticated user's vote history in reverse chronological order."""
    user_votes = Vote.query.filter_by(user_id=current_user.id).order_by(Vote.created_at.desc()).all()
    return render_template('history.html', votes=user_votes)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Authenticate a user and display the login form.
    
    Returns:
        Response: A redirect for authenticated users or successful logins; otherwise, the rendered login page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Register a new user and authenticate the account.
    
    Returns:
    	Response: A redirect to the index after successful registration or an authenticated user attempts to register; otherwise, the registration form.
    """
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Please enter all required fields.', 'error')
            return render_template('register.html')

        existing = User.query.filter_by(username=username).first()
        if existing:
            flash('Username already exists.', 'error')
            return render_template('register.html')

        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        flash('Registration successful!', 'success')
        return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    """Log out the current user and redirect to the home page."""
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

def initialize_app():
    """Initialize database, seed queue, and start background workers."""
    db.create_all()
    seed_queue_if_empty()
    start_scheduler()

if __name__ == '__main__':
    with app.app_context():
        initialize_app()
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
