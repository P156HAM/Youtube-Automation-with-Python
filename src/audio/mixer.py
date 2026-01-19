"""Audio mixing module for background music and sound effects."""

import os
import random
from pathlib import Path
from typing import List, Optional, Tuple, Union

from pydub import AudioSegment
from pydub.effects import normalize

from ..config import get_config


class AudioMixer:
    """Handles audio mixing for YouTube Shorts videos."""
    
    # Common audio formats to support
    SUPPORTED_FORMATS = ['.mp3', '.wav', '.ogg', '.m4a', '.flac']
    
    def __init__(self):
        """Initialize the audio mixer."""
        self.config = get_config()
        self.music_volume = self.config.get('audio.background_music_volume', 0.15)
        self.sfx_volume = self.config.get('audio.sfx_volume', 0.3)
        self.fade_in = self.config.get('audio.fade_in', 1.0)
        self.fade_out = self.config.get('audio.fade_out', 2.0)
    
    def _db_from_ratio(self, ratio: float) -> float:
        """Convert volume ratio (0-1) to decibels."""
        if ratio <= 0:
            return -60  # Effectively silent
        import math
        return 20 * math.log10(ratio)
    
    def _get_music_files(self) -> List[Path]:
        """Get list of available music files."""
        music_dir = self.config.get_path('music')
        if not music_dir.exists():
            return []
        
        music_files = []
        for ext in self.SUPPORTED_FORMATS:
            music_files.extend(music_dir.glob(f'*{ext}'))
        
        return music_files
    
    def _get_sfx_files(self) -> List[Path]:
        """Get list of available sound effect files."""
        sfx_dir = self.config.get_path('sfx')
        if not sfx_dir.exists():
            return []
        
        sfx_files = []
        for ext in self.SUPPORTED_FORMATS:
            sfx_files.extend(sfx_dir.glob(f'*{ext}'))
        
        return sfx_files
    
    def get_random_music(self) -> Optional[Path]:
        """Get a random music track from the library."""
        music_files = self._get_music_files()
        if not music_files:
            return None
        return random.choice(music_files)
    
    def get_notification_sound(self) -> Optional[Path]:
        """Get a Discord-style notification sound if available."""
        sfx_dir = self.config.get_path('sfx')
        
        # Look for common notification sound names
        notification_names = [
            'notification', 'notify', 'ping', 'message', 'discord'
        ]
        
        for name in notification_names:
            for ext in self.SUPPORTED_FORMATS:
                path = sfx_dir / f'{name}{ext}'
                if path.exists():
                    return path
        
        # Return any available SFX as fallback
        sfx_files = self._get_sfx_files()
        if sfx_files:
            return sfx_files[0]
        
        return None
    
    def load_audio(self, path: Union[str, Path]) -> AudioSegment:
        """
        Load an audio file.
        
        Args:
            path: Path to audio file
        
        Returns:
            Loaded AudioSegment
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        
        return AudioSegment.from_file(str(path))
    
    def prepare_background_music(
        self,
        music_path: Union[str, Path],
        duration_ms: int,
        volume: Optional[float] = None
    ) -> AudioSegment:
        """
        Prepare background music track for the video.
        
        Args:
            music_path: Path to music file
            duration_ms: Target duration in milliseconds
            volume: Volume level (0-1), uses config if None
        
        Returns:
            Prepared audio segment
        """
        volume = volume if volume is not None else self.music_volume
        
        # Load music
        music = self.load_audio(music_path)
        
        # Loop if too short
        while len(music) < duration_ms:
            music = music + music
        
        # Trim to target duration
        music = music[:duration_ms]
        
        # Apply fade in/out (convert to milliseconds)
        fade_in_ms = int(self.fade_in * 1000)
        fade_out_ms = int(self.fade_out * 1000)
        
        music = music.fade_in(fade_in_ms).fade_out(fade_out_ms)
        
        # Adjust volume
        volume_db = self._db_from_ratio(volume)
        music = music + volume_db
        
        return music
    
    def create_sfx_track(
        self,
        sfx_path: Union[str, Path],
        timestamps_ms: List[int],
        total_duration_ms: int,
        volume: Optional[float] = None
    ) -> AudioSegment:
        """
        Create a sound effects track with sounds at specified timestamps.
        
        Args:
            sfx_path: Path to sound effect file
            timestamps_ms: List of timestamps (in ms) to play the sound
            total_duration_ms: Total duration of the track
            volume: Volume level (0-1)
        
        Returns:
            Audio segment with SFX at specified positions
        """
        volume = volume if volume is not None else self.sfx_volume
        
        # Load SFX
        sfx = self.load_audio(sfx_path)
        
        # Adjust SFX volume
        volume_db = self._db_from_ratio(volume)
        sfx = sfx + volume_db
        
        # Create silent base track
        combined = AudioSegment.silent(duration=total_duration_ms)
        
        # Overlay SFX at each timestamp
        for ts in timestamps_ms:
            if ts < total_duration_ms:
                combined = combined.overlay(sfx, position=ts)
        
        return combined
    
    def mix_tracks(
        self,
        tracks: List[AudioSegment],
        normalize_output: bool = True
    ) -> AudioSegment:
        """
        Mix multiple audio tracks together.
        
        Args:
            tracks: List of audio segments to mix
            normalize_output: Whether to normalize the final mix
        
        Returns:
            Mixed audio segment
        """
        if not tracks:
            raise ValueError("No tracks to mix")
        
        # Start with the longest track
        tracks = sorted(tracks, key=len, reverse=True)
        mixed = tracks[0]
        
        # Overlay remaining tracks
        for track in tracks[1:]:
            # Pad shorter tracks with silence
            if len(track) < len(mixed):
                track = track + AudioSegment.silent(duration=len(mixed) - len(track))
            mixed = mixed.overlay(track)
        
        # Normalize if requested
        if normalize_output:
            mixed = normalize(mixed)
        
        return mixed
    
    def mix_for_video(
        self,
        duration_ms: int,
        music_path: Optional[Union[str, Path]] = None,
        sfx_timestamps_ms: Optional[List[int]] = None,
        output_path: Optional[Union[str, Path]] = None
    ) -> Tuple[AudioSegment, Optional[str]]:
        """
        Create a complete audio mix for a video.
        
        Args:
            duration_ms: Video duration in milliseconds
            music_path: Path to background music (uses random if None)
            sfx_timestamps_ms: Timestamps for notification sounds
            output_path: Optional path to save the mixed audio
        
        Returns:
            Tuple of (audio segment, output path if saved)
        """
        tracks = []
        
        # Add background music
        if music_path is None:
            music_path = self.get_random_music()
        
        if music_path:
            music = self.prepare_background_music(music_path, duration_ms)
            tracks.append(music)
        
        # Add notification sounds if timestamps provided
        if sfx_timestamps_ms and self.config.get('audio.notification_sound', True):
            sfx_path = self.get_notification_sound()
            if sfx_path:
                sfx_track = self.create_sfx_track(
                    sfx_path,
                    sfx_timestamps_ms,
                    duration_ms
                )
                tracks.append(sfx_track)
        
        # Mix everything together
        if tracks:
            mixed = self.mix_tracks(tracks)
        else:
            # Return silence if no tracks
            mixed = AudioSegment.silent(duration=duration_ms)
        
        # Save if output path provided
        saved_path = None
        if output_path:
            output_path = Path(output_path)
            output_format = output_path.suffix.lstrip('.') or 'mp3'
            mixed.export(str(output_path), format=output_format)
            saved_path = str(output_path)
        
        return mixed, saved_path
    
    def calculate_sfx_timestamps(
        self,
        num_messages: int,
        message_duration_ms: int,
        typing_duration_ms: int,
        skip_first: bool = True
    ) -> List[int]:
        """
        Calculate timestamps for notification sounds based on message timing.
        
        Args:
            num_messages: Number of messages in the video
            message_duration_ms: Duration each message is shown
            typing_duration_ms: Duration of typing indicator
            skip_first: Whether to skip sound for first message
        
        Returns:
            List of timestamps in milliseconds
        """
        timestamps = []
        current_time = 0
        
        for i in range(num_messages):
            if i > 0:
                # Add typing duration
                current_time += typing_duration_ms
            
            # Play notification when message appears
            if not (skip_first and i == 0):
                timestamps.append(current_time)
            
            # Add message display duration
            current_time += message_duration_ms
        
        return timestamps


# Example usage
if __name__ == "__main__":
    mixer = AudioMixer()
    
    # Check available music
    music_files = mixer._get_music_files()
    print(f"Found {len(music_files)} music files")
    
    sfx_files = mixer._get_sfx_files()
    print(f"Found {len(sfx_files)} SFX files")
    
    # Calculate example timestamps
    timestamps = mixer.calculate_sfx_timestamps(
        num_messages=10,
        message_duration_ms=1500,
        typing_duration_ms=800
    )
    print(f"SFX timestamps: {timestamps}")

