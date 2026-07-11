import pytest
from app import app, db
from models import User, Package, Vote, PypiQueue
from pypi_utils import parse_github_repo, is_low_quality

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

def test_github_parser():
    # Test valid URL parsing
    project_urls = {
        "Homepage": "https://github.com/psf/requests",
        "Bug Tracker": "https://github.com/psf/requests/issues"
    }
    owner, repo = parse_github_repo(project_urls)
    assert owner == "psf"
    assert repo == "requests"

    # Test single homepage parsing
    owner, repo = parse_github_repo(None, "https://github.com/encode/httpx")
    assert owner == "encode"
    assert repo == "httpx"

def test_is_low_quality_filter():
    # Valid pkg
    valid_info = {
        "name": "super-cool-pkg",
        "description": "This is an extremely robust and cool package that does awesome stuff.",
        "summary": "This package is really useful for doing advanced mathematical things.",
        "version": "1.2.3"
    }
    assert is_low_quality(valid_info) is False

    # Low quality pkg (no description)
    no_desc = {
        "name": "lazy-pkg",
        "description": "",
        "summary": "",
        "version": "0.1.0"
    }
    assert is_low_quality(no_desc) is True

    # Placeholder description
    placeholder = {
        "name": "test-pkg",
        "description": "work in progress to be done placeholder test package for testing purposes",
        "summary": "placeholder",
        "version": "0.0.1"
    }
    assert is_low_quality(placeholder) is True

def test_auth_routes(client):
    # Register new user
    r = client.post('/register', data={'username': 'testuser', 'password': 'testpassword'}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Registration successful!" in r.data

    # Logout
    r = client.get('/logout', follow_redirects=True)
    assert r.status_code == 200
    assert b"Logged out successfully." in r.data

    # Login user
    r = client.post('/login', data={'username': 'testuser', 'password': 'testpassword'}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Logged in successfully!" in r.data

def test_voting_flow(client):
    # Seed a package
    with app.app_context():
        p = Package(
            name="requests",
            author="Kenneth Reitz",
            version="2.31.0",
            description="Python HTTP for Humans.",
            pypi_url="https://pypi.org/project/requests/",
            total_downloads=1000000,
            github_stars=50000
        )
        db.session.add(p)
        db.session.commit()

        # Check default rating when no votes exist (should be 5.0)
        assert p.smash_ratio == 5.0

    # Guest voting smash
    r = client.post('/vote/1', data={'action': 'smash'}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Vote recorded as Guest!" in r.data

    # Register and log in to vote permanently
    client.post('/register', data={'username': 'voter', 'password': 'password'}, follow_redirects=True)

    # Permanent vote: Smash
    r = client.post('/vote/1', data={'action': 'smash'}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Logged your vote for package!" in r.data

    # Check rating update (1 Smash, 0 Pass = 10.0 rating)
    with app.app_context():
        p = Package.query.get(1)
        assert p.smash_ratio == 10.0
        assert p.smash_count == 1
        assert p.total_votes == 1

def test_leaderboard(client):
    # Seed packages
    with app.app_context():
        p1 = Package(name="pkg1", description="desc1", version="1.0", total_downloads=100, github_stars=10)
        p2 = Package(name="pkg2", description="desc2", version="1.0", total_downloads=200, github_stars=20)
        db.session.add_all([p1, p2])
        db.session.commit()

    r = client.get('/leaderboard')
    assert r.status_code == 200
    assert b"pkg1" in r.data
    assert b"pkg2" in r.data
