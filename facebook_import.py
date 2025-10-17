#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook Data Importer with File Existence Validation
"""

import json
import os
from datetime import datetime, timedelta
from models_v2 import TimelineData
from models import db, Comment  # Import db and Comment from original models
from sqlalchemy import and_
import subprocess
from PIL import Image
from io import BytesIO

def _generate_video_thumbnail(self, video_path):
    """Generate thumbnail from video file using ffmpeg"""
    try:
        # Output path for thumbnail
        thumbnail_path = video_path.rsplit('.', 1)[0] + '_thumb.jpg'
        
        # Use ffmpeg to extract frame at 1 second
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', '00:00:01',  # Grab frame at 1 second
            '-vframes', '1',
            '-q:v', '2',  # Quality
            thumbnail_path,
            '-y'  # Overwrite if exists
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        
        # Return relative path
        return thumbnail_path.replace('uploads/', '/uploads/')
        
    except Exception as e:
        print(f"    ⚠️  Failed to generate thumbnail: {e}")
        return None



class FacebookDataImporter:
    """
    Handles importing Facebook data from official data download.
    
    Expected structure:
    - posts/your_posts_1.json (or similar)
    - comments/comments.json
    - photos_and_videos/ (optional)
    """
    
    def __init__(self, data_directory):
        self.data_directory = data_directory
        self.stats = {
            'posts_imported': 0,
            'posts_skipped': 0,
            'posts_updated': 0,
            'comments_imported': 0,
            'media_skipped': 0,
            'errors': []
        }
        
    def import_all(self, start_date='2023-05-01', end_date='2023-05-31'):
        """Import all available data from Facebook export"""
        try:
            self.date_filter = {'start': start_date, 'end': end_date}
            self.import_posts()
            self.import_comments()
            return self.stats
        except Exception as e:
            self.stats['errors'].append(f"Import failed: {str(e)}")
            return self.stats
    
    def _file_exists(self, uri):
        """Check if a file actually exists on disk."""
        full_path = os.path.join(self.data_directory, uri)
        exists = os.path.isfile(full_path)
        
        print(f"          Checking file: {full_path}")
        print(f"          File exists: {exists}")
        
        if not exists:
            self.stats['media_skipped'] += 1
        
        return exists
    
    def import_posts(self):
        """Import posts from Facebook data export"""
        possible_paths = [
            'posts',
            'your_facebook_activity/posts',
            os.path.join('your_facebook_activity', 'posts')
        ]
        
        posts_dir = None
        for path in possible_paths:
            test_path = os.path.join(self.data_directory, path)
            if os.path.exists(test_path):
                posts_dir = test_path
                print(f"Found posts directory at: {posts_dir}")
                break
        
        if not posts_dir:
            self.stats['errors'].append(
                f"No posts directory found. Searched: {possible_paths}. "
                f"Available directories: {os.listdir(self.data_directory)}"
            )
            return
        
        json_files_to_check = [
            'your_posts__check_ins__photos_and_videos_1.json',
            'edits_you_made_to_posts.json',
            'content_sharing_links_you_have_created.json'
        ]
    
        for filename in os.listdir(posts_dir):
            if filename.endswith('.json') and filename not in json_files_to_check:
                json_files_to_check.append(filename)
        
        print(f"Found JSON files in posts directory: {json_files_to_check}")
        
        for filename in json_files_to_check:
            filepath = os.path.join(posts_dir, filename)
            if os.path.exists(filepath):
                print(f"Processing: {filename}")
                self._process_posts_file(filepath)
            else:
                print(f"Skipping (not found): {filename}")
            
    def _process_posts_file(self, filepath):
        """Process a single posts JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"File structure keys: {data.keys() if isinstance(data, dict) else 'list'}")
            
            posts = []
            
            if isinstance(data, list):
                posts = data
            elif isinstance(data, dict):
                for key in ['posts', 'status_updates', 'photos', 'videos', 'data']:
                    if key in data:
                        posts = data[key] if isinstance(data[key], list) else [data[key]]
                        break
                
                if not posts and 'timestamp' in data:
                    posts = [data]
            
            print(f"Found {len(posts)} posts in {os.path.basename(filepath)}")
            
            for post_data in posts:
                self._import_single_post(post_data)            
    
        except json.JSONDecodeError as e:
            self.stats['errors'].append(f"Invalid JSON in {filepath}: {str(e)}")
        except Exception as e:
            self.stats['errors'].append(f"Error processing {filepath}: {str(e)}")           
            
 
    def _generate_post_id(self, post_data):
        """Generate a consistent ID for posts without one"""
        timestamp = self._extract_timestamp(post_data)
        message_hash = hash(str(post_data.get('data', [{}])[0].get('post', '')))
        return f"import_{timestamp}_{abs(message_hash)}"

    def normalize_message(self, message):
        """Remove encoding differences for comparison"""
        if not message:
            return ""
        return ' '.join(message.strip().split())
    
    def _extract_message(self, post_data):
        """Extract post message from various Facebook export formats"""
        message = ''
        
        if 'data' in post_data and isinstance(post_data['data'], list):
            if post_data['data']:
                message = post_data['data'][0].get('post', '')
        else:
            message = post_data.get('message', '')
        
        if message:
            try:
                message = message.encode('latin1').decode('utf-8')
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
        
        return message    
    
    def _extract_timestamp(self, post_data):
        """Extract and normalize timestamp"""
        timestamp = post_data.get('timestamp', 0)
        if isinstance(timestamp, int):
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%dT%H:%M:%S+0000')
        return post_data.get('created_time', '')
    
    def _import_single_post(self, post_data):
        """Import a single post, handling duplicates intelligently"""
        try:
            created_time = self._extract_timestamp(post_data)
            
            # Skip posts outside May 2023 for testing
            post_date = created_time[:10]
            if post_date < '2023-05-01' or post_date > '2023-05-31':
                self.stats['posts_skipped'] += 1
                return
            
            print(f"\n  Processing post from {created_time}")
            
            # Extract all data first
            message = self._extract_message(post_data)
            print(f"    Message: {message[:50] if message else 'None'}...")
            
            photos = self._extract_photos(post_data)
            videos = self._extract_videos(post_data)
            links = self._extract_links(post_data)
            from_data = self._extract_author(post_data)
            
            # Create fingerprint for duplicate detection
            photo_count = len(photos) if photos else 0
            video_count = len(videos) if videos else 0
            normalized_message = self.normalize_message(message) if message else ""
            
            print(f"    Media counts - Photos: {photo_count}, Videos: {video_count}")
            
            # Search for duplicates within 2-day window
            try:
                date_obj = datetime.strptime(created_time[:10], '%Y-%m-%d')
                date_before = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')
                date_after = (date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
                
                existing_posts = TimelineData.query.filter(
                    and_(
                        TimelineData.created_time >= f"{date_before}T00:00:00",
                        TimelineData.created_time <= f"{date_after}T23:59:59"
                    )
                ).all()
                
                print(f"    Found {len(existing_posts)} existing posts in date window")
                
                # Check each existing post for matching fingerprint
                for existing in existing_posts:
                    existing_photo_count = len(existing.photos) if existing.photos else 0
                    existing_video_count = len(existing.videos) if existing.videos else 0
                    existing_message = self.normalize_message(existing.message) if existing.message else ""
                    
                    # Duplicate if: same message AND same media counts
                    if (normalized_message == existing_message and 
                        photo_count == existing_photo_count and 
                        video_count == existing_video_count):
                        
                        print(f"  🔍 Duplicate detected:")
                        print(f"     Message match: {normalized_message[:50]}...")
                        print(f"     Photos: {photo_count} (existing: {existing_photo_count})")
                        print(f"     Videos: {video_count} (existing: {existing_video_count})")
                        self.stats['posts_skipped'] += 1
                        return
            except Exception as e:
                print(f"    ⚠️  Error in duplicate detection: {e}")
                print(f"    Continuing with import anyway...")
            
            # Generate post ID
            post_id = self._generate_post_id(post_data)
            print(f"    Generated ID: {post_id}")
            
            # Create new post in TimelineData table
            new_post = TimelineData(
                facebook_id=post_id,
                message=message,
                created_time=created_time,
                photos=photos,
                videos=videos,
                links=links,
                from_data=from_data,
                source='import'
            )
            
            db.session.add(new_post)
            self.stats['posts_imported'] += 1
            print(f"  ✅ Added to session: {post_id}")
            
            db.session.commit()
            print(f"  ✅ Committed to database")
            
        except Exception as e:
            print(f"  ❌ ERROR importing post: {e}")
            import traceback
            traceback.print_exc()
            self.stats['errors'].append(f"Error importing post: {str(e)}")
            db.session.rollback()    
            
    def _extract_photos(self, post_data):
            """Extract photos from export format - ONLY if files exist"""
            photos = []
            
            attachments = post_data.get('attachments', [])
            print(f"    📸 Processing attachments, found {len(attachments)} attachment groups")
            
            for idx, attachment in enumerate(attachments):
                if 'data' in attachment:
                    print(f"      Attachment group {idx}: {len(attachment['data'])} items")
                    for item_idx, item in enumerate(attachment['data']):
                        if 'media' in item and 'uri' in item['media']:
                            uri = item['media']['uri']
                            print(f"        Item {item_idx}: URI = {uri}")
                            
                            is_video = 'video' in uri.lower() or uri.endswith(('.mp4', '.mov', '.avi'))
                            print(f"          Is video? {is_video}")
                            
                            if not is_video:
                                if self._file_exists(uri):
                                    photos.append({
                                        'src': f'/uploads/extracted/{uri}',
                                        'width': 0,
                                        'height': 0,
                                        'url': '',
                                        'title': item['media'].get('title', '')
                                    })
                                    print(f"          ✅ Added photo")
                                else:
                                    print(f"          ❌ Photo file not found")
                            else:
                                print(f"          ⏭️  Skipping (is video)")
            
            print(f"    📸 Total photos added: {len(photos)}")
            return photos if photos else None
        
    def _extract_videos(self, post_data):
        """Extract videos from export format - ONLY if files exist"""
        videos = []
        
        attachments = post_data.get('attachments', [])
        print(f"    🎥 Processing video attachments, found {len(attachments)} attachment groups")
        
        for idx, attachment in enumerate(attachments):
            if 'data' in attachment:
                for item_idx, item in enumerate(attachment['data']):
                    if 'media' in item and 'uri' in item['media']:
                        uri = item['media']['uri']
                        
                        is_video = 'video' in uri.lower() or uri.endswith(('.mp4', '.mov', '.avi'))
                        
                        if is_video:
                            if self._file_exists(uri):
                                # Get full path for thumbnail generation
                                full_video_path = os.path.join(self.data_directory, uri)
                                
                                # Generate thumbnail
                                thumbnail = self._generate_video_thumbnail(full_video_path)
                                
                                videos.append({
                                    'src': f'/uploads/extracted/{uri}',
                                    'thumbnail': thumbnail or '',  # Use generated thumbnail
                                    'url': '',
                                    'title': item['media'].get('title', ''),
                                    'description': item['media'].get('description', '')
                                })
                                print(f"          ✅ Added video with thumbnail: {thumbnail}")
        
        print(f"    🎥 Total videos added: {len(videos)}")
        return videos if videos else None    

    def _generate_video_thumbnail(self, video_path):
        """Generate thumbnail from first frame of video"""
        try:
            from PIL import Image
            import subprocess
            
            # Create thumbnail path
            thumbnail_path = video_path.rsplit('.', 1)[0] + '_thumb.jpg'
            
            # Use ffmpeg to extract first frame
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', '00:00:01',
                '-vframes', '1',
                '-vf', 'scale=320:-1',  # Resize to 320px wide
                '-q:v', '2',
                thumbnail_path,
                '-y'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if os.path.exists(thumbnail_path):
                # Return web path
                return thumbnail_path.replace('uploads/', '/uploads/')
            else:
                print(f"    ⚠️  Thumbnail generation failed")
                return None
                
        except Exception as e:
            print(f"    ⚠️  Error generating thumbnail: {e}")
            return None

    def _extract_links(self, post_data):
        """Extract shared links"""
        links = []
        attachments = post_data.get('attachments', [])
        
        for attachment in attachments:
            if 'data' in attachment:
                for item in attachment['data']:
                    if 'external_context' in item:
                        ext = item['external_context']
                        links.append({
                            'url': ext.get('url', ''),
                            'title': item.get('title', ''),
                            'description': item.get('description', ''),
                            'thumbnail': '',
                            'domain': ext.get('url', '').split('/')[2] if ext.get('url') else ''
                        })
        
        return links if links else None
    
    def _extract_author(self, post_data):
        """Extract author information"""
        return {'name': 'You', 'id': 'self'}
    
    def import_comments(self):
        """Import comments from Facebook export"""
        comments_file = os.path.join(self.data_directory, 'comments', 'comments.json')
        
        if not os.path.exists(comments_file):
            return
        
        try:
            with open(comments_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            comments = data.get('comments', []) if isinstance(data, dict) else data
            
            for comment_data in comments:
                self._import_single_comment(comment_data)
                
        except Exception as e:
            self.stats['errors'].append(f"Error importing comments: {str(e)}")
    
    def _import_single_comment(self, comment_data):
        """Import a single comment"""
        try:
            comment_id = comment_data.get('id') or f"import_comment_{hash(str(comment_data))}"
            
            existing = Comment.query.filter_by(facebook_id=comment_id).first()
            if existing:
                return
            
            new_comment = Comment(
                facebook_id=comment_id,
                post_id=comment_data.get('post_id', ''),
                message=comment_data.get('comment', ''),
                created_time=self._extract_timestamp(comment_data),
                from_data=comment_data.get('author', {}),
                like_count=0
            )
            db.session.add(new_comment)
            self.stats['comments_imported'] += 1
            db.session.commit()
            
        except Exception as e:
            self.stats['errors'].append(f"Error importing comment: {str(e)}")
            db.session.rollback()