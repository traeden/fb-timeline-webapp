from flask import Flask, redirect, request, session, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
from sqlalchemy import func
import os
from dotenv import load_dotenv
import requests

load_dotenv()
app = Flask(__name__)
bootstrap = Bootstrap(app)

app.secret_key = 'xyz789abc123'

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://localhost/timeline'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facebook_id = db.Column(db.String(100), unique=True)
    message = db.Column(db.Text)
    created_time = db.Column(db.String(50))
    photo_url = db.Column(db.String(2000), nullable=True)
    video_url = db.Column(db.String(2000), nullable=True)

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
    
    # Fetch posts with media
    posts_url = (
        f'https://graph.facebook.com/v18.0/me/feed'
        f'?access_token={access_token}'
        f'&fields=id,message,created_time,attachments{{type,media}}'
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
                attachments = post.get('attachments', {}).get('data', [])
                photo_url = ''
                video_url = ''
                if attachments:
                    for attachment in attachments:
                        if attachment.get('type') == 'photo':
                            photo_url = attachment.get('media', {}).get('image', {}).get('src', '')
                        elif attachment.get('type') in ['video', 'video_inline']:
                            video_url = attachment.get('media', {}).get('source', '')
                new_post = Post(
                    facebook_id=post['id'],
                    message=post.get('message', ''),
                    created_time=post['created_time'],
                    photo_url=photo_url,
                    video_url=video_url
                )
                db.session.add(new_post)
        db.session.commit()
    
    # Apply filters or clear them
    query = Post.query
    clear_filters = request.args.get('clear_filters')
    if clear_filters == 'true':
        # Reset to all posts, no filters
        db_posts = query.all()
    else:
        # Apply filters
        start_date = request.args.get('start_date')
        if start_date:
            query = query.filter(Post.created_time >= start_date)
        end_date = request.args.get('end_date')
        if end_date:
            query = query.filter(Post.created_time <= end_date)
        keyword = request.args.get('keyword')
        if keyword:
            query = query.filter(Post.message.ilike(f'%{keyword}%'))
        has_photo = request.args.get('has_photo')
        if has_photo == 'yes':
            query = query.filter(Post.photo_url != '')
        elif has_photo == 'no':
            query = query.filter(Post.photo_url == '')
        has_video = request.args.get('has_video')
        if has_video == 'yes':
            query = query.filter(Post.video_url != '')
        elif has_video == 'no':
            query = query.filter(Post.video_url == '')
        min_length = request.args.get('min_length')
        if min_length:
            query = query.filter(func.length(Post.message) >= int(min_length))
        max_length = request.args.get('max_length')
        if max_length:
            query = query.filter(func.length(Post.message) <= int(max_length))
        has_tags = request.args.get('has_tags')
        if has_tags == 'yes':
            query = query.filter(Post.message.ilike('%@%'))
        elif has_tags == 'no':
            query = query.filter(~Post.message.ilike('%@%'))
        db_posts = query.all()
    
    return render_template('timeline.html', posts=db_posts, user_data=user_data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)