#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Sep  3 10:11:49 2025

@author: traedennord
"""

from flask import Flask, redirect, request, session, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv
import requests

load_dotenv()
app = Flask(__name__)
app.secret_key = 'xyz789abc123'

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://localhost/timeline'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facebook_id = db.Column(db.String(100), unique=True)
    message = db.Column(db.Text)
    created_time = db.Column(db.String(50))

FB_APP_ID = os.getenv('FB_APP_ID')
FB_APP_SECRET = os.getenv('FB_APP_SECRET')
REDIRECT_URI = 'http://localhost:5000/callback'

@app.route('/')
def home():
    return 'Welcome! <a href="/login">Login with Facebook</a>'

@app.route('/login')
def login():
    fb_login_url = (
        f'https://www.facebook.com/v18.0/dialog/oauth'
        f'?client_id={FB_APP_ID}'
        f'&redirect_uri={REDIRECT_URI}'
        f'&scope=public_profile,user_posts'
    )
    return redirect(fb_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return 'Error: No code received', 400
    token_url = (
        f'https://graph.facebook.com/v18.0/oauth/access_token'
        f'?client_id={FB_APP_ID}'
        f'&redirect_uri={REDIRECT_URI}'
        f'&client_secret={FB_APP_SECRET}'
        f'&code={code}'
    )
    response = requests.get(token_url)
    data = response.json()
    access_token = data.get('access_token')
    if not access_token:
        return f'Error: No access token received - {data}', 400
    session['access_token'] = access_token
    return redirect(url_for('timeline'))

@app.route('/timeline')
def timeline():
    if 'access_token' not in session:
        return redirect(url_for('login'))
    access_token = session['access_token']
    
    # Fetch user data
    graph_url = (
        f'https://graph.facebook.com/v18.0/me'
        f'?access_token={access_token}'
        f'&fields=id,name'
    )
    response = requests.get(graph_url)
    data = response.json()
    if 'error' in data:
        return f"Error fetching user data: {data['error']['message']}", 500
    user_data = data
    
    # Fetch posts
    posts_url = (
        f'https://graph.facebook.com/v18.0/me/feed'
        f'?access_token={access_token}'
        f'&fields=id,message,created_time'
    )
    posts_response = requests.get(posts_url)
    posts_data = posts_response.json()
    if 'error' in posts_data:
        return f"Error fetching posts: {posts_data['error']['message']}", 500
    
    # Store posts in database
    with app.app_context():
        for post in posts_data.get('data', []):
            existing_post = Post.query.filter_by(facebook_id=post['id']).first()
            if not existing_post:
                new_post = Post(
                    facebook_id=post['id'],
                    message=post.get('message', ''),
                    created_time=post['created_time']
                )
                db.session.add(new_post)
        db.session.commit()
    
    db_posts = Post.query.all()
    return render_template('timeline.html', posts=db_posts, user_data=user_data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)