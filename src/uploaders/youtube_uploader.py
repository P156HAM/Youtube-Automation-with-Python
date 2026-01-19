"""YouTube Data API v3 integration for video uploads."""

import os
import pickle
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ..config import get_config
from ..generators.story_generator import Story


class YouTubeUploader:
    """Handles YouTube video uploads via the Data API v3."""
    
    # OAuth 2.0 scopes for YouTube upload
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    
    # Maximum retries for resumable uploads
    MAX_RETRIES = 10
    
    # Retry status codes
    RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
    
    def __init__(self):
        """Initialize the YouTube uploader."""
        self.config = get_config()
        self.credentials: Optional[Credentials] = None
        self.youtube = None
        
        # Paths for OAuth tokens
        self.state_dir = self.config.get_path('state')
        self.token_path = self.state_dir / 'youtube_token.pickle'
        self.client_secrets_path = self.state_dir / 'client_secrets.json'
    
    def _get_authenticated_service(self):
        """Get or create authenticated YouTube service."""
        if self.youtube:
            return self.youtube
        
        credentials = None
        
        # Load existing token if available
        if self.token_path.exists():
            with open(self.token_path, 'rb') as token:
                credentials = pickle.load(token)
        
        # Refresh or get new credentials
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                if not self.client_secrets_path.exists():
                    raise FileNotFoundError(
                        f"Client secrets file not found at {self.client_secrets_path}\n"
                        "Please download your OAuth 2.0 credentials from Google Cloud Console:\n"
                        "1. Go to https://console.cloud.google.com/apis/credentials\n"
                        "2. Create or select a project\n"
                        "3. Create OAuth 2.0 Client ID (Desktop application)\n"
                        "4. Download the JSON file\n"
                        "5. Save it as 'client_secrets.json' in the state/ directory"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secrets_path),
                    self.SCOPES
                )
                credentials = flow.run_local_server(port=0)
            
            # Save credentials for next run
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, 'wb') as token:
                pickle.dump(credentials, token)
        
        self.credentials = credentials
        self.youtube = build('youtube', 'v3', credentials=credentials)
        
        return self.youtube
    
    def authenticate(self) -> bool:
        """
        Authenticate with YouTube API.
        
        Returns:
            True if authentication successful
        """
        try:
            self._get_authenticated_service()
            print("✓ YouTube authentication successful!")
            return True
        except Exception as e:
            print(f"✗ YouTube authentication failed: {e}")
            return False
    
    def _generate_metadata(self, story: Story) -> Dict[str, Any]:
        """
        Generate video metadata from story.
        
        Args:
            story: Story to generate metadata for
        
        Returns:
            Dictionary with title, description, tags, etc.
        """
        # Get base tags from config
        base_tags = self.config.get('youtube.tags', [])
        
        # Combine with story tags
        all_tags = list(set(base_tags + story.tags))
        
        # Ensure tags don't exceed YouTube's limit (500 characters total)
        final_tags = []
        total_length = 0
        for tag in all_tags:
            if total_length + len(tag) + 1 <= 500:
                final_tags.append(tag)
                total_length += len(tag) + 1
        
        # Generate description
        description = story.description or self.config.get('youtube.default_description', '')
        
        return {
            'title': story.title[:100],  # YouTube title limit
            'description': description[:5000],  # YouTube description limit
            'tags': final_tags,
            'categoryId': self.config.get('youtube.category_id', '23'),  # Comedy
            'privacyStatus': self.config.get('youtube.privacy_status', 'public')
        }
    
    def upload(
        self,
        video_path: str,
        story: Optional[Story] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        thumbnail_path: Optional[str] = None,
        privacy_status: Optional[str] = None,
        notify_subscribers: bool = True
    ) -> Optional[str]:
        """
        Upload a video to YouTube.
        
        Args:
            video_path: Path to the video file
            story: Story object (used to generate metadata if not provided)
            title: Video title (overrides story title)
            description: Video description (overrides story description)
            tags: Video tags (overrides story tags)
            thumbnail_path: Path to custom thumbnail image
            privacy_status: 'public', 'private', or 'unlisted'
            notify_subscribers: Whether to notify subscribers
        
        Returns:
            Video ID if successful, None otherwise
        """
        youtube = self._get_authenticated_service()
        
        # Generate metadata
        if story:
            metadata = self._generate_metadata(story)
        else:
            metadata = {
                'title': title or 'Untitled Video',
                'description': description or '',
                'tags': tags or [],
                'categoryId': self.config.get('youtube.category_id', '23'),
                'privacyStatus': privacy_status or self.config.get('youtube.privacy_status', 'public')
            }
        
        # Override with explicit parameters
        if title:
            metadata['title'] = title
        if description:
            metadata['description'] = description
        if tags:
            metadata['tags'] = tags
        if privacy_status:
            metadata['privacyStatus'] = privacy_status
        
        # Build request body
        body = {
            'snippet': {
                'title': metadata['title'],
                'description': metadata['description'],
                'tags': metadata['tags'],
                'categoryId': metadata['categoryId']
            },
            'status': {
                'privacyStatus': metadata['privacyStatus'],
                'selfDeclaredMadeForKids': False,
                'notifySubscribers': notify_subscribers
            }
        }
        
        # Create media upload
        media = MediaFileUpload(
            video_path,
            mimetype='video/mp4',
            resumable=True,
            chunksize=1024 * 1024  # 1MB chunks
        )
        
        # Execute upload with retry logic
        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        
        response = self._resumable_upload(request)
        
        if response:
            video_id = response['id']
            print(f"✓ Video uploaded successfully!")
            print(f"  Video ID: {video_id}")
            print(f"  URL: https://youtube.com/shorts/{video_id}")
            
            # Upload thumbnail if provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                self._set_thumbnail(video_id, thumbnail_path)
            
            return video_id
        
        return None
    
    def _resumable_upload(self, request) -> Optional[Dict[str, Any]]:
        """
        Execute resumable upload with retry logic.
        
        Args:
            request: Upload request object
        
        Returns:
            Response dictionary if successful, None otherwise
        """
        response = None
        error = None
        retry = 0
        
        while response is None:
            try:
                print("Uploading video...")
                status, response = request.next_chunk()
                
                if status:
                    progress = int(status.progress() * 100)
                    print(f"  Upload progress: {progress}%")
                    
            except HttpError as e:
                if e.resp.status in self.RETRIABLE_STATUS_CODES:
                    error = f"Retriable HTTP error {e.resp.status}: {e.content}"
                else:
                    raise
            except Exception as e:
                error = f"Error during upload: {e}"
            
            if error:
                print(f"  {error}")
                retry += 1
                
                if retry > self.MAX_RETRIES:
                    print("  Maximum retries exceeded, giving up.")
                    return None
                
                # Exponential backoff
                sleep_seconds = random.random() * (2 ** retry)
                print(f"  Retrying in {sleep_seconds:.1f} seconds...")
                time.sleep(sleep_seconds)
                error = None
        
        return response
    
    def _set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """
        Set custom thumbnail for a video.
        
        Args:
            video_id: YouTube video ID
            thumbnail_path: Path to thumbnail image
        
        Returns:
            True if successful
        """
        youtube = self._get_authenticated_service()
        
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            print(f"  ✓ Thumbnail set successfully")
            return True
        except HttpError as e:
            print(f"  ✗ Failed to set thumbnail: {e}")
            return False
    
    def get_channel_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the authenticated channel.
        
        Returns:
            Channel information dictionary
        """
        youtube = self._get_authenticated_service()
        
        try:
            response = youtube.channels().list(
                part='snippet,statistics',
                mine=True
            ).execute()
            
            if response['items']:
                channel = response['items'][0]
                return {
                    'id': channel['id'],
                    'title': channel['snippet']['title'],
                    'description': channel['snippet'].get('description', ''),
                    'subscribers': channel['statistics'].get('subscriberCount', 'Hidden'),
                    'videos': channel['statistics'].get('videoCount', 0),
                    'views': channel['statistics'].get('viewCount', 0)
                }
        except HttpError as e:
            print(f"Failed to get channel info: {e}")
        
        return None
    
    def list_recent_uploads(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        List recent uploads from the authenticated channel.
        
        Args:
            max_results: Maximum number of videos to return
        
        Returns:
            List of video information dictionaries
        """
        youtube = self._get_authenticated_service()
        
        try:
            # Get uploads playlist ID
            channels_response = youtube.channels().list(
                part='contentDetails',
                mine=True
            ).execute()
            
            if not channels_response['items']:
                return []
            
            uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Get videos from uploads playlist
            playlist_response = youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=max_results
            ).execute()
            
            videos = []
            for item in playlist_response.get('items', []):
                snippet = item['snippet']
                videos.append({
                    'id': snippet['resourceId']['videoId'],
                    'title': snippet['title'],
                    'description': snippet['description'],
                    'published_at': snippet['publishedAt'],
                    'thumbnail': snippet['thumbnails'].get('medium', {}).get('url')
                })
            
            return videos
            
        except HttpError as e:
            print(f"Failed to list uploads: {e}")
            return []


# Example usage
if __name__ == "__main__":
    uploader = YouTubeUploader()
    
    # Check if we can authenticate
    if uploader.authenticate():
        # Get channel info
        info = uploader.get_channel_info()
        if info:
            print(f"\nChannel: {info['title']}")
            print(f"Subscribers: {info['subscribers']}")
            print(f"Total videos: {info['videos']}")

