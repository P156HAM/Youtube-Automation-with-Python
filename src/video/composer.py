"""Video composition module for creating YouTube Shorts from Discord frames."""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

# MoviePy 2.x imports
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    ImageSequenceClip,
    concatenate_videoclips,
)
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut, MultiplyVolume

from ..config import get_config
from ..generators.story_generator import Message, Story
from ..renderers.discord_renderer import DiscordRenderer


class VideoComposer:
    """Composes Discord conversation frames into YouTube Shorts videos."""
    
    def __init__(self):
        """Initialize the video composer."""
        self.config = get_config()
        self.fps = self.config.get('video.fps', 30)
        self.width = self.config.get('discord.width', 1080)
        self.height = self.config.get('discord.height', 1920)
        self.message_delay = self.config.get('discord.message_delay', 1.5)
        self.typing_duration = self.config.get('video.typing_duration', 0.8)
        self.renderer = DiscordRenderer()
    
    def _calculate_durations(
        self,
        story: Story,
        target_duration: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Calculate optimal message and typing durations.
        
        Args:
            story: Story to calculate durations for
            target_duration: Target video duration (uses config if None)
        
        Returns:
            Tuple of (message_duration, typing_duration)
        """
        num_messages = len(story.messages)
        
        if target_duration is None:
            min_duration = self.config.get('video.duration_min', 30)
            max_duration = self.config.get('video.duration_max', 59)
            # Aim for middle of the range
            target_duration = (min_duration + max_duration) / 2
        
        # Each message has: typing indicator + message display
        # Total frames = num_messages * 2 (typing + display)
        # We want last message to have extra time
        
        # Calculate time per message cycle
        time_per_message = target_duration / num_messages
        
        # Split between typing and display (30% typing, 70% display)
        typing_time = time_per_message * 0.3
        display_time = time_per_message * 0.7
        
        # Clamp to reasonable values
        typing_time = max(0.4, min(1.0, typing_time))
        display_time = max(1.0, min(3.0, display_time))
        
        return display_time, typing_time
    
    def compose_from_frames(
        self,
        frame_paths: List[str],
        output_path: str,
        audio_path: Optional[str] = None,
        message_duration: float = 1.5,
        typing_duration: float = 0.8
    ) -> str:
        """
        Compose video from pre-rendered frames.
        
        Args:
            frame_paths: List of paths to frame images
            output_path: Path to save the output video
            audio_path: Optional path to background music
            message_duration: Duration to show each message frame
            typing_duration: Duration to show typing frames
        
        Returns:
            Path to the output video
        """
        clips = []
        
        for frame_path in frame_paths:
            # Determine if this is a typing frame or message frame
            is_typing = 'typing' in os.path.basename(frame_path)
            duration = typing_duration if is_typing else message_duration
            
            # MoviePy 2.x uses with_duration instead of set_duration
            clip = ImageClip(frame_path, duration=duration)
            clips.append(clip)
        
        # Concatenate all clips
        video = concatenate_videoclips(clips, method="compose")
        
        # Add audio if provided
        if audio_path and os.path.exists(audio_path):
            audio = AudioFileClip(audio_path)
            
            # Trim or loop audio to match video duration
            if audio.duration < video.duration:
                # Loop by concatenating
                loops_needed = int(video.duration / audio.duration) + 1
                audio_clips = [audio] * loops_needed
                from moviepy import concatenate_audioclips
                audio = concatenate_audioclips(audio_clips)
            
            # Trim to video duration (MoviePy 2.x uses subclipped)
            audio = audio.subclipped(0, video.duration)
            
            # Apply fade in/out and volume (MoviePy 2.x uses with_effects)
            fade_in = self.config.get('audio.fade_in', 1.0)
            fade_out = self.config.get('audio.fade_out', 2.0)
            volume = self.config.get('audio.background_music_volume', 0.15)
            
            audio = audio.with_effects([
                AudioFadeIn(fade_in),
                AudioFadeOut(fade_out),
                MultiplyVolume(volume)
            ])
            
            # MoviePy 2.x uses with_audio
            video = video.with_audio(audio)
        
        # Write output
        video.write_videofile(
            output_path,
            fps=self.fps,
            codec=self.config.get('video.codec', 'libx264'),
            audio_codec=self.config.get('video.audio_codec', 'aac'),
            bitrate=self.config.get('video.bitrate', '8M'),
            preset='medium',
            threads=4,
            logger=None  # Suppress verbose output
        )
        
        # Clean up
        video.close()
        
        return output_path
    
    def compose_story(
        self,
        story: Story,
        output_path: str,
        audio_path: Optional[str] = None,
        target_duration: Optional[float] = None,
        cleanup_frames: bool = True
    ) -> str:
        """
        Compose a complete video from a story.
        
        Args:
            story: Story to compose
            output_path: Path to save the output video
            audio_path: Optional path to background music
            target_duration: Target video duration in seconds
            cleanup_frames: Whether to delete temporary frames after composition
        
        Returns:
            Path to the output video
        """
        # Create temporary directory for frames
        tmp_dir = self.config.get_path('renders_tmp')
        story_hash = hash(story.title + str(len(story.messages)))
        frames_dir = tmp_dir / f"frames_{abs(story_hash)}"
        
        try:
            # Render all frames
            print(f"Rendering {len(story.messages)} message frames...")
            frame_paths = self.renderer.render_all_frames(
                story,
                str(frames_dir),
                include_typing=self.config.get('video.typing_animation', True)
            )
            
            # Calculate optimal durations
            message_duration, typing_duration = self._calculate_durations(
                story, target_duration
            )
            
            print(f"Composing video ({message_duration:.1f}s per message, {typing_duration:.1f}s typing)...")
            
            # Compose video from frames
            result = self.compose_from_frames(
                frame_paths,
                output_path,
                audio_path,
                message_duration,
                typing_duration
            )
            
            return result
            
        finally:
            # Cleanup temporary frames
            if cleanup_frames and frames_dir.exists():
                shutil.rmtree(frames_dir)
    
    def compose_with_effects(
        self,
        story: Story,
        output_path: str,
        audio_path: Optional[str] = None,
        sfx_paths: Optional[List[str]] = None,
        target_duration: Optional[float] = None
    ) -> str:
        """
        Compose video with additional effects like notification sounds.
        
        Args:
            story: Story to compose
            output_path: Path to save the output video
            audio_path: Path to background music
            sfx_paths: List of paths to sound effect files
            target_duration: Target video duration
        
        Returns:
            Path to the output video
        """
        # This is an enhanced version that will be used with AudioMixer
        # For now, delegate to the basic compose method
        return self.compose_story(
            story,
            output_path,
            audio_path,
            target_duration
        )
    
    def create_thumbnail(
        self,
        story: Story,
        output_path: str
    ) -> str:
        """
        Create a thumbnail image for the video.
        
        Args:
            story: Story to create thumbnail for
            output_path: Path to save the thumbnail
        
        Returns:
            Path to the thumbnail
        """
        thumbnail = self.renderer.render_thumbnail(story)
        thumbnail.save(output_path, 'PNG')
        return output_path


# Example usage
if __name__ == "__main__":
    from ..generators.story_generator import Story, Message
    
    # Create test story
    test_messages = [
        Message(
            username="TestUser1",
            content="Hello, this is a test message!",
            avatar_color="#f47fff"
        ),
        Message(
            username="TestUser2",
            content="Oh wow, a test? Let me grab my popcorn 🍿",
            avatar_color="#7289da",
            reactions=["😂"]
        ),
    ]
    
    test_story = Story(
        title="Test Composition",
        theme="test",
        messages=test_messages
    )
    
    composer = VideoComposer()
    # composer.compose_story(test_story, "test_video.mp4")
    print("Video composer ready!")

