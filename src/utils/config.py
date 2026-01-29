"""
Configuration Loader for Trading System

Loads configuration from YAML file with environment variable substitution.
"""

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


def _substitute_env_vars(value: Any) -> Any:
    """
    Recursively substitute environment variables in config values.
    
    Supports ${VAR_NAME} syntax. Returns None if env var is not set.
    """
    if isinstance(value, str):
        # Pattern to match ${VAR_NAME}
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, value)
        
        for var_name in matches:
            env_value = os.environ.get(var_name)
            if env_value is not None:
                value = value.replace(f'${{{var_name}}}', env_value)
            else:
                # Return the original placeholder if env var not set
                pass
        return value
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    else:
        return value


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to config file. If None, uses default location.
        
    Returns:
        Configuration dictionary with environment variables substituted.
    """
    if config_path is None:
        # Default to config/config.yaml relative to project root
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config" / "config.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Substitute environment variables
    config = _substitute_env_vars(config)
    
    return config


def get_db_path(config: Optional[Dict] = None) -> str:
    """
    Get the database path from config, resolving relative paths.
    """
    if config is None:
        config = load_config()
    
    db_path = config.get('paths', {}).get('database', 'data/agent.db')
    
    # If relative path, resolve from project root
    if not os.path.isabs(db_path):
        project_root = Path(__file__).parent.parent.parent
        db_path = project_root / db_path
    
    return str(db_path)


def get_inbox_path(config: Optional[Dict] = None) -> str:
    """
    Get the inbox path from config, resolving relative paths.
    """
    if config is None:
        config = load_config()
    
    inbox_path = config.get('paths', {}).get('inbox', 'inbox')
    
    if not os.path.isabs(inbox_path):
        project_root = Path(__file__).parent.parent.parent
        inbox_path = project_root / inbox_path
    
    return str(inbox_path)


# Singleton config instance
_config_cache: Optional[Dict] = None


def get_config() -> Dict[str, Any]:
    """
    Get cached config instance.
    """
    global _config_cache
    if _config_cache is None:
        _config_cache = load_config()
    return _config_cache


def reload_config() -> Dict[str, Any]:
    """
    Force reload of configuration.
    """
    global _config_cache
    _config_cache = load_config()
    return _config_cache
