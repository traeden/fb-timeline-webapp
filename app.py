#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Sep 12 12:54:57 2025

@author: traedennord
"""

from flask import Flask, redirect, request, session, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
import os
from dotenv import load_dotenv
import requests
import json
from datetime import datetime, timedelta
from sqlalchemy import func, or_, and_
from urllib.parse import urlencode
from sqlalchemy.dialects.postgresql import JSON

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
    photos = db.Column(JSON, nullable=True)  # Array of photo objects
    videos = db.Column(JSON, nullable=True)  # Array of video objects
    links = db.Column(JSON, nullable=True)   # Array of link objects

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
            print(f"    Added video: {video_data['src'][:50] if video_data['src'] else 'no source'}...")
            
        # Handle albums (can contain photos, videos, or mixed media)
        elif attachment_type == 'album':
            subattachments = attachment.get('subattachments', {}).get('data', [])
            print(f"    Processing album with {len(subattachments)} subattachments")
            for subattachment in subattachments:
                sub_type = subattachment.get('type', '')
                sub_media_type = subattachment.get('media_type', '')
                print(f"      Subattachment: type={sub_type}, media_type={sub_media_type}")
                
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
                        print(f"        Added photo: {media['image'].get('src', '')[:50]}...")
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
                    print(f"        Added video: {video_data['src'][:50] if video_data['src'] else 'no source'}...")
                        
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
            print(f"    Added link: {link_data['url'][:50] if link_data['url'] else 'no url'}...")
        
        # Handle restricted/unavailable content
        elif attachment_type == 'native_templates':
            print(f"    Skipping restricted content: {attachment.get('title', 'No title')}")
    
    return photos, videos, links

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login')
def login():
    api_start_date = request.args.get('api_start_date')
    api_end_date = request.args.get('api_end_date')
    api_post_type = request.args.get('api_post_type')
    
    # Debug: Print what we received from the form
    print(f"Login received - api_start_date: {api_start_date}, api_end_date: {api_end_date}, api_post_type: {api_post_type}")
    
    # Store parameters in session
    session['api_filters'] = {
        'start_date': api_start_date,
        'end_date': api_end_date,
        'post_type': api_post_type
    }
    
    # Build query parameters properly
    params = {}
    if api_start_date is not None:
        params['api_start_date'] = api_start_date
    if api_end_date is not None:
        params['api_end_date'] = api_end_date
    if api_post_type is not None:
        params['api_post_type'] = api_post_type
    
    # Construct full redirect_uri with query parameters (only if params exist and are not empty)
    full_redirect_uri = REDIRECT_URI
    if params and any(v for v in params.values() if v):  # Only add params if they have values
        full_redirect_uri += '?' + urlencode(params)
    
    # Store the full redirect_uri in session
    session['original_redirect_uri'] = full_redirect_uri
    
    print(f"OAuth redirect_uri: {full_redirect_uri}")
    
    fb_login_url = (
        f'https://www.facebook.com/v18.0/dialog/oauth'
        f'?client_id={FB_APP_ID}'
        f'&redirect_uri={full_redirect_uri}'
        f'&scope=public_profile,user_posts'
    )
    return redirect(fb_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return 'Error: No code received', 400
    
    # Retrieve the original redirect_uri from session
    original_redirect_uri = session.get('original_redirect_uri', REDIRECT_URI)
    
    # Retrieve parameters from session
    api_filters = session.get('api_filters', {})
    api_start_date = api_filters.get('start_date')
    api_end_date = api_filters.get('end_date')
    api_post_type = api_filters.get('post_type')
    
    # Debug: Print callback parameters
    print(f"Callback retrieved - api_start_date: {api_start_date}, api_end_date: {api_end_date}, api_post_type: {api_post_type}")
    
    # Add all query parameters, preserving session values
    query_params = {}
    if api_start_date is not None:
        query_params['api_start_date'] = api_start_date
    if api_end_date is not None:
        query_params['api_end_date'] = api_end_date
    if api_post_type is not None:
        query_params['api_post_type'] = api_post_type
    
    # Pass all filters to timeline, including empty ones
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
    
    print(f"Redirecting to timeline with: {redirect_url}")
    
    # Use the EXACT same redirect_uri that was used in the OAuth request (including query parameters)
    token_url = (
        f'https://graph.facebook.com/v18.0/oauth/access_token'
        f'?client_id={FB_APP_ID}'
        f'&redirect_uri={original_redirect_uri}'
        f'&client_secret={FB_APP_SECRET}'
        f'&code={code}'
    )
    
    print(f"Token URL: {token_url}")
    print(f"Using redirect_uri: {original_redirect_uri}")
    print(f"Original redirect_uri from session: {original_redirect_uri}")
    
    response = requests.get(token_url)
    data = response.json()
    
    print(f"Token response status: {response.status_code}")
    print(f"Token response data: {data}")
    
    access_token = data.get('access_token')
    
    if not access_token:
        return f'Error: No access token received - {data}', 400
    
    session['access_token'] = access_token
    
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
    
    # Get API filters from request (for data fetch)
    api_start_date = request.args.get('api_start_date')
    api_end_date = request.args.get('api_end_date')
    api_post_type = request.args.get('api_post_type')
    
    # Get display filters from request (for server-side filtering)
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
    
    # Clean up keyword parameter
    if keyword and (keyword.strip() == '' or keyword.lower() == 'none'):
        keyword = None
    
    # Debug: Print all filters
    print(f"API filters - start: {api_start_date}, end: {api_end_date}, type: {api_post_type}")
    print(f"Display filters - start: {display_start_date}, end: {display_end_date}, keyword: {keyword}, photo: {has_photo}, video: {has_video}, links: {has_links}")
    print(f"Length filters - min: {min_length}, max: {max_length}, tags: {has_tags}")
    
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
    
    # Fetch posts from API (always fetch recent posts if no filters, or filtered posts if filters provided)
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
                # Add 23:59:59 to end date to include the entire day
                end_datetime = datetime.strptime(api_end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                end_timestamp = int(end_datetime.timestamp())
                until_param = f'&until={end_timestamp}'
            except ValueError:
                pass
        
        type_param = f'&type={api_post_type}' if api_post_type else ''
        
        # Set default limit based on whether filters are provided
        limit = '100' if (api_start_date or api_end_date or api_post_type) else '20'
        
        posts_url = (
            f'https://graph.facebook.com/v18.0/me/feed'
            f'?access_token={access_token}'
            f'&fields=id,message,created_time,link,attachments{{type,media_type,media,url,title,description,subattachments{{type,media_type,media,url,title,description}},target{{url}}}}'
            f'{since_param}{until_param}{type_param}&limit={limit}'
        )
        
        print(f"Facebook API URL: {posts_url}")
        print(f"API Filters - Start: {api_start_date} ({since_param}), End: {api_end_date} ({until_param}), Type: {api_post_type}")
        
        posts_response = requests.get(posts_url)
        posts_data = posts_response.json()
        
        print(f"API Response Status: {posts_response.status_code}")
        print(f"API Response Keys: {list(posts_data.keys())}")
        
        if 'error' in posts_data:
            print(f"API Error: {posts_data['error']}")
            if 'Please reduce the amount of data' in posts_data.get('error', {}).get('message', ''):
                return "Error: Too much data requested. Please narrow the date range and retry.", 400
            return f"Error fetching posts: {posts_data['error']['message']}", 500
        
        print(f"Raw API Response: {json.dumps(posts_data, indent=2)[:1000]}...")
        
        # Store posts in database with multiple attachments
        with app.app_context():
            print(f"Processing {len(posts_data.get('data', []))} posts from API")
            print(f"Posts data: {json.dumps(posts_data.get('data', [])[:2], indent=2)}")  # Show first 2 posts for debugging
            for post in posts_data.get('data', []):
                existing_post = Post.query.filter_by(facebook_id=post['id']).first()
                if not existing_post:
                    # Debug: Print raw post data
                    print(f"Processing post {post['id']}:")
                    print(f"  Message: {post.get('message', '')[:100]}...")
                    print(f"  Has attachments: {bool(post.get('attachments'))}")
                    print(f"  Has link: {bool(post.get('link'))}")
                    
                    if post.get('attachments'):
                        print(f"  Attachments count: {len(post['attachments'].get('data', []))}")
                        for i, att in enumerate(post['attachments'].get('data', [])):
                            print(f"    Attachment {i}: type={att.get('type')}, media_type={att.get('media_type')}")
                    
                    try:
                        photos, videos, links = process_attachments(post)
                        print(f"  Processed attachments: {len(photos) if photos else 0} photos, {len(videos) if videos else 0} videos, {len(links) if links else 0} links")
                        
                        new_post = Post(
                            facebook_id=post['id'],
                            message=post.get('message', ''),
                            created_time=post['created_time'],
                            photos=photos if photos else None,
                            videos=videos if videos else None,
                            links=links if links else None
                        )
                        db.session.add(new_post)
                        print(f"  Successfully added post {post['id']} to session")
                    except Exception as e:
                        print(f"  ERROR processing post {post['id']}: {e}")
                        # Fallback: store basic post without attachments
                        try:
                            new_post = Post(
                                facebook_id=post['id'],
                                message=post.get('message', ''),
                                created_time=post['created_time'],
                                photos=None,
                                videos=None,
                                links=None
                            )
                            db.session.add(new_post)
                            print(f"  Fallback: stored basic post {post['id']}")
                        except Exception as e2:
                            print(f"  CRITICAL ERROR: Could not store post {post['id']}: {e2}")
                else:
                    print(f"Post {post['id']} already exists, skipping")
            
            try:
                db.session.commit()
                print("Database commit completed successfully")
            except Exception as e:
                print(f"Database commit failed: {e}")
                db.session.rollback()
    
    # Server-side filtering for display
    query = Post.query.order_by(Post.created_time.desc())
    
    # Apply display filters only if clear_filters is not true
    if clear_filters != 'true':
        # Date filtering
        if display_start_date:
            query = query.filter(func.substring(Post.created_time, 1, 10) >= display_start_date)
        if display_end_date:
            query = query.filter(func.substring(Post.created_time, 1, 10) <= display_end_date)
        
        # Keyword filtering
        if keyword:
            query = query.filter(Post.message.ilike(f'%{keyword}%'))
        
        # Photo filtering
        if has_photo == 'yes':
            query = query.filter(and_(Post.photos.isnot(None), func.json_array_length(Post.photos) > 0))
        elif has_photo == 'no':
            query = query.filter(or_(Post.photos.is_(None), func.json_array_length(Post.photos) == 0))
        
        # Video filtering
        if has_video == 'yes':
            query = query.filter(and_(Post.videos.isnot(None), func.json_array_length(Post.videos) > 0))
        elif has_video == 'no':
            query = query.filter(or_(Post.videos.is_(None), func.json_array_length(Post.videos) == 0))
        
        # Links filtering
        if has_links == 'yes':
            query = query.filter(and_(Post.links.isnot(None), func.json_array_length(Post.links) > 0))
        elif has_links == 'no':
            query = query.filter(or_(Post.links.is_(None), func.json_array_length(Post.links) == 0))
        
        # Length filtering
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
        
        # Tags filtering
        if has_tags == 'yes':
            query = query.filter(Post.message.ilike('%@%'))
        elif has_tags == 'no':
            query = query.filter(~Post.message.ilike('%@%'))
    
    db_posts = query.all()
    print(f"Filtered posts count: {len(db_posts)}")
    
    return render_template('timeline.html', posts=db_posts, user_data=user_data)

@app.route('/debug')
def debug():
    """Debug route to see raw API response"""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    access_token = session['access_token']
    
    # Get a few recent posts with full attachment data
    posts_url = (
        f'https://graph.facebook.com/v18.0/me/feed'
        f'?access_token={access_token}'
        f'&fields=id,message,created_time,link,attachments{{type,media_type,media,url,title,description,subattachments{{type,media_type,media,url,title,description}},target{{url}}}}'
        f'&limit=5'
    )
    
    response = requests.get(posts_url)
    data = response.json()
    
    return f"<pre>{json.dumps(data, indent=2)}</pre>"

@app.route('/db-debug')
def db_debug():
    """Debug route to see what's in the database"""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    
    with app.app_context():
        posts = Post.query.order_by(Post.created_time.desc()).limit(10).all()
        db_data = []
        for post in posts:
            db_data.append({
                'id': post.id,
                'facebook_id': post.facebook_id,
                'message': post.message[:100] + '...' if post.message and len(post.message) > 100 else post.message,
                'created_time': post.created_time,
                'photos_count': len(post.photos) if post.photos else 0,
                'videos_count': len(post.videos) if post.videos else 0,
                'links_count': len(post.links) if post.links else 0,
                'photos': post.photos,
                'videos': post.videos,
                'links': post.links
            })
    
    return f"<pre>{json.dumps(db_data, indent=2)}</pre>"

@app.route('/test-fetch')
def test_fetch():
    """Test route to fetch posts without any filters"""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    access_token = session['access_token']
    
    # Simple API call without any filters
    posts_url = (
        f'https://graph.facebook.com/v18.0/me/feed'
        f'?access_token={access_token}'
        f'&fields=id,message,created_time,link,attachments{{type,media_type,media,url,title,description,subattachments{{type,media_type,media,url,title,description}},target{{url}}}}'
        f'&limit=10'
    )
    
    print(f"Test fetch URL: {posts_url}")
    response = requests.get(posts_url)
    data = response.json()
    
    print(f"Test fetch response: {json.dumps(data, indent=2)}")
    
    return f"<pre>{json.dumps(data, indent=2)}</pre>"

@app.route('/force-fetch')
def force_fetch():
    """Force fetch and store posts without any filters"""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    access_token = session['access_token']
    
    # Simple API call to fetch recent posts
    posts_url = (
        f'https://graph.facebook.com/v18.0/me/feed'
        f'?access_token={access_token}'
        f'&fields=id,message,created_time,link,attachments{{type,media_type,media,url,title,description,subattachments{{type,media_type,media,url,title,description}},target{{url}}}}'
        f'&limit=10'
    )
    
    print(f"Force fetch URL: {posts_url}")
    response = requests.get(posts_url)
    data = response.json()
    
    if 'error' in data:
        return f"<pre>Error: {json.dumps(data, indent=2)}</pre>"
    
    # Store posts in database
    with app.app_context():
        stored_count = 0
        for post in data.get('data', []):
            existing_post = Post.query.filter_by(facebook_id=post['id']).first()
            if not existing_post:
                try:
                    photos, videos, links = process_attachments(post)
                    new_post = Post(
                        facebook_id=post['id'],
                        message=post.get('message', ''),
                        created_time=post['created_time'],
                        photos=photos if photos else None,
                        videos=videos if videos else None,
                        links=links if links else None
                    )
                    db.session.add(new_post)
                    stored_count += 1
                    print(f"Stored post {post['id']}")
                except Exception as e:
                    print(f"Error storing post {post['id']}: {e}")
        
        try:
            db.session.commit()
            return f"<h2>Force Fetch Complete</h2><p>Stored {stored_count} new posts</p><pre>{json.dumps(data, indent=2)}</pre>"
        except Exception as e:
            db.session.rollback()
            return f"<h2>Force Fetch Failed</h2><p>Error: {e}</p><pre>{json.dumps(data, indent=2)}</pre>"

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Only create tables if they don't exist
    app.run(debug=True, port=5000)