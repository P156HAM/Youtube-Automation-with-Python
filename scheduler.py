#!/usr/bin/env python3
"""
YouTube Shorts Automation Scheduler

Runs automatically in the background, generating and uploading videos
at specified intervals without any manual intervention.

Usage:
    python3 scheduler.py                    # Run with default settings (every 4 hours)
    python3 scheduler.py --interval 6       # Run every 6 hours
    python3 scheduler.py --daily 3          # Upload 3 videos per day at random times
    python3 scheduler.py --times 09:00,15:00,21:00  # Upload at specific times
"""

import argparse
import random
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import Pipeline
from src.config import get_config


class Scheduler:
    """Automated scheduler for YouTube Shorts generation and upload."""
    
    def __init__(self):
        self.pipeline = Pipeline()
        self.config = get_config()
        self.running = True
        self.videos_uploaded_today = 0
        self.last_reset_date = datetime.now().date()
        
        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        print("\n\n🛑 Shutting down scheduler...")
        self.running = False
    
    def _get_random_theme(self) -> str:
        """Get a random theme from available themes."""
        themes = self.config.get('story.themes', [
            'AITA', 'workplace_chaos', 'relationship_drama',
            'roommate_horror', 'family_dinner', 'online_dating'
        ])
        return random.choice(themes)
    
    def _log(self, message: str):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def run_once(self) -> bool:
        """Run a single video generation and upload cycle."""
        try:
            theme = self._get_random_theme()
            self._log(f"🎬 Starting video generation (theme: {theme})")
            
            job = self.pipeline.run(theme=theme, upload=True)
            
            if job.youtube_id:
                self._log(f"✅ Video uploaded: https://youtube.com/shorts/{job.youtube_id}")
                self.videos_uploaded_today += 1
                return True
            else:
                self._log("⚠️ Video created but upload failed")
                return False
                
        except Exception as e:
            self._log(f"❌ Error: {e}")
            return False
    
    def run_interval(self, hours: float = 4.0):
        """
        Run videos at regular intervals.
        
        Args:
            hours: Hours between each video
        """
        interval_seconds = hours * 3600
        
        self._log(f"🚀 Scheduler started - uploading every {hours} hours")
        self._log(f"   Press Ctrl+C to stop")
        print()
        
        while self.running:
            # Reset daily counter
            if datetime.now().date() != self.last_reset_date:
                self.videos_uploaded_today = 0
                self.last_reset_date = datetime.now().date()
            
            # Run a video
            self.run_once()
            
            if not self.running:
                break
            
            # Calculate next run time
            next_run = datetime.now() + timedelta(seconds=interval_seconds)
            self._log(f"💤 Next video at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            
            # Sleep with periodic checks for shutdown
            sleep_until = time.time() + interval_seconds
            while time.time() < sleep_until and self.running:
                time.sleep(60)  # Check every minute
        
        self._log("Scheduler stopped")
    
    def run_daily(self, videos_per_day: int = 3):
        """
        Run a specific number of videos per day at random times.
        
        Args:
            videos_per_day: Number of videos to upload each day
        """
        self._log(f"🚀 Scheduler started - {videos_per_day} videos per day at random times")
        self._log(f"   Press Ctrl+C to stop")
        print()
        
        while self.running:
            # Reset daily counter at midnight
            if datetime.now().date() != self.last_reset_date:
                self.videos_uploaded_today = 0
                self.last_reset_date = datetime.now().date()
                self._log(f"📅 New day - will upload {videos_per_day} videos today")
            
            # Check if we need to upload more today
            if self.videos_uploaded_today < videos_per_day:
                # Calculate remaining videos and time
                remaining_videos = videos_per_day - self.videos_uploaded_today
                now = datetime.now()
                end_of_day = now.replace(hour=23, minute=0, second=0)
                remaining_seconds = (end_of_day - now).total_seconds()
                
                if remaining_seconds > 0:
                    # Random delay before next video
                    max_delay = remaining_seconds / remaining_videos
                    delay = random.uniform(60, min(max_delay, 3600))  # At least 1 min, max 1 hour
                    
                    next_run = now + timedelta(seconds=delay)
                    self._log(f"⏰ Next video at: {next_run.strftime('%H:%M:%S')} ({remaining_videos} remaining today)")
                    
                    # Wait
                    sleep_until = time.time() + delay
                    while time.time() < sleep_until and self.running:
                        time.sleep(60)
                    
                    if self.running:
                        self.run_once()
            else:
                # Done for today, sleep until midnight
                now = datetime.now()
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0)
                sleep_seconds = (tomorrow - now).total_seconds()
                
                self._log(f"✅ Done for today ({self.videos_uploaded_today} videos). Sleeping until midnight...")
                
                sleep_until = time.time() + sleep_seconds
                while time.time() < sleep_until and self.running:
                    time.sleep(60)
        
        self._log("Scheduler stopped")
    
    def run_at_times(self, times: list):
        """
        Run videos at specific times each day.
        
        Args:
            times: List of times in HH:MM format (e.g., ['09:00', '15:00', '21:00'])
        """
        # Parse times
        scheduled_times = []
        for t in times:
            hour, minute = map(int, t.split(':'))
            scheduled_times.append((hour, minute))
        
        scheduled_times.sort()
        
        self._log(f"🚀 Scheduler started - uploading at: {', '.join(times)}")
        self._log(f"   Press Ctrl+C to stop")
        print()
        
        while self.running:
            now = datetime.now()
            
            # Find next scheduled time
            next_time = None
            for hour, minute in scheduled_times:
                scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if scheduled > now:
                    next_time = scheduled
                    break
            
            # If no time today, schedule for tomorrow
            if next_time is None:
                hour, minute = scheduled_times[0]
                next_time = (now + timedelta(days=1)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
            
            # Wait until next scheduled time
            sleep_seconds = (next_time - now).total_seconds()
            self._log(f"⏰ Next video at: {next_time.strftime('%Y-%m-%d %H:%M')}")
            
            sleep_until = time.time() + sleep_seconds
            while time.time() < sleep_until and self.running:
                time.sleep(60)
            
            if self.running:
                self.run_once()
        
        self._log("Scheduler stopped")


def main():
    parser = argparse.ArgumentParser(
        description='YouTube Shorts Automation Scheduler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scheduler.py                      # Every 4 hours (default)
    python3 scheduler.py --interval 6         # Every 6 hours
    python3 scheduler.py --daily 3            # 3 videos per day at random times
    python3 scheduler.py --times 09:00,15:00,21:00  # At specific times
    python3 scheduler.py --once               # Run once and exit
        """
    )
    
    parser.add_argument('--interval', '-i', type=float, default=4.0,
                        help='Hours between uploads (default: 4)')
    parser.add_argument('--daily', '-d', type=int,
                        help='Videos per day at random times')
    parser.add_argument('--times', '-t',
                        help='Specific times to upload (comma-separated, e.g., 09:00,15:00,21:00)')
    parser.add_argument('--once', action='store_true',
                        help='Run once and exit')
    
    args = parser.parse_args()
    
    scheduler = Scheduler()
    
    if args.once:
        scheduler.run_once()
    elif args.daily:
        scheduler.run_daily(videos_per_day=args.daily)
    elif args.times:
        times = [t.strip() for t in args.times.split(',')]
        scheduler.run_at_times(times)
    else:
        scheduler.run_interval(hours=args.interval)


if __name__ == "__main__":
    main()

