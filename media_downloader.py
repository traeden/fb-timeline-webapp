#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Oct  4 22:05:29 2025

@author: traedennord
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Media downloader for Facebook API content
Downloads photos and videos and stores them locally
"""

import os
import requests
from datetime import datetime
import hashlib
from PIL import Image
from io import BytesIO

class MediaDownloader:
    """
    Downloads and processes media from Facebook API
    Supports quality selection for images
    """
    
    def __init__(self, base_upload_dir='uploads/api'):
        self.base_upload_dir = base_upload_dir
        os.makedirs(base_upload_dir, exist_ok=True)
        
    def _generate_filename(self, url, media_type='photo'):
        """Generate unique filename from URL"""
        # Extract Facebook ID from URL if possible
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        extension = '.jpg' if media_type == 'photo' else '.mp4'
        return f"{timestamp}_{url_hash}{extension}"
    
    def _create_date_folder(self, created_time):
        """Create folder structure based on post date"""
        # Extract date from created_time: 2023-05-08T12:36:14+0000
        date_str = created_time[:10]  # Gets YYYY-MM-DD
        year_month = date_str[:7]  # Gets YYYY-MM
        
        folder_path = os.path.join(self.base_upload_dir, year_month, date_str)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path
    
    def download_photo(self, photo_url, created_time, quality='high'):
        """
        Download and save a photo with quality control
        
        Args:
            photo_url: URL to the photo
            created_time: Post creation time for folder organization
            quality: 'low', 'medium', or 'high'
        
        Returns:
            dict with local file info or None if failed
        """
        try:
            print(f"      Downloading photo: {photo_url[:50]}...")
            
            # Download image
            response = requests.get(photo_url, timeout=30)
            response.raise_for_status()
            
            # Open image with PIL
            img = Image.open(BytesIO(response.content))
            original_width, original_height = img.size
            
            # Apply quality settings
            if quality == 'low':
                # Max 800px on longest side, 60% JPEG quality
                max_size = 800
                jpeg_quality = 60
            elif quality == 'medium':
                # Max 1200px on longest side, 80% JPEG quality
                max_size = 1200
                jpeg_quality = 80
            else:  # high
                # Max 1920px on longest side, 95% JPEG quality
                max_size = 1920
                jpeg_quality = 95
            
            # Resize if needed
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                print(f"        Resized from {original_width}x{original_height} to {img.size[0]}x{img.size[1]}")
            
            # Convert RGBA to RGB if necessary
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Save to disk
            folder_path = self._create_date_folder(created_time)
            filename = self._generate_filename(photo_url, 'photo')
            filepath = os.path.join(folder_path, filename)
            
            img.save(filepath, 'JPEG', quality=jpeg_quality, optimize=True)
            file_size = os.path.getsize(filepath)
            
            print(f"        ✅ Saved: {filepath} ({file_size // 1024}KB)")
            
            # Return relative path from uploads directory
            relative_path = filepath.replace('uploads/', '/uploads/')
            
            return {
                'src': relative_path,
                'width': img.size[0],
                'height': img.size[1],
                'url': photo_url,
                'title': '',
                'file_size': file_size
            }
            
        except Exception as e:
            print(f"        ❌ Failed to download photo: {e}")
            return None
    
    def download_video(self, video_url, created_time, thumbnail_url=None):
        """
        Download and save a video
        
        Args:
            video_url: URL to the video
            created_time: Post creation time for folder organization
            thumbnail_url: Optional thumbnail URL
        
        Returns:
            dict with local file info or None if failed
        """
        try:
            print(f"      Downloading video: {video_url[:50]}...")
            
            # Download video
            response = requests.get(video_url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Save video
            folder_path = self._create_date_folder(created_time)
            filename = self._generate_filename(video_url, 'video')
            filepath = os.path.join(folder_path, filename)
            
            # Stream download for large files
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = os.path.getsize(filepath)
            print(f"        ✅ Saved video: {filepath} ({file_size // (1024*1024)}MB)")
            
            # Download thumbnail if provided
            thumbnail_path = None
            if thumbnail_url:
                try:
                    thumb_response = requests.get(thumbnail_url, timeout=30)
                    thumb_response.raise_for_status()
                    
                    thumb_filename = self._generate_filename(thumbnail_url + '_thumb', 'photo')
                    thumb_filepath = os.path.join(folder_path, thumb_filename)
                    
                    with open(thumb_filepath, 'wb') as f:
                        f.write(thumb_response.content)
                    
                    thumbnail_path = thumb_filepath.replace('uploads/', '/uploads/')
                    print(f"        ✅ Saved thumbnail: {thumb_filepath}")
                    
                except Exception as e:
                    print(f"        ⚠️ Failed to download thumbnail: {e}")
            
            # Return relative path from uploads directory
            relative_path = filepath.replace('uploads/', '/uploads/')
            
            return {
                'src': relative_path,
                'thumbnail': thumbnail_path or '',
                'url': video_url,
                'title': '',
                'description': '',
                'file_size': file_size
            }
            
        except Exception as e:
            print(f"        ❌ Failed to download video: {e}")
            return None
    
    def get_storage_stats(self):
        """Get statistics about stored media"""
        total_size = 0
        file_count = 0
        
        for root, dirs, files in os.walk(self.base_upload_dir):
            for file in files:
                filepath = os.path.join(root, file)
                total_size += os.path.getsize(filepath)
                file_count += 1
        
        return {
            'total_size_mb': total_size / (1024 * 1024),
            'file_count': file_count
        }