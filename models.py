#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep 30 22:36:54 2025

@author: traedennord
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSON

db = SQLAlchemy()

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facebook_id = db.Column(db.String(100), unique=True)
    message = db.Column(db.Text)
    created_time = db.Column(db.String(50))
    photos = db.Column(JSON, nullable=True)
    videos = db.Column(JSON, nullable=True)
    links = db.Column(JSON, nullable=True)
    from_data = db.Column(JSON, nullable=True)
    comments = db.Column(JSON, nullable=True)
    source = db.Column(db.String(20), default='api')  # NEW: 'api' or 'import'

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facebook_id = db.Column(db.String(100), unique=True)
    post_id = db.Column(db.String(100), db.ForeignKey('post.facebook_id'))
    message = db.Column(db.Text)
    created_time = db.Column(db.String(50))
    from_data = db.Column(JSON, nullable=True)
    like_count = db.Column(db.Integer, default=0)