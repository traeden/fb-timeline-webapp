#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Sep 12 12:54:57 2025

@author: traedennord
"""

from flask import Flask, redirect, request, session, url_for, render_template, flash
from flask_bootstrap import Bootstrap
from werkzeug.utils import secure_filename
import os
from dotenv import load_dotenv
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode
from sqlalchemy import func, or_, and_, text

"""from flask_sqlalchemy import SQLAlchemy
import json
from sqlalchemy.dialects.postgresql import JSON
"""



# Import models and importer
from models import db, Post, Comment
from facebook_import import FacebookDataImporter

load_dotenv()
app = Flask(__name__)
bootstrap = Bootstrap(app)

app.secret_key = 'xyz789abc123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://localhost/timeline'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max

# Initialize database with app
db.init_app(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


"""db = SQLAlchemy(app)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facebook_id = db.Column(db.String(100), unique=True)
    message = db.Column(db.Text)
    created_time = db.Column(db.String(50))
    photos = db.Column(JSON, nullable=True)  # Array of photo objects
    videos = db.Column(JSON, nullable=True)  # Array of video objects
    links = db.Column(JSON, nullable=True)   # Array of link objects
    from_data = db.Column(JSON, nullable=True)  # Author information
    comments = db.Column(JSON, nullable=True)  # Array of comment objects

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facebook_id = db.Column(db.String(100), unique=True)
    post_id = db.Column(db.String(100), db.ForeignKey('post.facebook_id'))
    message = db.Column(db.Text)
    created_time = db.Column(db.String(50))
    from_data = db.Column(JSON, nullable=True)  # Commenter information
    like_count = db.Column(db.Integer, default=0)"""

FB_APP_ID = os.getenv('FB_APP_ID')
FB_APP_SECRET = os.getenv('FB_APP_SECRET')
REDIRECT_URI = 'http://localhost:5000/callback'

def process_attachments(post_data):
    """
    Process all attachments from a Facebook post, handling multiple photos,
    videos, albums, and link previews with comprehensive field extraction
    """
    photos = []
    videos = []
    links = []
    
    # Handle direct link in post (not in attachments)
    if post_data.get('link'):
        links.append({
            'url': post_data['link'],
            'title': '',
            'description': '',
            'thumbnail': '',
            'domain': post_data['link'].split('/')[2] if post_data['link'] else ''
        })
    
    attachments = post_data.get('attachments', {}).get('data', [])
    
    for attachment in attachments:
        attachment_type = attachment.get('type', '')
        media_type = attachment.get('media_type', '')
        
        # Handle photos
        if attachment_type == 'photo' or media_type == 'photo':
            media = attachment.get('media', {})
            if 'image' in media:
                photos.append({
                    'src': media['image'].get('src', ''),
                    'width': media['image'].get('width', 0),
                    'height': media['image'].get('height', 0),
                    'url': attachment.get('url', ''),
                    'title': attachment.get('title', '')
                })
                
        # Handle videos
        elif attachment_type == 'video' or attachment_type == 'video_inline' or media_type == 'video':
            media = attachment.get('media', {})
            video_data = {
                'src': media.get('source', ''),
                'thumbnail': media.get('image', {}).get('src', '') if media.get('image') else '',
                'url': attachment.get('url', ''),
                'title': attachment.get('title', ''),
                'description': attachment.get('description', '')
            }
            videos.append(video_data)
                        
        # Handle shared links
        elif attachment_type == 'share' or attachment_type == 'link' or media_type == 'link':
            target = attachment.get('target', {})
            media = attachment.get('media', {})
            
            link_data = {
                'url': target.get('url', '') or attachment.get('url', ''),
                'title': attachment.get('title', ''),
                'description': attachment.get('description', ''),
                'thumbnail': media.get('image', {}).get('src', '') if media.get('image') else '',
                'domain': ''
            }
            
            # Extract domain from URL
            if link_data['url']:
                try:
                    link_data['domain'] = link_data['url'].split('/')[2]
                except:
                    link_data['domain'] = ''
            
            links.append(link_data)
        
        # Handle albums (can contain photos, videos, or mixed media)
        elif attachment_type == 'album':
            subattachments = attachment.get('subattachments', {}).get('data', [])
            for subattachment in subattachments:
                sub_type = subattachment.get('type', '')
                sub_media_type = subattachment.get('media_type', '')
                
                if sub_type == 'photo' or sub_media_type == 'photo':
                    media = subattachment.get('media', {})
                    if 'image' in media:
                        photos.append({
                            'src': media['image'].get('src', ''),
                            'width': media['image'].get('width', 0),
                            'height': media['image'].get('height', 0),
                            'url': subattachment.get('url', ''),
                            'title': subattachment.get('title', '')
                        })
                elif sub_type == 'video' or sub_media_type == 'video':
                    media = subattachment.get('media', {})
                    video_data = {
                        'src': media.get('source', ''),
                        'thumbnail': media.get('image', {}).get('src', '') if media.get('image') else '',
                        'url': subattachment.get('url', ''),
                        'title': subattachment.get('title', ''),
                        'description': subattachment.get('description', '')
                    }
                    videos.append(video_data)
    
    return photos, videos, links

def process_comments(post_id, access_token):
    """
    Fetch and process comments for a specific post
    """
    comments_url = (
        f'https://graph.facebook.com/v18.0/{post_id}/comments'
        f'?access_token={access_token}'
        f'&fields=id,message,created_time,from,like_count'
        f'&limit=50'
    )
    
    try:
        response = requests.get(comments_url)
        comments_data = response.json()
        
        if 'data' in comments_data:
            comments = []
            for comment in comments_data['data']:
                comments.append({
                    'id': comment['id'],
                    'message': comment.get('message', ''),
                    'created_time': comment['created_time'],
                    'from': comment.get('from', {}),
                    'like_count': comment.get('like_count', 0)
                })
            return comments
        else:
            print(f"No comments found for post {post_id}")
            return []
    except Exception as e:
        print(f"Error fetching comments for post {post_id}: {e}")
        return []

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login')
def login():
    api_start_date = request.args.get('api_start_date')
    api_end_date = request.args.get('api_end_date')
    api_post_type = request.args.get('api_post_type')
    
    # Store parameters in session
    session['api_filters'] = {
        'start_date': api_start_date,
        'end_date': api_end_date,
        'post_type': api_post_type
    }
    
    # Use clean redirect_uri
    session['original_redirect_uri'] = REDIRECT_URI
    
    fb_login_url = (
        f'https://www.facebook.com/v18.0/dialog/oauth'
        f'?client_id={FB_APP_ID}'
        f'&redirect_uri={REDIRECT_URI}'
        f'&scope=public_profile,user_posts,user_photos'
    )
    return redirect(fb_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return 'Error: No code received', 400
    
    original_redirect_uri = session.get('original_redirect_uri', REDIRECT_URI)
    
    # Retrieve parameters from session
    api_filters = session.get('api_filters', {})
    api_start_date = api_filters.get('start_date')
    api_end_date = api_filters.get('end_date')
    api_post_type = api_filters.get('post_type')
    
    # Token exchange
    token_url = (
        f'https://graph.facebook.com/v18.0/oauth/access_token'
        f'?client_id={FB_APP_ID}'
        f'&redirect_uri={original_redirect_uri}'
        f'&client_secret={FB_APP_SECRET}'
        f'&code={code}'
    )
    
    response = requests.get(token_url)
    data = response.json()
    
    access_token = data.get('access_token')
    if not access_token:
        return f'Error: No access token received - {data}', 400
    
    session['access_token'] = access_token
    
    # Build redirect to timeline
    params = {}
    if api_start_date is not None:
        params['api_start_date'] = api_start_date
    if api_end_date is not None:
        params['api_end_date'] = api_end_date
    if api_post_type is not None:
        params['api_post_type'] = api_post_type
    
    redirect_url = url_for('timeline')
    if params:
        redirect_url += '?' + urlencode(params)
    
    return redirect(redirect_url)

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
    
    # Get API filters from request
    api_start_date = request.args.get('api_start_date')
    api_end_date = request.args.get('api_end_date')
    api_post_type = request.args.get('api_post_type')
    
    # Get display filters from request
    display_start_date = request.args.get('display_start_date')
    display_end_date = request.args.get('display_end_date')
    keyword = request.args.get('keyword')
    has_photo = request.args.get('has_photo')
    has_video = request.args.get('has_video')
    has_links = request.args.get('has_links')
    min_length = request.args.get('min_length')
    max_length = request.args.get('max_length')
    has_tags = request.args.get('has_tags')
    clear_filters = request.args.get('clear_filters')
    fetch_comments = request.args.get('fetch_comments')  # New parameter
    
    # Clean up keyword parameter
    if keyword and (keyword.strip() == '' or keyword.lower() == 'none'):
        keyword = None
    
    # Set defaults and validate API filters
    if api_start_date or api_end_date or api_post_type:
        if not api_start_date:
            api_start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        if not api_end_date:
            api_end_date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            api_start_date = datetime.strptime(api_start_date, '%Y-%m-%d').strftime('%Y-%m-%d')
            api_end_date = datetime.strptime(api_end_date, '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError:
            return "Invalid API date format. Please ensure dates are in YYYY-MM-DD format.", 400
    
    # Fetch posts from API
    if True:  # Always fetch posts
        # Convert dates to Unix timestamps for Facebook API
        since_param = ''
        until_param = ''
        if api_start_date:
            try:
                start_timestamp = int(datetime.strptime(api_start_date, '%Y-%m-%d').timestamp())
                since_param = f'&since={start_timestamp}'
            except ValueError:
                pass
        if api_end_date:
            try:
                end_datetime = datetime.strptime(api_end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                end_timestamp = int(end_datetime.timestamp())
                until_param = f'&until={end_timestamp}'
            except ValueError:
                pass
        
        type_param = f'&type={api_post_type}' if api_post_type else ''
        limit = '100' if (api_start_date or api_end_date or api_post_type) else '20'
        
        posts_url = (
            f'https://graph.facebook.com/v18.0/me/posts'  # Changed from feed to posts for your own posts
            f'?access_token={access_token}'
            f'&fields=id,message,created_time,link,from,attachments{{type,media_type,media,url,title,description,subattachments{{type,media_type,media,url,title,description}},target{{url}}}}'
            f'{since_param}{until_param}{type_param}&limit={limit}'
        )
        
        print(f"Facebook API URL: {posts_url}")
        
        posts_response = requests.get(posts_url)
        posts_data = posts_response.json()
        
        if 'error' in posts_data:
            return render_template('error.html', message=f"Error fetching posts: {posts_data['error']['message']}"), 500
        
        # Store posts in database
        with app.app_context():
            print(f"Processing {len(posts_data.get('data', []))} posts from API")
            for post in posts_data.get('data', []):
                existing_post = Post.query.filter_by(facebook_id=post['id']).first()
                if not existing_post:
                    try:
                        photos, videos, links = process_attachments(post)
                        from_data = post.get('from')
                        
                        # Fetch comments if requested
                        comments = []
                        if fetch_comments == 'yes':
                            comments = process_comments(post['id'], access_token)
                        
                        new_post = Post(
                            facebook_id=post['id'],
                            message=post.get('message', ''),
                            created_time=post['created_time'],
                            photos=photos if photos else None,
                            videos=videos if videos else None,
                            links=links if links else None,
                            from_data=from_data,
                            comments=comments if comments else None
                        )
                        db.session.add(new_post)
                        print(f"  Successfully added post {post['id']}")
                        
                        # Store individual comments in Comment table
                        if comments:
                            for comment in comments:
                                existing_comment = Comment.query.filter_by(facebook_id=comment['id']).first()
                                if not existing_comment:
                                    new_comment = Comment(
                                        facebook_id=comment['id'],
                                        post_id=post['id'],
                                        message=comment['message'],
                                        created_time=comment['created_time'],
                                        from_data=comment['from'],
                                        like_count=comment['like_count']
                                    )
                                    db.session.add(new_comment)
                        
                    except Exception as e:
                        print(f"  ERROR processing post {post['id']}: {e}")
                else:
                    print(f"Post {post['id']} already exists, skipping")
            
            try:
                db.session.commit()
                print("Database commit completed successfully")
            except Exception as e:
                print(f"Database commit failed: {e}")
                db.session.rollback()
    
    # Server-side filtering for display (same as before)
    query = Post.query.order_by(Post.created_time.desc())
    
    if clear_filters != 'true':
        if display_start_date:
            query = query.filter(func.substring(Post.created_time, 1, 10) >= display_start_date)
        if display_end_date:
            query = query.filter(func.substring(Post.created_time, 1, 10) <= display_end_date)
        if keyword:
            query = query.filter(Post.message.ilike(f'%{keyword}%'))
        if min_length:
            try:
                query = query.filter(func.length(Post.message) >= int(min_length))
            except ValueError:
                pass
        if max_length:
            try:
                query = query.filter(func.length(Post.message) <= int(max_length))
            except ValueError:
                pass
        if has_tags == 'yes':
            query = query.filter(Post.message.ilike('%@%'))
        elif has_tags == 'no':
            query = query.filter(~Post.message.ilike('%@%'))
    
    all_posts = query.all()
    
    # Apply JSON-based filters
    filtered_posts = []
    for post in all_posts:
        if clear_filters == 'true':
            filtered_posts.append(post)
            continue
        
        if has_photo == 'yes':
            if not post.photos or not isinstance(post.photos, list) or len(post.photos) == 0:
                continue
        elif has_photo == 'no':
            if post.photos and isinstance(post.photos, list) and len(post.photos) > 0:
                continue
        
        if has_video == 'yes':
            if not post.videos or not isinstance(post.videos, list) or len(post.videos) == 0:
                continue
        elif has_video == 'no':
            if post.videos and isinstance(post.videos, list) and len(post.videos) > 0:
                continue
        
        if has_links == 'yes':
            if not post.links or not isinstance(post.links, list) or len(post.links) == 0:
                continue
        elif has_links == 'no':
            if post.links and isinstance(post.links, list) and len(post.links) > 0:
                continue
        
        filtered_posts.append(post)
    
    return render_template('timeline.html', posts=filtered_posts, user_data=user_data)


@app.route('/import-data', methods=['GET', 'POST'])
def import_data():
    if request.method == 'POST':
        if 'facebook_data' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(request.url)
        
        file = request.files['facebook_data']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and file.filename.endswith('.zip'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Extract zip
            import zipfile
            extract_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'extracted')
            os.makedirs(extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Import data
            importer = FacebookDataImporter(extract_dir)
            stats = importer.import_all()
            
            # Clean up
            os.remove(filepath)
            
            flash(f"Import complete! Posts: {stats['posts_imported']} imported, "
                  f"{stats['posts_updated']} updated, {stats['posts_skipped']} skipped. "
                  f"Comments: {stats['comments_imported']} imported.", 'success')
            
            if stats['errors']:
                for error in stats['errors'][:5]:  # Show first 5 errors
                    flash(error, 'warning')
            
            return redirect(url_for('timeline'))
    
    return render_template('import.html')


@app.route('/refresh-comments/<post_id>')
def refresh_comments(post_id):
    """Refresh comments for a specific post"""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    
    access_token = session['access_token']
    
    # Fetch fresh comments
    comments = process_comments(post_id, access_token)
    
    # Update post in database
    post = Post.query.filter_by(facebook_id=post_id).first()
    if post:
        post.comments = comments if comments else None
        
        # Update Comment table
        for comment in comments:
            existing_comment = Comment.query.filter_by(facebook_id=comment['id']).first()
            if not existing_comment:
                new_comment = Comment(
                    facebook_id=comment['id'],
                    post_id=post_id,
                    message=comment['message'],
                    created_time=comment['created_time'],
                    from_data=comment['from'],
                    like_count=comment['like_count']
                )
                db.session.add(new_comment)
        
        db.session.commit()
    
    return redirect(url_for('timeline'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)