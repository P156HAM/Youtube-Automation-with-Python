#!/usr/bin/env python3
"""
YouTube Shorts Automation - Main Entry Point

Usage:
    python main.py                     # Run single video (no upload)
    python main.py --upload            # Run single video and upload to YouTube
    python main.py --theme AITA        # Run with specific theme
    python main.py --batch 5           # Create 5 videos
    python main.py --auth              # Setup YouTube authentication
    python main.py --list              # List all jobs
    python main.py --test              # Test render (no API calls)
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def test_render():
    """Test the rendering pipeline without API calls."""
    from src.generators.story_generator import Message, Story
    from src.renderers.discord_renderer import DiscordRenderer
    from src.video.composer import VideoComposer
    
    print("🧪 Running test render...")
    
    # Create test story
    test_messages = [
        Message(
            username="ChaoticNeutral42",
            content="guys I need advice ASAP",
            avatar_color="#f47fff",
            reactions=[]
        ),
        Message(
            username="ChaoticNeutral42", 
            content="I accidentally sent my boss a meme instead of the quarterly report",
            avatar_color="#f47fff",
            reactions=["💀", "😂"]
        ),
        Message(
            username="WorkplaceWarrior",
            content="which meme was it",
            avatar_color="#7289da",
            reactions=[]
        ),
        Message(
            username="ChaoticNeutral42",
            content="the one where the cat is on fire saying 'this is fine'",
            avatar_color="#f47fff",
            reactions=["💀", "😂", "🔥"]
        ),
        Message(
            username="CorporateClown",
            content="did you get a response yet??",
            avatar_color="#43b581",
            reactions=[]
        ),
        Message(
            username="ChaoticNeutral42",
            content="yeah... he replied with 'mood'",
            avatar_color="#f47fff",
            reactions=["🎉", "😂"]
        ),
        Message(
            username="WorkplaceWarrior",
            content="LMAO your boss is a legend",
            avatar_color="#7289da",
            reactions=[]
        ),
        Message(
            username="ChaoticNeutral42",
            content="UPDATE: I just got promoted",
            avatar_color="#f47fff",
            reactions=["🎊", "🏆", "😂", "💀"]
        ),
    ]
    
    test_story = Story(
        title="Accidentally Sent Boss a Meme Instead of Report 💀",
        theme="workplace_chaos",
        messages=test_messages,
        description="When your meme game is so strong it gets you promoted 😂"
    )
    
    # Render single frame
    renderer = DiscordRenderer()
    frame = renderer.render_frame(test_messages)
    
    # Save test frame
    output_dir = Path(__file__).parent / "renders" / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    test_frame_path = output_dir / "test_frame.png"
    frame.save(str(test_frame_path))
    print(f"✓ Test frame saved: {test_frame_path}")
    
    # Render all frames
    frames_dir = output_dir / "test_frames"
    frame_paths = renderer.render_all_frames(test_story, str(frames_dir))
    print(f"✓ Rendered {len(frame_paths)} frames to: {frames_dir}")
    
    print("\n✅ Test render complete!")
    print(f"   Check the output at: {output_dir}")
    
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='YouTube Shorts Automation Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py --test              # Test render without API calls
    python main.py                     # Generate video (no upload)
    python main.py --upload            # Generate and upload to YouTube
    python main.py --theme AITA        # Use specific theme
    python main.py --batch 5           # Create 5 videos
    python main.py --auth              # Setup YouTube authentication
    python main.py --list              # List all jobs

Available themes:
    AITA, relationship_drama, workplace_chaos, 
    roommate_horror, family_dinner, online_dating
        """
    )
    
    parser.add_argument('--test', action='store_true',
                        help='Run test render without API calls')
    parser.add_argument('--auth', action='store_true',
                        help='Setup YouTube authentication')
    parser.add_argument('--upload', action='store_true',
                        help='Upload video to YouTube after creation')
    parser.add_argument('--theme', '-t',
                        help='Story theme (AITA, workplace_chaos, etc.)')
    parser.add_argument('--batch', '-b', type=int,
                        help='Create multiple videos')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all jobs')
    parser.add_argument('--music', '-m',
                        help='Path to background music file')
    
    args = parser.parse_args()
    
    # Test mode doesn't require API keys
    if args.test:
        test_render()
        return
    
    # Import pipeline (requires API configuration)
    try:
        from src.pipeline import Pipeline
    except Exception as e:
        print(f"❌ Failed to initialize pipeline: {e}")
        print("\nMake sure you have:")
        print("  1. Installed dependencies: pip install -r requirements.txt")
        print("  2. Set OPENAI_API_KEY in your environment")
        return
    
    pipeline = Pipeline()
    
    if args.auth:
        # YouTube authentication
        print("🔐 Setting up YouTube authentication...")
        if pipeline.uploader.authenticate():
            info = pipeline.uploader.get_channel_info()
            if info:
                print(f"\n✓ Connected to channel: {info['title']}")
                print(f"  Subscribers: {info['subscribers']}")
        return
    
    if args.list:
        # List jobs
        jobs = pipeline.list_jobs()
        print(f"\n📋 Found {len(jobs)} jobs:\n")
        for job in jobs[:20]:
            status_icon = {
                'completed': '✅',
                'failed': '❌',
                'pending': '⏳'
            }.get(job.status.value, '○')
            
            print(f"  {status_icon} [{job.id}] {job.status.value}")
            if job.story:
                print(f"      Title: {job.story.title[:50]}...")
            if job.youtube_id:
                print(f"      URL: https://youtube.com/shorts/{job.youtube_id}")
        return
    
    # Run pipeline
    if args.batch:
        print(f"🚀 Starting batch run ({args.batch} videos)...\n")
        jobs = pipeline.run_batch(
            count=args.batch,
            upload=args.upload
        )
        print(f"\n✅ Batch complete! Created {len(jobs)} videos.")
    else:
        print("🚀 Starting pipeline...\n")
        job = pipeline.run(
            theme=args.theme,
            upload=args.upload,
            music_path=args.music
        )
        
        print(f"\n✅ Complete!")
        print(f"   Job ID: {job.id}")
        print(f"   Video: {job.video_path}")
        if job.youtube_id:
            print(f"   YouTube: https://youtube.com/shorts/{job.youtube_id}")


if __name__ == "__main__":
    main()

