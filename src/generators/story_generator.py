"""AI-powered story generator for Discord-style conversations."""

import json
import random
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from openai import OpenAI

from ..config import get_config

if TYPE_CHECKING:
    from .reddit_trends import RedditTopic


@dataclass
class Message:
    """Represents a single Discord message."""
    username: str
    content: str
    avatar_color: str
    timestamp: Optional[str] = None
    reactions: List[str] = field(default_factory=list)


@dataclass
class Story:
    """Represents a complete conversation story."""
    title: str
    theme: str
    messages: List[Message]
    description: str = ""
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert story to dictionary."""
        return {
            'title': self.title,
            'theme': self.theme,
            'description': self.description,
            'tags': self.tags,
            'messages': [
                {
                    'username': msg.username,
                    'content': msg.content,
                    'avatar_color': msg.avatar_color,
                    'timestamp': msg.timestamp,
                    'reactions': msg.reactions
                }
                for msg in self.messages
            ]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Story':
        """Create story from dictionary."""
        messages = [
            Message(
                username=msg['username'],
                content=msg['content'],
                avatar_color=msg['avatar_color'],
                timestamp=msg.get('timestamp'),
                reactions=msg.get('reactions', [])
            )
            for msg in data['messages']
        ]
        return cls(
            title=data['title'],
            theme=data['theme'],
            messages=messages,
            description=data.get('description', ''),
            tags=data.get('tags', [])
        )
    
    def save(self, filepath: str) -> None:
        """Save story to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'Story':
        """Load story from JSON file."""
        with open(filepath, 'r') as f:
            return cls.from_dict(json.load(f))


class StoryGenerator:
    """Generates funny Reddit-style Discord conversation stories using GPT-4."""
    
    THEME_PROMPTS = {
        'AITA': "AITA drama - Someone did something UNHINGED and asks if they're wrong. Plot twist: they're either completely justified or absolutely insane",
        'relationship_drama': "Relationship chaos - Partner did something wild. Betrayal, plot twists, and dramatic reveals",
        'workplace_chaos': "Work drama - Boss/coworker is UNHINGED. Absurd requests, toxic behavior, satisfying clap-backs",
        'roommate_horror': "Roommate nightmares - They did WHAT?! Escalating insanity, boundary violations, petty revenge",
        'family_dinner': "Family roast session - Holiday dinner goes OFF THE RAILS. Secrets exposed, drama unleashed",
        'online_dating': "Dating app HORROR - Match reveals red flags. Creepy, cringe, or chaotic energy",
    }
    
    def __init__(self):
        """Initialize the story generator."""
        self.config = get_config()
        self.client = OpenAI(api_key=self.config.openai_api_key)
        self.username_colors = self.config.get('discord.colors.username_colors', [
            "#f47fff", "#7289da", "#43b581", "#faa61a", "#f04747", "#00d4aa"
        ])
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for story generation."""
        return """You are a Gen-Z comedy writer creating UNHINGED viral Discord conversations like Beluga or Reddit drama channels. Your style is CHAOTIC, DRAMATIC, and MEME-HEAVY.

VIBE CHECK - Your stories MUST be:
1. UNHINGED - Go wild. Absurd escalations, chaotic energy, unexpected turns
2. MEME BRAIN - Use internet slang naturally: "bruh", "nah", "fr fr", "ong", "lowkey", "no cap"
3. DRAMATIC AF - Big reactions to everything. Nothing is chill. Everything is INSANE
4. EMOJI CHAOS - Characters react with 💀😂😭🗿 when shocked/dying of laughter
5. SHORT & PUNCHY - Messages are quick hits, not essays. Max 1-2 sentences

MANDATORY LANGUAGE TO USE NATURALLY:
- "bruh" / "BRO" when shocked
- "💀" or "I'm dead" when something's too funny
- "WHAT" / "WTF" / "???" for disbelief
- "nah" / "NAH" when rejecting something crazy
- "lmao" / "😂" for laughing
- "OMG" for dramatic moments
- "sus" when something's sketchy

TONE: Sassy, chaotic, unfiltered. Characters can roast each other. Be edgy (but not offensive). Think Twitter/Discord drama energy.

Output ONLY valid JSON, nothing else."""

    def _get_generation_prompt(self, theme: str, num_messages: int) -> str:
        """Get the user prompt for generating a specific story."""
        theme_description = self.THEME_PROMPTS.get(theme, theme)
        
        return f"""Generate an UNHINGED Discord conversation story:

THEME: {theme_description}
MESSAGES: {num_messages}

JSON structure:
{{
    "title": "Clickbait title with drama/shock factor",
    "theme": "{theme}",
    "description": "Brief YouTube description (2-3 sentences)",
    "tags": ["discord", "drama", "funny", "viral", "shorts"],
    "messages": [
        {{
            "username": "ChaoticUsername",
            "content": "bruh WHAT 💀",
            "reactions": ["💀", "😂"]
        }}
    ]
}}

REQUIREMENTS:
- 2-4 characters with unhinged usernames (ex: ChaosGremlin, DefinitelyNotSus, BruhMoment2024)
- Messages are SHORT and PUNCHY (under 150 chars)
- USE THESE NATURALLY: bruh, 💀, nah, WHAT, lmao, OMG, WTF, sus, I'm dead
- Reactions on dramatic moments: 💀 😂 😭 🗿 💀
- ESCALATE the chaos - each message raises stakes
- End with a punchline that HITS

EXAMPLE VIBE:
User1: "so my roommate ate my leftover pizza"
User2: "that's annoying but not that bad?"
User1: "it was in a locked safe"
User2: "WHAT"
User1: "he learned safecracking for this"
User3: "bruh 💀"
User2: "I'm actually dead rn"

Return ONLY JSON. GO CRAZY."""

    def generate(
        self,
        theme: Optional[str] = None,
        num_messages: Optional[int] = None,
        trending_topic: Optional['RedditTopic'] = None
    ) -> Story:
        """
        Generate a new story.
        
        Args:
            theme: Story theme (random if not specified)
            num_messages: Number of messages (random within config limits if not specified)
            trending_topic: Optional Reddit topic to base the story on
        
        Returns:
            Generated Story object
        """
        # If we have a trending topic, use its theme
        if trending_topic:
            from .reddit_trends import RedditTrendsFetcher
            fetcher = RedditTrendsFetcher()
            theme = fetcher.get_theme_for_topic(trending_topic)
        
        # Select random theme if not specified
        if theme is None:
            themes = self.config.get('story.themes', list(self.THEME_PROMPTS.keys()))
            theme = random.choice(themes)
        
        # Determine number of messages
        if num_messages is None:
            min_msgs = self.config.get('story.min_messages', 8)
            max_msgs = self.config.get('story.max_messages', 15)
            num_messages = random.randint(min_msgs, max_msgs)
        
        # Generate story using OpenAI
        model = self.config.openai_model
        
        # Build the user prompt
        user_prompt = self._get_generation_prompt(theme, num_messages)
        
        # Add trending topic context if provided
        if trending_topic:
            from .reddit_trends import RedditTrendsFetcher
            fetcher = RedditTrendsFetcher()
            topic_prompt = fetcher.topic_to_story_prompt(trending_topic)
            user_prompt = f"{topic_prompt}\n\n{user_prompt}"
        
        # Models that support JSON response format
        json_supported_models = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4-turbo-preview', 
                                  'gpt-3.5-turbo-1106', 'gpt-3.5-turbo-0125']
        
        request_params = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": self.config.get('openai.max_tokens', 2000),
            "temperature": self.config.get('openai.temperature', 0.8),
        }
        
        # Only add response_format for supported models
        if any(supported in model for supported in json_supported_models):
            request_params["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**request_params)
        
        # Parse response
        content = response.choices[0].message.content
        story_data = json.loads(content)
        
        # Assign colors to usernames
        username_to_color = {}
        color_index = 0
        
        for msg_data in story_data['messages']:
            username = msg_data['username']
            if username not in username_to_color:
                username_to_color[username] = self.username_colors[
                    color_index % len(self.username_colors)
                ]
                color_index += 1
            msg_data['avatar_color'] = username_to_color[username]
        
        return Story.from_dict(story_data)
    
    def generate_batch(
        self,
        count: int,
        themes: Optional[List[str]] = None
    ) -> List[Story]:
        """
        Generate multiple stories.
        
        Args:
            count: Number of stories to generate
            themes: List of themes to use (cycles through if fewer than count)
        
        Returns:
            List of generated Story objects
        """
        stories = []
        
        if themes is None:
            themes = self.config.get('story.themes', list(self.THEME_PROMPTS.keys()))
        
        for i in range(count):
            theme = themes[i % len(themes)]
            story = self.generate(theme=theme)
            stories.append(story)
            print(f"Generated story {i+1}/{count}: {story.title}")
        
        return stories


# Example usage and testing
if __name__ == "__main__":
    generator = StoryGenerator()
    story = generator.generate(theme="AITA")
    print(f"\nGenerated Story: {story.title}")
    print(f"Theme: {story.theme}")
    print(f"Messages: {len(story.messages)}")
    print("\nConversation:")
    for msg in story.messages:
        print(f"  [{msg.username}]: {msg.content}")
        if msg.reactions:
            print(f"    Reactions: {' '.join(msg.reactions)}")

