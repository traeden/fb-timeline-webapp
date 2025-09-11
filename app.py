from flask import Flask, redirect, request, session, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
import os
from dotenv import load_dotenv
import requests
from datetime import datetime, timedelta
from sqlalchemy import func, or_, and_
from urllib.parse import urlencode

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
    
    # Construct full redirect_uri with query parameters
    full_redirect_uri = REDIRECT_URI
    if params:
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
    
    # Use the redirect_uri from the request if available, falling back to session
    redirect_uri = request.url if request.url.startswith(REDIRECT_URI) else original_redirect_uri
    
    # Retrieve parameters from session
    api_filters = session.get('api_filters', {})
    api_start_date = api_filters.get('start_date')
    api_end_date = api_filters.get('end_date')
    api_post_type = api_filters.get('post_type')
    
    # Debug: Print callback parameters
    print(f"Callback retrieved - api_start_date: {api_start_date}, api_end_date: {api_end_date}, api_post_type: {api_post_type}")
    print(f"Using redirect_uri: {redirect_uri}")
    
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
    
    # Use the matched redirect_uri for the token request
    token_url = (
        f'https://graph.facebook.com/v18.0/oauth/access_token'
        f'?client_id={FB_APP_ID}'
        f'&redirect_uri={redirect_uri}'
        f'&client_secret={FB_APP_SECRET}'
        f'&code={code}'
    )
    
    response = requests.get(token_url)
    data = response.json()
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
    
    # Get display filters from request (for server-side filtering) - CLEANED UP
    display_start_date = request.args.get('display_start_date')
    display_end_date = request.args.get('display_end_date')
    keyword = request.args.get('keyword')
    has_photo = request.args.get('has_photo')
    has_video = request.args.get('has_video')
    min_length = request.args.get('min_length')
    max_length = request.args.get('max_length')
    has_tags = request.args.get('has_tags')
    clear_filters = request.args.get('clear_filters')
    
    # Clean up keyword parameter
    if keyword and (keyword.strip() == '' or keyword.lower() == 'none'):
        keyword = None
    
    # Debug: Print all filters
    print(f"API filters - start: {api_start_date}, end: {api_end_date}, type: {api_post_type}")
    print(f"Display filters - start: {display_start_date}, end: {display_end_date}")
    print(f"Other filters - keyword: {keyword}, photo: {has_photo}, video: {has_video}")
    print(f"Length filters - min: {min_length}, max: {max_length}, tags: {has_tags}")
    
    # Only fetch from API if we have API filters (avoid unnecessary API calls)
    if api_start_date or api_end_date or api_post_type:
        # Set defaults for API filters
        if not api_start_date:
            api_start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        if not api_end_date:
            api_end_date = datetime.now().strftime('%Y-%m-%d')
        
        # Parse and validate API dates
        try:
            api_start_date = datetime.strptime(api_start_date, '%Y-%m-%d').strftime('%Y-%m-%d')
            api_end_date = datetime.strptime(api_end_date, '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError:
            return "Invalid API date format. Please ensure dates are in YYYY-MM-DD format.", 400
        
        # Build Facebook API parameters
        since_param = f'&since={api_start_date}'
        until_param = f'&until={api_end_date}'
        type_param = f'&type={api_post_type}' if api_post_type else ''
        
        # Fetch posts with API-level filtering
        posts_url = (
            f'https://graph.facebook.com/v18.0/me/feed'
            f'?access_token={access_token}'
            f'&fields=id,message,created_time,attachments{{type,media}}'
            f'{since_param}{until_param}{type_param}&limit=100'
        )
        
        print(f"Facebook API URL: {posts_url}")
        
        posts_response = requests.get(posts_url)
        posts_data = posts_response.json()
        
        if 'error' in posts_data:
            if 'Please reduce the amount of data' in posts_data.get('error', {}).get('message', ''):
                return "Error: Too much data requested. Please narrow the date range and retry.", 400
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
                        photo_url=photo_url if photo_url else None,
                        video_url=video_url if video_url else None
                    )
                    db.session.add(new_post)
            db.session.commit()
    
    # Server-side filtering for display
    query = Post.query.order_by(Post.created_time.desc())
    
    # Apply display filters only if clear_filters is not true
    if clear_filters != 'true':
        # Date filtering
        if display_start_date:
            try:
                # Extract date portion from created_time for comparison
                query = query.filter(func.substring(Post.created_time, 1, 10) >= display_start_date)
                print(f"Applied start date filter: {display_start_date}")
            except Exception as e:
                print(f"Error with start date filter: {e}")
        
        if display_end_date:
            try:
                query = query.filter(func.substring(Post.created_time, 1, 10) <= display_end_date)
                print(f"Applied end date filter: {display_end_date}")
            except Exception as e:
                print(f"Error with end date filter: {e}")
        
        # Keyword filtering
        if keyword:
            query = query.filter(Post.message.ilike(f'%{keyword}%'))
            print(f"Applied keyword filter: {keyword}")
        
        # Photo filtering - FIXED LOGIC
        if has_photo == 'yes':
            query = query.filter(and_(Post.photo_url.isnot(None), Post.photo_url != ''))
            print("Applied has_photo=yes filter")
        elif has_photo == 'no':
            query = query.filter(or_(Post.photo_url.is_(None), Post.photo_url == ''))
            print("Applied has_photo=no filter")
        
        # Video filtering - FIXED LOGIC
        if has_video == 'yes':
            query = query.filter(and_(Post.video_url.isnot(None), Post.video_url != ''))
            print("Applied has_video=yes filter")
        elif has_video == 'no':
            query = query.filter(or_(Post.video_url.is_(None), Post.video_url == ''))
            print("Applied has_video=no filter")
        
        # Length filtering
        if min_length:
            try:
                min_len = int(min_length)
                query = query.filter(func.length(Post.message) >= min_len)
                print(f"Applied min_length filter: {min_len}")
            except ValueError:
                pass
        
        if max_length:
            try:
                max_len = int(max_length)
                query = query.filter(func.length(Post.message) <= max_len)
                print(f"Applied max_length filter: {max_len}")
            except ValueError:
                pass
        
        # Tags filtering
        if has_tags == 'yes':
            query = query.filter(Post.message.ilike('%@%'))
            print("Applied has_tags=yes filter")
        elif has_tags == 'no':
            query = query.filter(~Post.message.ilike('%@%'))
            print("Applied has_tags=no filter")
    
    # Execute query and get results
    try:
        db_posts = query.all()
        print(f"Final query returned {len(db_posts)} posts")
        
        # Debug: Print first few posts
        for i, post in enumerate(db_posts[:3]):
            print(f"Post {i+1}: ID={post.facebook_id}, message_len={len(post.message or '')}, photo_url={'YES' if post.photo_url else 'NO'}, video_url={'YES' if post.video_url else 'NO'}")
            
    except Exception as e:
        print(f"Database query error: {e}")
        db_posts = []
    
    return render_template('timeline.html', posts=db_posts, user_data=user_data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
    
    # Add this route to your Flask app for debugging
@app.route('/debug-data')
def debug_data():
    if 'access_token' not in session:
        return "Not logged in"
    
    # Get first 5 posts to examine
    posts = Post.query.limit(5).all()
    
    debug_info = []
    for post in posts:
        info = {
            'id': post.facebook_id,
            'message_length': len(post.message or ''),
            'message_preview': (post.message or '')[:100] + '...' if post.message else 'None',
            'created_time': post.created_time,
            'created_time_type': type(post.created_time).__name__,
            'photo_url': post.photo_url,
            'photo_url_type': type(post.photo_url).__name__,
            'photo_url_is_none': post.photo_url is None,
            'photo_url_is_empty': post.photo_url == '' if post.photo_url is not None else 'N/A',
            'video_url': post.video_url,
            'video_url_type': type(post.video_url).__name__,
            'video_url_is_none': post.video_url is None,
            'video_url_is_empty': post.video_url == '' if post.video_url is not None else 'N/A',
            'has_at_symbol': '@' in (post.message or ''),
        }
        debug_info.append(info)
    
    # Also check total counts
    total_posts = Post.query.count()
    posts_with_photos = Post.query.filter(and_(Post.photo_url.isnot(None), Post.photo_url != '')).count()
    posts_without_photos = Post.query.filter(or_(Post.photo_url.is_(None), Post.photo_url == '')).count()
    posts_with_videos = Post.query.filter(and_(Post.video_url.isnot(None), Post.video_url != '')).count()
    posts_without_videos = Post.query.filter(or_(Post.video_url.is_(None), Post.video_url == '')).count()
    posts_with_tags = Post.query.filter(Post.message.ilike('%@%')).count()
    posts_without_tags = Post.query.filter(~Post.message.ilike('%@%')).count()
    
    return f"""
    <h2>Database Debug Info</h2>
    <h3>Total Counts:</h3>
    <ul>
        <li>Total posts: {total_posts}</li>
        <li>Posts with photos: {posts_with_photos}</li>
        <li>Posts without photos: {posts_without_photos}</li>
        <li>Posts with videos: {posts_with_videos}</li>
        <li>Posts without videos: {posts_without_videos}</li>
        <li>Posts with tags (@): {posts_with_tags}</li>
        <li>Posts without tags: {posts_without_tags}</li>
    </ul>
    
    <h3>Sample Post Data:</h3>
    <pre>{chr(10).join([str(info) for info in debug_info])}</pre>
    """