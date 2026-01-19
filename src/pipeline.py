"""Main pipeline orchestrator for YouTube Shorts automation."""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audio.mixer import AudioMixer
from .config import get_config
from .generators.story_generator import Story, StoryGenerator
from .renderers.discord_renderer import DiscordRenderer
from .uploaders.youtube_uploader import YouTubeUploader
from .video.composer import VideoComposer


class JobStatus(Enum):
    """Status of a pipeline job."""
    PENDING = "pending"
    GENERATING_STORY = "generating_story"
    RENDERING_FRAMES = "rendering_frames"
    COMPOSING_VIDEO = "composing_video"
    MIXING_AUDIO = "mixing_audio"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineJob:
    """Represents a single video generation job."""
    id: str
    theme: Optional[str] = None
    status: JobStatus = JobStatus.PENDING
    story: Optional[Story] = None
    video_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    youtube_id: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            'id': self.id,
            'theme': self.theme,
            'status': self.status.value,
            'story': self.story.to_dict() if self.story else None,
            'video_path': self.video_path,
            'thumbnail_path': self.thumbnail_path,
            'youtube_id': self.youtube_id,
            'error': self.error,
            'created_at': self.created_at,
            'completed_at': self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PipelineJob':
        """Create job from dictionary."""
        job = cls(
            id=data['id'],
            theme=data.get('theme'),
            status=JobStatus(data['status']),
            video_path=data.get('video_path'),
            thumbnail_path=data.get('thumbnail_path'),
            youtube_id=data.get('youtube_id'),
            error=data.get('error'),
            created_at=data.get('created_at', datetime.now().isoformat()),
            completed_at=data.get('completed_at')
        )
        if data.get('story'):
            job.story = Story.from_dict(data['story'])
        return job
    
    def save(self, jobs_dir: Path) -> None:
        """Save job to file."""
        jobs_dir.mkdir(parents=True, exist_ok=True)
        filepath = jobs_dir / f"{self.id}.json"
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: Path) -> 'PipelineJob':
        """Load job from file."""
        with open(filepath, 'r') as f:
            return cls.from_dict(json.load(f))


class Pipeline:
    """
    Main orchestrator for the YouTube Shorts automation pipeline.
    
    Coordinates all stages:
    1. Story generation (GPT-4)
    2. Frame rendering (Discord UI)
    3. Video composition (MoviePy)
    4. Audio mixing (pydub)
    5. YouTube upload
    """
    
    def __init__(self):
        """Initialize the pipeline with all components."""
        self.config = get_config()
        
        # Initialize components
        self.story_generator = StoryGenerator()
        self.renderer = DiscordRenderer()
        self.composer = VideoComposer()
        self.audio_mixer = AudioMixer()
        self.uploader = YouTubeUploader()
        
        # Directories
        self.jobs_dir = self.config.get_path('jobs')
        self.renders_dir = self.config.get_path('renders_final')
        self.tmp_dir = self.config.get_path('renders_tmp')
    
    def create_job(self, theme: Optional[str] = None) -> PipelineJob:
        """
        Create a new pipeline job.
        
        Args:
            theme: Story theme (random if None)
        
        Returns:
            New PipelineJob instance
        """
        job_id = str(uuid.uuid4())[:8]
        job = PipelineJob(id=job_id, theme=theme)
        job.save(self.jobs_dir)
        return job
    
    def _update_job(self, job: PipelineJob, status: JobStatus, **kwargs) -> None:
        """Update job status and save."""
        job.status = status
        for key, value in kwargs.items():
            setattr(job, key, value)
        job.save(self.jobs_dir)
    
    def run_job(
        self,
        job: PipelineJob,
        upload: bool = True,
        music_path: Optional[str] = None
    ) -> PipelineJob:
        """
        Execute a complete pipeline job.
        
        Args:
            job: Job to execute
            upload: Whether to upload to YouTube
            music_path: Optional specific music track to use
        
        Returns:
            Updated job with results
        """
        try:
            print(f"\n{'='*50}")
            print(f"Starting job: {job.id}")
            print(f"{'='*50}")
            
            # Step 1: Generate story
            print("\n📝 Step 1: Generating story...")
            self._update_job(job, JobStatus.GENERATING_STORY)
            
            story = self.story_generator.generate(theme=job.theme)
            job.story = story
            print(f"   ✓ Generated: '{story.title}'")
            print(f"   ✓ Theme: {story.theme}")
            print(f"   ✓ Messages: {len(story.messages)}")
            
            # Step 2: Render frames
            print("\n🎨 Step 2: Rendering Discord frames...")
            self._update_job(job, JobStatus.RENDERING_FRAMES)
            
            frames_dir = self.tmp_dir / f"frames_{job.id}"
            frame_paths = self.renderer.render_all_frames(
                story,
                str(frames_dir),
                include_typing=self.config.get('video.typing_animation', True)
            )
            print(f"   ✓ Rendered {len(frame_paths)} frames")
            
            # Step 3: Prepare audio
            print("\n🎵 Step 3: Mixing audio...")
            self._update_job(job, JobStatus.MIXING_AUDIO)
            
            # Calculate durations
            message_duration = self.config.get('discord.message_delay', 1.5)
            typing_duration = self.config.get('video.typing_duration', 0.8)
            total_duration_ms = int(
                len(story.messages) * (message_duration + typing_duration) * 1000
            )
            
            # Get or select music
            if music_path is None:
                music_path = self.audio_mixer.get_random_music()
            
            audio_path = None
            if music_path:
                audio_output = self.tmp_dir / f"audio_{job.id}.mp3"
                # Calculate SFX timestamps
                sfx_timestamps = self.audio_mixer.calculate_sfx_timestamps(
                    num_messages=len(story.messages),
                    message_duration_ms=int(message_duration * 1000),
                    typing_duration_ms=int(typing_duration * 1000)
                )
                
                _, audio_path = self.audio_mixer.mix_for_video(
                    duration_ms=total_duration_ms,
                    music_path=music_path,
                    sfx_timestamps_ms=sfx_timestamps if self.config.get('audio.notification_sound', True) else None,
                    output_path=audio_output
                )
                print(f"   ✓ Audio prepared: {audio_path}")
            else:
                print("   ⚠ No background music found, proceeding without audio")
            
            # Step 4: Compose video
            print("\n🎬 Step 4: Composing video...")
            self._update_job(job, JobStatus.COMPOSING_VIDEO)
            
            self.renders_dir.mkdir(parents=True, exist_ok=True)
            video_filename = f"{job.id}_{story.theme}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            video_path = self.renders_dir / video_filename
            
            self.composer.compose_from_frames(
                frame_paths,
                str(video_path),
                audio_path=audio_path,
                message_duration=message_duration,
                typing_duration=typing_duration
            )
            
            job.video_path = str(video_path)
            print(f"   ✓ Video saved: {video_path}")
            
            # Create thumbnail
            thumbnail_path = self.renders_dir / f"{job.id}_thumbnail.png"
            self.composer.create_thumbnail(story, str(thumbnail_path))
            job.thumbnail_path = str(thumbnail_path)
            print(f"   ✓ Thumbnail saved: {thumbnail_path}")
            
            # Step 5: Upload to YouTube
            if upload:
                print("\n📤 Step 5: Uploading to YouTube...")
                self._update_job(job, JobStatus.UPLOADING)
                
                video_id = self.uploader.upload(
                    video_path=str(video_path),
                    story=story,
                    thumbnail_path=str(thumbnail_path)
                )
                
                if video_id:
                    job.youtube_id = video_id
                    print(f"   ✓ Uploaded! https://youtube.com/shorts/{video_id}")
                else:
                    print("   ⚠ Upload failed or was skipped")
            else:
                print("\n📤 Step 5: Skipping YouTube upload (upload=False)")
            
            # Mark complete
            job.completed_at = datetime.now().isoformat()
            self._update_job(job, JobStatus.COMPLETED)
            
            print(f"\n{'='*50}")
            print(f"✅ Job {job.id} completed successfully!")
            print(f"{'='*50}")
            
            # Cleanup temp files
            self._cleanup_temp(job.id)
            
            return job
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ Job failed: {error_msg}")
            self._update_job(job, JobStatus.FAILED, error=error_msg)
            raise
    
    def _cleanup_temp(self, job_id: str) -> None:
        """Clean up temporary files for a job."""
        import shutil
        
        frames_dir = self.tmp_dir / f"frames_{job_id}"
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        
        audio_file = self.tmp_dir / f"audio_{job_id}.mp3"
        if audio_file.exists():
            audio_file.unlink()
    
    def run(
        self,
        theme: Optional[str] = None,
        upload: bool = True,
        music_path: Optional[str] = None
    ) -> PipelineJob:
        """
        Run a complete pipeline cycle from start to finish.
        
        Args:
            theme: Story theme (random if None)
            upload: Whether to upload to YouTube
            music_path: Optional specific music track
        
        Returns:
            Completed job
        """
        job = self.create_job(theme=theme)
        return self.run_job(job, upload=upload, music_path=music_path)
    
    def run_batch(
        self,
        count: int,
        themes: Optional[List[str]] = None,
        upload: bool = True
    ) -> List[PipelineJob]:
        """
        Run multiple pipeline jobs.
        
        Args:
            count: Number of videos to create
            themes: List of themes to use (cycles if fewer than count)
            upload: Whether to upload to YouTube
        
        Returns:
            List of completed jobs
        """
        jobs = []
        
        if themes is None:
            themes = self.config.get('story.themes', [])
        
        for i in range(count):
            theme = themes[i % len(themes)] if themes else None
            print(f"\n{'#'*60}")
            print(f"# Batch job {i+1}/{count}")
            print(f"{'#'*60}")
            
            try:
                job = self.run(theme=theme, upload=upload)
                jobs.append(job)
            except Exception as e:
                print(f"Job {i+1} failed: {e}")
                # Continue with remaining jobs
        
        return jobs
    
    def list_jobs(self, status: Optional[JobStatus] = None) -> List[PipelineJob]:
        """
        List all jobs, optionally filtered by status.
        
        Args:
            status: Filter by status (all if None)
        
        Returns:
            List of jobs
        """
        jobs = []
        
        if not self.jobs_dir.exists():
            return jobs
        
        for filepath in self.jobs_dir.glob('*.json'):
            try:
                job = PipelineJob.load(filepath)
                if status is None or job.status == status:
                    jobs.append(job)
            except Exception:
                continue
        
        # Sort by creation time
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        
        return jobs
    
    def retry_failed_jobs(self) -> List[PipelineJob]:
        """
        Retry all failed jobs.
        
        Returns:
            List of retried jobs
        """
        failed_jobs = self.list_jobs(status=JobStatus.FAILED)
        results = []
        
        for job in failed_jobs:
            print(f"\nRetrying job: {job.id}")
            job.status = JobStatus.PENDING
            job.error = None
            
            try:
                result = self.run_job(job)
                results.append(result)
            except Exception as e:
                print(f"Retry failed: {e}")
        
        return results


# CLI interface
def main():
    """Main entry point for CLI usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='YouTube Shorts Automation Pipeline')
    parser.add_argument('command', choices=['run', 'batch', 'list', 'retry', 'auth'],
                        help='Command to execute')
    parser.add_argument('--theme', '-t', help='Story theme')
    parser.add_argument('--count', '-c', type=int, default=1, help='Number of videos for batch')
    parser.add_argument('--no-upload', action='store_true', help='Skip YouTube upload')
    parser.add_argument('--status', '-s', help='Filter jobs by status')
    
    args = parser.parse_args()
    
    pipeline = Pipeline()
    
    if args.command == 'auth':
        # Just authenticate with YouTube
        pipeline.uploader.authenticate()
        info = pipeline.uploader.get_channel_info()
        if info:
            print(f"\nChannel: {info['title']}")
            print(f"Subscribers: {info['subscribers']}")
    
    elif args.command == 'run':
        # Run single job
        job = pipeline.run(
            theme=args.theme,
            upload=not args.no_upload
        )
        print(f"\nJob completed: {job.id}")
        if job.youtube_id:
            print(f"Watch at: https://youtube.com/shorts/{job.youtube_id}")
    
    elif args.command == 'batch':
        # Run batch jobs
        jobs = pipeline.run_batch(
            count=args.count,
            upload=not args.no_upload
        )
        print(f"\nCompleted {len(jobs)} jobs")
    
    elif args.command == 'list':
        # List jobs
        status = JobStatus(args.status) if args.status else None
        jobs = pipeline.list_jobs(status=status)
        
        print(f"\nFound {len(jobs)} jobs:")
        for job in jobs[:20]:  # Show last 20
            status_icon = '✓' if job.status == JobStatus.COMPLETED else '✗' if job.status == JobStatus.FAILED else '○'
            print(f"  {status_icon} {job.id}: {job.status.value}")
            if job.story:
                print(f"     Title: {job.story.title[:50]}...")
    
    elif args.command == 'retry':
        # Retry failed jobs
        jobs = pipeline.retry_failed_jobs()
        print(f"\nRetried {len(jobs)} jobs")


if __name__ == "__main__":
    main()

