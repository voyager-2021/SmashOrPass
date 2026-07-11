import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    votes = db.relationship('Vote', backref='user', lazy=True)

class Package(db.Model):
    __tablename__ = 'packages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    author = db.Column(db.String(200))
    version = db.Column(db.String(50))
    description = db.Column(db.Text)
    github_url = db.Column(db.String(500))
    pypi_url = db.Column(db.String(500))
    total_downloads = db.Column(db.BigInteger, default=0)
    github_stars = db.Column(db.Integer, default=0)
    license = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    votes = db.relationship('Vote', backref='package', lazy=True)

    @property
    def smash_count(self):
        return sum(1 for v in self.votes if v.is_smash)

    @property
    def total_votes(self):
        return len(self.votes)

    @property
    def smash_ratio(self):
        # Scale 0.0 - 10.0 rating
        total = self.total_votes
        if total == 0:
            return 5.0 # default rating when no votes exist
        return round((self.smash_count / total) * 10, 1)

class Vote(db.Model):
    __tablename__ = 'votes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey('packages.id'), nullable=False)
    is_smash = db.Column(db.Boolean, nullable=False) # True = Smash, False = Pass
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'package_id', name='_user_package_uc'),)

class PypiQueue(db.Model):
    __tablename__ = 'pypi_queue'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    status = db.Column(db.String(50), default='pending') # pending, fetched, rejected, error
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
