"""AI-powered story generator for Discord-style conversations."""

import json
import random
from dataclasses import dataclass, field
from typing import List, Optional

from openai import OpenAI

from ..config import get_config


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
        'AITA': "Am I The A**hole - Someone asks if they were wrong in a ridiculous situation",
        'relationship_drama': "Wild relationship stories with unexpected twists",
        'workplace_chaos': "Absurd workplace situations and coworker drama",
        'roommate_horror': "Nightmare roommate situations that escalate hilariously",
        'family_dinner': "Family gatherings that go completely off the rails",
        'online_dating': "Dating app conversations that take unexpected turns",
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
        return """You are a comedy writer who creates viral Discord conversation stories in the style of popular Reddit posts. Your stories should be:

1. FUNNY - Use absurd situations, unexpected twists, and comedic timing
2. RELATABLE - Based on real-life situations people recognize
3. ENGAGING - Each message should make the reader want to see the next one
4. CONCISE - Messages should be short and punchy (1-3 sentences max per message)
5. NATURAL - Sound like real Discord conversations with casual language, typos, and reactions

Characters should have distinct personalities and funny usernames. Include moments of:
- Dramatic reveals
- Unexpected plot twists
- Comedic misunderstandings
- Satisfying conclusions or cliffhangers

Output your response as valid JSON only, no other text."""

    def _get_generation_prompt(self, theme: str, num_messages: int) -> str:
        """Get the user prompt for generating a specific story."""
        theme_description = self.THEME_PROMPTS.get(theme, theme)
        
        return f"""Generate a funny Discord conversation story with the following requirements:

THEME: {theme_description}
NUMBER OF MESSAGES: {num_messages}

Create a JSON object with this exact structure:
{{
    "title": "A catchy, clickbait-style title for the story",
    "theme": "{theme}",
    "description": "A brief description for YouTube (2-3 sentences)",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
    "messages": [
        {{
            "username": "FunnyUsername123",
            "content": "The message content",
            "reactions": ["😂", "💀"]  // Optional, can be empty array
        }},
        // ... more messages
    ]
}}

Requirements:
- Use 2-4 different characters with creative Discord-style usernames
- Messages should be SHORT (under 200 characters each)
- Include appropriate emoji reactions on key messages (not every message)
- Make it ACTUALLY funny with good comedic timing
- The story should have a clear beginning, middle, and end
- End with a punchline or satisfying conclusion

Return ONLY the JSON, no other text or markdown."""

    def generate(
        self,
        theme: Optional[str] = None,
        num_messages: Optional[int] = None
    ) -> Story:
        """
        Generate a new story.
        
        Args:
            theme: Story theme (random if not specified)
            num_messages: Number of messages (random within config limits if not specified)
        
        Returns:
            Generated Story object
        """
        # Select random theme if not specified
        if theme is None:
            themes = self.config.get('story.themes', list(self.THEME_PROMPTS.keys()))
            theme = random.choice(themes)
        
        # Determine number of messages
        if num_messages is None:
            min_msgs = self.config.get('story.min_messages', 8)
            max_msgs = self.config.get('story.max_messages', 15)
            num_messages = random.randint(min_msgs, max_msgs)
        
        # Generate story using GPT-4
        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": self._get_generation_prompt(theme, num_messages)}
            ],
            max_tokens=self.config.get('openai.max_tokens', 2000),
            temperature=self.config.get('openai.temperature', 0.8),
            response_format={"type": "json_object"}
        )
        
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

