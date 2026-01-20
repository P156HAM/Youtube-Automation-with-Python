"""Discord-style conversation frame renderer - Beluga Style."""

import math
import os
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji  # For emoji support

from ..config import get_config
from ..generators.story_generator import Message, Story


class DiscordRenderer:
    """Renders Discord-style conversation frames - Beluga/viral style with BIG readable text."""
    
    # Discord dark theme colors
    COLORS = {
        'background': '#36393f',
        'message_hover': '#32353b',
        'text': '#ffffff',  # Brighter white for better readability
        'text_muted': '#8e9297',
        'divider': '#42454a',
        'channel_bg': '#2f3136',
        'input_bg': '#40444b',
    }
    
    def __init__(self):
        """Initialize the Discord renderer."""
        self.config = get_config()
        self.width = self.config.get('discord.width', 1080)
        self.height = self.config.get('discord.height', 1920)
        
        # Font settings - MUCH BIGGER for Beluga style
        self.font_path = self._get_font_path()
        self.emoji_font_path = self._get_emoji_font_path()
        
        # Beluga-style: BIG readable fonts
        self.font_username = self._load_font(42, bold=True)
        self.font_message = self._load_font(38)
        self.font_timestamp = self._load_font(24)
        self.font_reaction = self._load_font(36)
        
        # Layout settings - Beluga style (bigger everything)
        self.padding = 40
        self.avatar_size = 90  # Bigger avatars
        self.message_spacing = 25
        self.line_height = 50  # Bigger line height
        self.max_visible_messages = 6  # Only show last N messages
        
        # Colors from config
        self.username_colors = self.config.get('discord.colors.username_colors', [
            "#f47fff", "#7289da", "#43b581", "#faa61a", "#f04747", "#00d4aa"
        ])
        
        # Load custom avatars from pool
        self.avatar_pool = self._load_avatar_pool()
        self.username_avatar_map = {}
    
    def _get_font_path(self) -> Optional[str]:
        """Get path to a suitable font."""
        possible_fonts = [
            # macOS - prefer bold/semibold for readability
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            '/System/Library/Fonts/Supplemental/Arial.ttf',
            '/System/Library/Fonts/SFNS.ttf',
            '/Library/Fonts/Arial.ttf',
            # Linux
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            # Windows
            'C:/Windows/Fonts/arialbd.ttf',
            'C:/Windows/Fonts/arial.ttf',
        ]
        
        for font_path in possible_fonts:
            if os.path.exists(font_path):
                return font_path
        return None
    
    def _get_emoji_font_path(self) -> Optional[str]:
        """Get path to emoji font."""
        emoji_fonts = [
            # macOS
            '/System/Library/Fonts/Apple Color Emoji.ttc',
            # Linux
            '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
            # Windows
            'C:/Windows/Fonts/seguiemj.ttf',
        ]
        for path in emoji_fonts:
            if os.path.exists(path):
                return path
        return None
    
    def _load_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """Load a font at the specified size."""
        try:
            if self.font_path:
                return ImageFont.truetype(self.font_path, size)
        except Exception:
            pass
        return ImageFont.load_default()
    
    def _load_avatar_pool(self) -> List[Image.Image]:
        """Load avatar images from the avatars folder."""
        avatars = []
        try:
            avatars_dir = self.config.get_path('avatars')
            if avatars_dir.exists():
                for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
                    for avatar_path in sorted(avatars_dir.glob(ext)):
                        if 'readme' in avatar_path.name.lower():
                            continue
                        try:
                            img = Image.open(avatar_path).convert('RGBA')
                            img = img.resize((self.avatar_size, self.avatar_size), Image.Resampling.LANCZOS)
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
    
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def _generate_avatar(self, username: str, color: str, size: int = 90) -> Image.Image:
        """Generate a simple avatar with initials - bigger for Beluga style."""
        avatar = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(avatar)
        
        bg_color = self._hex_to_rgb(color)
        draw.ellipse([0, 0, size-1, size-1], fill=bg_color)
        
        # Get initials
        initials = ''.join(word[0].upper() for word in username.split()[:2])
        if len(initials) == 0:
            initials = username[0].upper() if username else '?'
        elif len(initials) == 1:
            initials = username[:2].upper()
        
        try:
            font = ImageFont.truetype(self.font_path, size // 2) if self.font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), initials, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size - text_width) // 2
        y = (size - text_height) // 2 - 4
        
        draw.text((x, y), initials, fill=(255, 255, 255), font=font)
        return avatar
    
    def _get_avatar_for_user(self, username: str, color: str) -> Image.Image:
        """Get an avatar for a username."""
        if username in self.username_avatar_map:
            return self.username_avatar_map[username]
        
        if self.avatar_pool:
            avatar_index = hash(username) % len(self.avatar_pool)
            avatar = self.avatar_pool[avatar_index].copy()
            self.username_avatar_map[username] = avatar
            return avatar
        
        avatar = self._generate_avatar(username, color, self.avatar_size)
        self.username_avatar_map[username] = avatar
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
        show_avatar: bool = True,
        is_latest: bool = False
    ) -> int:
        """Draw a single Discord message - Beluga style with BIG text and emoji support."""
        x_start = self.padding
        
        # Highlight latest message with subtle background
        if is_latest:
            highlight_color = (64, 68, 75, 180)
            draw.rectangle(
                [0, y_position - 10, self.width, y_position + 200],
                fill=highlight_color[:3]
            )
        
        if show_avatar:
            # Draw avatar
            avatar = self._get_avatar_for_user(message.username, message.avatar_color)
            img.paste(avatar, (x_start, y_position), avatar)
            
            # Draw username - BIG and colorful
            username_x = x_start + self.avatar_size + 20
            username_color = self._hex_to_rgb(message.avatar_color)
            draw.text(
                (username_x, y_position + 5),
                message.username,
                fill=username_color,
                font=self.font_username
            )
            
            text_y = y_position + 55
        else:
            text_y = y_position
        
        # Draw message content with EMOJI SUPPORT using Pilmoji
        text_x = x_start + self.avatar_size + 20
        max_text_width = self.width - text_x - self.padding - 40
        
        lines = self._wrap_text(message.content, max_text_width)
        
        # Use Pilmoji for emoji rendering
        with Pilmoji(img) as pilmoji:
            for line in lines:
                pilmoji.text(
                    (text_x, text_y),
                    line,
                    fill=self._hex_to_rgb(self.COLORS['text']),
                    font=self.font_message
                )
                text_y += self.line_height
        
        # Draw reactions with EMOJI SUPPORT
        if message.reactions:
            reaction_y = text_y + 15
            reaction_x = text_x
            
            for reaction in message.reactions:
                # Draw reaction bubble
                bubble_width = 65
                bubble_height = 50
                
                draw.rounded_rectangle(
                    [reaction_x, reaction_y, reaction_x + bubble_width, reaction_y + bubble_height],
                    radius=25,
                    fill=self._hex_to_rgb('#4f545c')
                )
                
                # Draw emoji using Pilmoji for proper rendering
                with Pilmoji(img) as pilmoji:
                    pilmoji.text(
                        (reaction_x + 15, reaction_y + 8),
                        reaction,
                        font=self.font_reaction
                    )
                
                reaction_x += bubble_width + 12
            
            text_y = reaction_y + bubble_height + 15
        
        height = text_y - y_position + self.message_spacing
        return height
    
    def render_frame(
        self,
        messages: List[Message],
        visible_count: Optional[int] = None,
        typing_indicator: bool = False,
        typing_user: Optional[str] = None
    ) -> Image.Image:
        """Render a conversation frame - Beluga style with limited visible messages."""
        if visible_count is None:
            visible_count = len(messages)
        
        visible_messages = messages[:visible_count]
        
        # Only show last N messages for Beluga style (keeps it readable)
        if len(visible_messages) > self.max_visible_messages:
            visible_messages = visible_messages[-self.max_visible_messages:]
        
        # Create base image
        img = Image.new('RGB', (self.width, self.height), self._hex_to_rgb(self.COLORS['background']))
        draw = ImageDraw.Draw(img)
        
        # Calculate total height needed
        total_height = 0
        message_heights = []
        last_user = None
        
        for i, msg in enumerate(visible_messages):
            show_avatar = msg.username != last_user
            lines = self._wrap_text(msg.content, self.width - self.padding * 2 - self.avatar_size - 60)
            height = (55 if show_avatar else 0) + len(lines) * self.line_height
            if msg.reactions:
                height += 75
            height += self.message_spacing
            message_heights.append((height, show_avatar))
            total_height += height
            last_user = msg.username
        
        # Position messages in the CENTER of the screen (Beluga style)
        y_position = max(150, (self.height - total_height) // 2 - 100)
        
        # Draw messages
        last_user = None
        for i, msg in enumerate(visible_messages):
            show_avatar = msg.username != last_user
            is_latest = (i == len(visible_messages) - 1)  # Highlight the newest message
            height = self._draw_message(draw, img, msg, y_position, show_avatar, is_latest)
            y_position += height
            last_user = msg.username
        
        # Draw typing indicator
        if typing_indicator and typing_user:
            y_position += 20
            text_x = self.padding + self.avatar_size + 20
            
            # Draw typing animation dots
            typing_text = f"{typing_user} is typing"
            draw.text(
                (text_x, y_position),
                typing_text,
                fill=self._hex_to_rgb(self.COLORS['text_muted']),
                font=self.font_timestamp
            )
            
            # Animated dots
            dots_x = text_x + draw.textbbox((0, 0), typing_text, font=self.font_timestamp)[2] + 5
            draw.text((dots_x, y_position), "...", fill=self._hex_to_rgb('#ffffff'), font=self.font_timestamp)
        
        return img
    
    def render_all_frames(
        self,
        story: Story,
        output_dir: str,
        include_typing: bool = True
    ) -> List[str]:
        """Render all frames for a story with progressive message reveal."""
        os.makedirs(output_dir, exist_ok=True)
        frame_paths = []
        frame_num = 0
        
        for i in range(1, len(story.messages) + 1):
            # Typing indicator before each message (except first)
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
        """Render a thumbnail image for the video."""
        return self.render_frame(story.messages, visible_count=min(3, len(story.messages)))


if __name__ == "__main__":
    from ..generators.story_generator import Story, Message
    
    test_messages = [
        Message(username="ChaoticNeutral", content="guys I need advice ASAP", avatar_color="#f47fff"),
        Message(username="ChaoticNeutral", content="I accidentally sent my boss a meme", avatar_color="#f47fff", reactions=["💀", "😂"]),
    ]
    
    test_story = Story(title="Test", theme="test", messages=test_messages)
    renderer = DiscordRenderer()
    frame = renderer.render_frame(test_messages)
    frame.save("test_frame.png")
    print("Test frame saved")
