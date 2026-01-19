"""Configuration management for YouTube Shorts Automation."""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


class Config:
    """Handles loading and accessing configuration settings."""
    
    _instance: Optional['Config'] = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls) -> 'Config':
        """Singleton pattern to ensure single config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load configuration from YAML and environment variables."""
        # Load .env file
        load_dotenv()
        
        # Determine project root
        self.project_root = Path(__file__).parent.parent
        config_path = self.project_root / "config" / "settings.yaml"
        
        # Load YAML config
        if config_path.exists():
            with open(config_path, 'r') as f:
                self._config = yaml.safe_load(f)
        else:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        # Resolve environment variables in config
        self._resolve_env_vars(self._config)
        
        # Convert relative paths to absolute
        self._resolve_paths()
    
    def _resolve_env_vars(self, obj: Any) -> Any:
        """Recursively resolve environment variables in config values."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                obj[key] = self._resolve_env_vars(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                obj[i] = self._resolve_env_vars(item)
        elif isinstance(obj, str):
            # Match ${VAR_NAME} pattern
            pattern = r'\$\{([^}]+)\}'
            matches = re.findall(pattern, obj)
            for match in matches:
                env_value = os.getenv(match, '')
                obj = obj.replace(f'${{{match}}}', env_value)
        return obj
    
    def _resolve_paths(self) -> None:
        """Convert relative paths in config to absolute paths."""
        if 'paths' in self._config:
            for key, value in self._config['paths'].items():
                if isinstance(value, str) and not Path(value).is_absolute():
                    self._config['paths'][key] = str(self.project_root / value)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        
        Example: config.get('openai.api_key')
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_path(self, key: str) -> Path:
        """Get a path from configuration as a Path object."""
        path_str = self.get(f'paths.{key}')
        if path_str:
            return Path(path_str)
        raise KeyError(f"Path not found in config: {key}")
    
    @property
    def openai_api_key(self) -> str:
        """Get OpenAI API key."""
        return self.get('openai.api_key', '')
    
    @property
    def openai_model(self) -> str:
        """Get OpenAI model name."""
        return self.get('openai.model', 'gpt-4')
    
    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access."""
        return self.get(key)
    
    def reload(self) -> None:
        """Reload configuration from disk."""
        self._load_config()


# Global config instance
def get_config() -> Config:
    """Get the global configuration instance."""
    return Config()

