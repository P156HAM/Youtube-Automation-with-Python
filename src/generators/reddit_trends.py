"""Fetch trending topics from Reddit for story inspiration."""

import random
import re
from dataclasses import dataclass
from typing import List, Optional

import requests

from ..config import get_config


@dataclass
class RedditTopic:
    """Represents a trending Reddit topic."""
    title: str
    subreddit: str
    score: int
    url: str
    summary: Optional[str] = None
    
    def to_prompt(self) -> str:
        """Convert topic to a story prompt."""
        return f"{self.title} (from r/{self.subreddit})"


class RedditTrendsFetcher:
    """Fetches trending topics from Reddit for story generation."""
    
    # Subreddits that work well for Discord drama stories
    DRAMA_SUBREDDITS = [
        'AmItheAsshole',
        'relationship_advice', 
        'tifu',
        'pettyrevenge',
        'MaliciousCompliance',
        'entitledparents',
        'ChoosingBeggars',
        'antiwork',
        'BestofRedditorUpdates',
        'confession',
    ]
    
    # Map subreddits to our themes
    SUBREDDIT_TO_THEME = {
        'AmItheAsshole': 'AITA',
        'relationship_advice': 'relationship_drama',
        'tifu': 'workplace_chaos',
        'pettyrevenge': 'roommate_horror',
        'MaliciousCompliance': 'workplace_chaos',
        'entitledparents': 'family_dinner',
        'ChoosingBeggars': 'online_dating',
        'antiwork': 'workplace_chaos',
        'BestofRedditorUpdates': 'relationship_drama',
        'confession': 'AITA',
    }
    
    def __init__(self):
        """Initialize the Reddit trends fetcher."""
        self.config = get_config()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def fetch_subreddit_hot(
        self, 
        subreddit: str, 
        limit: int = 10
    ) -> List[RedditTopic]:
        """
        Fetch hot posts from a subreddit.
        
        Args:
            subreddit: Subreddit name (without r/)
            limit: Number of posts to fetch
        
        Returns:
            List of RedditTopic objects
        """
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            topics = []
            for post in data['data']['children']:
                post_data = post['data']
                
                # Skip pinned/stickied posts
                if post_data.get('stickied', False):
                    continue
                
                # Clean up the title
                title = self._clean_title(post_data['title'])
                
                topic = RedditTopic(
                    title=title,
                    subreddit=subreddit,
                    score=post_data.get('score', 0),
                    url=f"https://reddit.com{post_data['permalink']}",
                    summary=post_data.get('selftext', '')[:500] if post_data.get('selftext') else None
                )
                topics.append(topic)
            
            return topics
            
        except Exception as e:
            print(f"  ⚠ Failed to fetch r/{subreddit}: {e}")
            return []
    
    def _clean_title(self, title: str) -> str:
        """Clean up a Reddit post title."""
        # Remove common prefixes
        prefixes = ['AITA', 'WIBTA', 'TIFU', 'UPDATE:', '[UPDATE]', 'Update:']
        for prefix in prefixes:
            if title.upper().startswith(prefix.upper()):
                title = title[len(prefix):].strip()
                # Remove leading punctuation
                title = re.sub(r'^[\s\-:]+', '', title)
        
        # Capitalize first letter
        if title:
            title = title[0].upper() + title[1:]
        
        return title
    
    def fetch_trending(self, limit_per_sub: int = 5) -> List[RedditTopic]:
        """
        Fetch trending topics from all drama subreddits.
        
        Args:
            limit_per_sub: Number of posts to fetch per subreddit
        
        Returns:
            List of trending topics, sorted by score
        """
        all_topics = []
        
        print("  📡 Fetching trending Reddit topics...")
        for subreddit in self.DRAMA_SUBREDDITS:
            topics = self.fetch_subreddit_hot(subreddit, limit_per_sub)
            all_topics.extend(topics)
        
        # Sort by score and return top topics
        all_topics.sort(key=lambda t: t.score, reverse=True)
        
        print(f"  ✓ Found {len(all_topics)} trending topics")
        return all_topics
    
    def get_random_trending(self) -> Optional[RedditTopic]:
        """
        Get a random trending topic.
        
        Returns:
            A random trending topic or None if fetch fails
        """
        topics = self.fetch_trending(limit_per_sub=3)
        if not topics:
            return None
        
        # Weight by score (higher score = more likely to be picked)
        total_score = sum(max(t.score, 1) for t in topics)
        pick = random.randint(1, total_score)
        
        current = 0
        for topic in topics:
            current += max(topic.score, 1)
            if current >= pick:
                return topic
        
        return random.choice(topics)
    
    def get_theme_for_topic(self, topic: RedditTopic) -> str:
        """Get the matching theme for a Reddit topic."""
        return self.SUBREDDIT_TO_THEME.get(topic.subreddit, 'AITA')
    
    def topic_to_story_prompt(self, topic: RedditTopic) -> str:
        """
        Convert a Reddit topic to a detailed story prompt.
        
        Args:
            topic: The Reddit topic
        
        Returns:
            A prompt string for story generation
        """
        prompt = f"Based on this REAL trending Reddit topic: \"{topic.title}\""
        
        if topic.summary:
            # Add a brief summary if available
            clean_summary = topic.summary[:200].replace('\n', ' ').strip()
            if clean_summary:
                prompt += f"\n\nContext: {clean_summary}..."
        
        prompt += "\n\nCreate a Discord conversation INSPIRED by this topic. Make it MORE dramatic and chaotic than the original."
        
        return prompt


# Example usage
if __name__ == "__main__":
    fetcher = RedditTrendsFetcher()
    
    print("Fetching trending topics...")
    topics = fetcher.fetch_trending(limit_per_sub=3)
    
    print(f"\nTop 10 trending topics:")
    for i, topic in enumerate(topics[:10], 1):
        print(f"{i}. [{topic.subreddit}] {topic.title[:60]}... ({topic.score} upvotes)")
    
    print("\n\nRandom topic for story:")
    random_topic = fetcher.get_random_trending()
    if random_topic:
        print(f"  Title: {random_topic.title}")
        print(f"  Theme: {fetcher.get_theme_for_topic(random_topic)}")
        print(f"  Prompt: {fetcher.topic_to_story_prompt(random_topic)[:200]}...")

