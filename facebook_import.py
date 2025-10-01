#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep 30 22:39:48 2025

@author: traedennord
"""

import json
import os
from datetime import datetime
from models import db, Post, Comment

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
            'errors': []
        }
    
    def import_all(self):
        """Import all available data from Facebook export"""
        try:
            self.import_posts()
            self.import_comments()
            return self.stats
        except Exception as e:
            self.stats['errors'].append(f"Import failed: {str(e)}")
            return self.stats
    
    def import_posts(self):
        """Import posts from Facebook data export"""
        posts_dir = os.path.join(self.data_directory, 'posts')
        
        if not os.path.exists(posts_dir):
            self.stats['errors'].append("No 'posts' directory found in data export")
            return
        
        # Facebook exports posts in numbered JSON files
        for filename in os.listdir(posts_dir):
            if filename.startswith('your_posts') and filename.endswith('.json'):
                filepath = os.path.join(posts_dir, filename)
                self._process_posts_file(filepath)
    
    def _process_posts_file(self, filepath):
        """Process a single posts JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Facebook export structure varies, adapt as needed
            posts = data if isinstance(data, list) else data.get('posts', [])
            
            for post_data in posts:
                self._import_single_post(post_data)
                
        except Exception as e:
            self.stats['errors'].append(f"Error processing {filepath}: {str(e)}")
    
    def _import_single_post(self, post_data):
        """Import a single post, handling duplicates intelligently"""
        try:
            # Extract post ID - Facebook export may use 'post_id' or generate one
            post_id = post_data.get('post_id') or self._generate_post_id(post_data)
            
            # Check if post already exists
            existing_post = Post.query.filter_by(facebook_id=post_id).first()
            
            # Extract standardized data
            message = self._extract_message(post_data)
            created_time = self._extract_timestamp(post_data)
            photos = self._extract_photos(post_data)
            videos = self._extract_videos(post_data)
            links = self._extract_links(post_data)
            from_data = self._extract_author(post_data)
            
            if existing_post:
                # Update if import has more data (e.g., comments not in API)
                if self._should_update(existing_post, post_data):
                    existing_post.message = message or existing_post.message
                    existing_post.photos = photos or existing_post.photos
                    existing_post.videos = videos or existing_post.videos
                    existing_post.links = links or existing_post.links
                    existing_post.source = 'import'  # Mark as enriched by import
                    self.stats['posts_updated'] += 1
                else:
                    self.stats['posts_skipped'] += 1
            else:
                # Create new post
                new_post = Post(
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
            
            db.session.commit()
            
        except Exception as e:
            self.stats['errors'].append(f"Error importing post: {str(e)}")
            db.session.rollback()
    
    def _generate_post_id(self, post_data):
        """Generate a consistent ID for posts without one"""
        timestamp = self._extract_timestamp(post_data)
        message_hash = hash(str(post_data.get('data', [{}])[0].get('post', '')))
        return f"import_{timestamp}_{abs(message_hash)}"
    
    def _extract_message(self, post_data):
        """Extract post message from various Facebook export formats"""
        # Facebook export structure: data[0].post or message
        if 'data' in post_data and isinstance(post_data['data'], list):
            return post_data['data'][0].get('post', '') if post_data['data'] else ''
        return post_data.get('message', '')
    
    def _extract_timestamp(self, post_data):
        """Extract and normalize timestamp"""
        timestamp = post_data.get('timestamp', 0)
        if isinstance(timestamp, int):
            # Facebook exports use Unix timestamp
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%dT%H:%M:%S+0000')
        return post_data.get('created_time', '')
    
    def _extract_photos(self, post_data):
        """Extract photos from export format"""
        photos = []
        attachments = post_data.get('attachments', [])
        
        for attachment in attachments:
            if 'data' in attachment:
                for item in attachment['data']:
                    if 'media' in item and 'photo_image' in item['media']:
                        photos.append({
                            'src': item['media']['photo_image'].get('uri', ''),
                            'width': 0,  # Export doesn't include dimensions
                            'height': 0,
                            'url': '',
                            'title': item.get('title', '')
                        })
        
        return photos if photos else None
    
    def _extract_videos(self, post_data):
        """Extract videos from export format"""
        videos = []
        attachments = post_data.get('attachments', [])
        
        for attachment in attachments:
            if 'data' in attachment:
                for item in attachment['data']:
                    if 'media' in item and 'video_info' in item['media']:
                        videos.append({
                            'src': item['media']['video_info'].get('uri', ''),
                            'thumbnail': item['media'].get('thumbnail', {}).get('uri', ''),
                            'url': '',
                            'title': item.get('title', ''),
                            'description': item.get('description', '')
                        })
        
        return videos if videos else None
    
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
        # Export format typically doesn't include author for your own posts
        return {'name': 'You', 'id': 'self'}
    
    def _should_update(self, existing_post, new_data):
        """Determine if existing post should be updated with import data"""
        # Update if import has data that API didn't provide
        # For example, tagged posts or more complete media
        return existing_post.source == 'api'  # Prioritize import data
    
    def import_comments(self):
        """Import comments from Facebook export"""
        comments_file = os.path.join(self.data_directory, 'comments', 'comments.json')
        
        if not os.path.exists(comments_file):
            return  # No comments file
        
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