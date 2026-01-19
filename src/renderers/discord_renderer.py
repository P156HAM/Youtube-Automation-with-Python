"""Discord-style conversation frame renderer."""

import hashlib
import math
import os
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from ..config import get_config
from ..generators.story_generator import Message, Story


class DiscordRenderer:
    """Renders Discord-style conversation frames for video generation."""
    
    # Discord dark theme colors
    COLORS = {
        'background': '#36393f',
        'message_hover': '#32353b',
        'text': '#dcddde',
        'text_muted': '#72767d',
        'divider': '#42454a',
        'channel_bg': '#2f3136',
        'input_bg': '#40444b',
    }
    
    def __init__(self):
        """Initialize the Discord renderer."""
        self.config = get_config()
        self.width = self.config.get('discord.width', 1080)
        self.height = self.config.get('discord.height', 1920)
        
        # Font settings
        self.font_path = self._get_font_path()
        self.font_username = self._load_font(18, bold=True)
        self.font_message = self._load_font(17)
        self.font_timestamp = self._load_font(12)
        self.font_reaction = self._load_font(14)
        
        # Layout settings
        self.padding = 20
        self.avatar_size = 48
        self.message_spacing = 8
        self.line_height = 24
        
        # Colors from config
        self.username_colors = self.config.get('discord.colors.username_colors', [
            "#f47fff", "#7289da", "#43b581", "#faa61a", "#f04747", "#00d4aa"
        ])
        
        # Load custom avatars from pool
        self.avatar_pool = self._load_avatar_pool()
        self.username_avatar_map = {}  # Cache: username -> avatar image
    
    def _get_font_path(self) -> Optional[str]:
        """Get path to a suitable font."""
        # Try to find a system font that looks good for Discord
        possible_fonts = [
            # macOS
            '/System/Library/Fonts/Supplemental/Arial.ttf',
            '/System/Library/Fonts/SFNS.ttf',
            '/Library/Fonts/Arial.ttf',
            # Linux
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/TTF/DejaVuSans.ttf',
            # Windows
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/segoeui.ttf',
        ]
        
        for font_path in possible_fonts:
            if os.path.exists(font_path):
                return font_path
        
        return None
    
    def _load_avatar_pool(self) -> List[Image.Image]:
        """Load avatar images from the avatars folder."""
        avatars = []
        try:
            avatars_dir = self.config.get_path('avatars')
            if avatars_dir.exists():
                # Look for avatar files (avatar_1.png, avatar_2.png, etc. or any image)
                for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
                    for avatar_path in sorted(avatars_dir.glob(ext)):
                        # Skip README files
                        if 'readme' in avatar_path.name.lower():
                            continue
                        try:
                            img = Image.open(avatar_path).convert('RGBA')
                            # Resize to avatar size
                            img = img.resize((self.avatar_size, self.avatar_size), Image.Resampling.LANCZOS)
                            # Make circular
                            img = self._make_circular(img)
                            avatars.append(img)
                        except Exception:
                            continue
        except Exception:
            pass
        return avatars
    
    def _make_circular(self, img: Image.Image) -> Image.Image:
        """Make an image circular with transparency."""
        size = img.size[0]
        mask = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse([0, 0, size-1, size-1], fill=255)
        
        result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        result.paste(img, (0, 0), mask)
        return result
    
    def _get_avatar_for_user(self, username: str, color: str) -> Image.Image:
        """Get an avatar for a username (from pool or generated)."""
        # Check cache first
        if username in self.username_avatar_map:
            return self.username_avatar_map[username]
        
        # If we have custom avatars, assign one based on username hash
        if self.avatar_pool:
            # Use hash to consistently assign same avatar to same username
            avatar_index = hash(username) % len(self.avatar_pool)
            avatar = self.avatar_pool[avatar_index].copy()
            self.username_avatar_map[username] = avatar
            return avatar
        
        # Otherwise, generate a simple avatar with initials
        avatar = self._generate_avatar(username, color, self.avatar_size)
        self.username_avatar_map[username] = avatar
        return avatar
    
    def _load_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """Load a font at the specified size."""
        try:
            if self.font_path:
                return ImageFont.truetype(self.font_path, size)
        except Exception:
            pass
        
        # Fallback to default font
        return ImageFont.load_default()
    
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def _generate_avatar(self, username: str, color: str, size: int = 48) -> Image.Image:
        """Generate a simple avatar with initials."""
        avatar = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(avatar)
        
        # Draw circular background
        bg_color = self._hex_to_rgb(color)
        draw.ellipse([0, 0, size-1, size-1], fill=bg_color)
        
        # Draw initials
        initials = ''.join(word[0].upper() for word in username.split()[:2])
        if len(initials) == 0:
            initials = username[0].upper() if username else '?'
        elif len(initials) == 1:
            initials = username[:2].upper()
        
        try:
            font = ImageFont.truetype(self.font_path, size // 2) if self.font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        
        # Center the text
        bbox = draw.textbbox((0, 0), initials, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size - text_width) // 2
        y = (size - text_height) // 2 - 2
        
        draw.text((x, y), initials, fill=(255, 255, 255), font=font)
        
        return avatar
    
    def _wrap_text(self, text: str, max_width: int) -> List[str]:
        """Wrap text to fit within max_width pixels."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox(
                (0, 0), test_line, font=self.font_message
            )
            
            if bbox[2] - bbox[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines if lines else ['']
    
    def _draw_message(
        self,
        draw: ImageDraw.Draw,
        img: Image.Image,
        message: Message,
        y_position: int,
        show_avatar: bool = True
    ) -> int:
        """
        Draw a single Discord message and return the height used.
        
        Args:
            draw: ImageDraw instance
            img: Image to draw on (for pasting avatar)
            message: Message to draw
            y_position: Y position to start drawing
            show_avatar: Whether to show avatar (False for consecutive messages from same user)
        
        Returns:
            Height of the drawn message
        """
        x_start = self.padding
        
        if show_avatar:
            # Draw avatar (uses custom pool if available, otherwise generates)
            avatar = self._get_avatar_for_user(message.username, message.avatar_color)
            img.paste(avatar, (x_start, y_position), avatar)
            
            # Draw username
            username_x = x_start + self.avatar_size + 12
            username_color = self._hex_to_rgb(message.avatar_color)
            draw.text(
                (username_x, y_position),
                message.username,
                fill=username_color,
                font=self.font_username
            )
            
            # Draw timestamp
            if message.timestamp:
                timestamp_x = username_x + draw.textbbox(
                    (0, 0), message.username, font=self.font_username
                )[2] + 8
                draw.text(
                    (timestamp_x, y_position + 3),
                    message.timestamp,
                    fill=self._hex_to_rgb(self.COLORS['text_muted']),
                    font=self.font_timestamp
                )
            
            text_y = y_position + 24
        else:
            text_y = y_position
        
        # Draw message content
        text_x = x_start + self.avatar_size + 12
        max_text_width = self.width - text_x - self.padding - 20
        
        lines = self._wrap_text(message.content, max_text_width)
        
        for line in lines:
            draw.text(
                (text_x, text_y),
                line,
                fill=self._hex_to_rgb(self.COLORS['text']),
                font=self.font_message
            )
            text_y += self.line_height
        
        # Draw reactions if any
        if message.reactions:
            reaction_y = text_y + 4
            reaction_x = text_x
            
            for reaction in message.reactions:
                # Draw reaction bubble
                reaction_text = reaction
                bbox = draw.textbbox((0, 0), reaction_text, font=self.font_reaction)
                bubble_width = bbox[2] - bbox[0] + 16
                bubble_height = 24
                
                # Draw rounded rectangle for reaction
                draw.rounded_rectangle(
                    [reaction_x, reaction_y, reaction_x + bubble_width, reaction_y + bubble_height],
                    radius=12,
                    fill=self._hex_to_rgb(self.COLORS['input_bg'])
                )
                
                draw.text(
                    (reaction_x + 8, reaction_y + 4),
                    reaction_text,
                    fill=self._hex_to_rgb(self.COLORS['text']),
                    font=self.font_reaction
                )
                
                reaction_x += bubble_width + 6
            
            text_y = reaction_y + bubble_height + 8
        
        # Calculate total height
        height = text_y - y_position + self.message_spacing
        
        return height
    
    def render_frame(
        self,
        messages: List[Message],
        visible_count: Optional[int] = None,
        typing_indicator: bool = False,
        typing_user: Optional[str] = None
    ) -> Image.Image:
        """
        Render a conversation frame showing messages up to visible_count.
        
        Args:
            messages: All messages in the conversation
            visible_count: Number of messages to show (all if None)
            typing_indicator: Whether to show typing indicator
            typing_user: Username showing typing indicator
        
        Returns:
            Rendered frame as PIL Image
        """
        if visible_count is None:
            visible_count = len(messages)
        
        visible_messages = messages[:visible_count]
        
        # Create base image
        img = Image.new('RGB', (self.width, self.height), self._hex_to_rgb(self.COLORS['background']))
        draw = ImageDraw.Draw(img)
        
        # Calculate starting Y position (we want messages to appear from top-middle area)
        # First, calculate total height needed
        total_height = 0
        message_heights = []
        last_user = None
        
        for msg in visible_messages:
            show_avatar = msg.username != last_user
            # Estimate height
            lines = self._wrap_text(msg.content, self.width - self.padding * 2 - self.avatar_size - 32)
            height = (24 if show_avatar else 0) + len(lines) * self.line_height
            if msg.reactions:
                height += 32
            height += self.message_spacing
            message_heights.append((height, show_avatar))
            total_height += height
            last_user = msg.username
        
        # Start from a position that centers the content vertically
        y_position = max(100, (self.height - total_height) // 3)
        
        # Draw messages
        last_user = None
        for i, msg in enumerate(visible_messages):
            show_avatar = msg.username != last_user
            height = self._draw_message(draw, img, msg, y_position, show_avatar)
            y_position += height
            last_user = msg.username
        
        # Draw typing indicator if requested
        if typing_indicator and typing_user:
            y_position += 10
            # Draw typing dots animation (static for single frame)
            text_x = self.padding + self.avatar_size + 12
            typing_text = f"{typing_user} is typing..."
            draw.text(
                (text_x, y_position),
                typing_text,
                fill=self._hex_to_rgb(self.COLORS['text_muted']),
                font=self.font_timestamp
            )
        
        return img
    
    def render_all_frames(
        self,
        story: Story,
        output_dir: str,
        include_typing: bool = True
    ) -> List[str]:
        """
        Render all frames for a story with progressive message reveal.
        
        Args:
            story: Story to render
            output_dir: Directory to save frames
            include_typing: Whether to include typing indicator frames
        
        Returns:
            List of paths to rendered frame images
        """
        os.makedirs(output_dir, exist_ok=True)
        frame_paths = []
        frame_num = 0
        
        for i in range(1, len(story.messages) + 1):
            # Optionally render typing indicator before each message
            if include_typing and i > 1:
                next_user = story.messages[i-1].username
                typing_frame = self.render_frame(
                    story.messages,
                    visible_count=i-1,
                    typing_indicator=True,
                    typing_user=next_user
                )
                frame_path = os.path.join(output_dir, f"frame_{frame_num:04d}_typing.png")
                typing_frame.save(frame_path, 'PNG')
                frame_paths.append(frame_path)
                frame_num += 1
            
            # Render frame with current message visible
            frame = self.render_frame(story.messages, visible_count=i)
            frame_path = os.path.join(output_dir, f"frame_{frame_num:04d}.png")
            frame.save(frame_path, 'PNG')
            frame_paths.append(frame_path)
            frame_num += 1
        
        return frame_paths
    
    def render_thumbnail(self, story: Story) -> Image.Image:
        """
        Render a thumbnail image for the video.
        
        Args:
            story: Story to create thumbnail for
        
        Returns:
            Thumbnail image
        """
        # Show first few messages for thumbnail
        return self.render_frame(story.messages, visible_count=min(4, len(story.messages)))


# Example usage
if __name__ == "__main__":
    from ..generators.story_generator import Story, Message
    
    # Create test messages
    test_messages = [
        Message(
            username="ChaoticNeutral",
            content="guys I need advice ASAP",
            avatar_color="#f47fff",
            reactions=[]
        ),
        Message(
            username="ChaoticNeutral",
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
            username="ChaoticNeutral",
            content="the one where the cat is on fire saying 'this is fine'",
            avatar_color="#f47fff",
            reactions=["💀", "😂", "🔥"]
        ),
    ]
    
    test_story = Story(
        title="Test Story",
        theme="workplace_chaos",
        messages=test_messages
    )
    
    renderer = DiscordRenderer()
    frame = renderer.render_frame(test_messages)
    frame.save("test_frame.png")
    print("Test frame saved to test_frame.png")

