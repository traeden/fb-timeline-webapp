#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Oct  4 22:15:48 2025

@author: traedennord
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
New timeline data model with local media storage
"""

from models import db  # Import the EXISTING db from models.py
from sqlalchemy.dialects.postgresql import JSON

class TimelineData(db.Model):
    """
    New timeline model that stores media files locally instead of URLs
    """
    __tablename__ = 'timeline_data'
    
    id = db.Column(db.Integer, primary_key=True)
    facebook_id = db.Column(db.String(100), unique=True, index=True)
    message = db.Column(db.Text)
    created_time = db.Column(db.String(50), index=True)
    
    # Media stored as local file paths
    photos = db.Column(JSON, nullable=True)
    videos = db.Column(JSON, nullable=True)
    links = db.Column(JSON, nullable=True)
    
    from_data = db.Column(JSON, nullable=True)
    comments = db.Column(JSON, nullable=True)
    
    source = db.Column(db.String(20), default='api_v2')
    media_quality = db.Column(db.String(20), default='high')
    
    def __repr__(self):
        return f'<TimelineData {self.facebook_id}>'
