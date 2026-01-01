"""
Environment Variable Loader

Automatically loads environment variables from config/secrets.env at module import.
This ensures API keys (FRED, etc.) are available throughout the application.

Usage:
    # Just import this module anywhere - variables are auto-loaded
    import src.env_loader
    
    # Or import at the top of your main application file
    from src import env_loader
    
    # Access keys using standard os.getenv
    import os
    fred_key = os.getenv("FRED_API_KEY")
"""

import os
from pathlib import Path
from typing import Optional

# Try to import dotenv, but don't fail if not installed
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


def load_environment_variables(env_file: Optional[str] = None, verbose: bool = False) -> bool:
    """
    Load environment variables from .env file.
    
    Args:
        env_file: Path to .env file (default: config/secrets.env)
        verbose: Print loading status
        
    Returns:
        True if variables were loaded, False otherwise
    """
    if not HAS_DOTENV:
        if verbose:
            print("⚠️  python-dotenv not installed. Install with: pip install python-dotenv")
            print("   Environment variables must be set manually via export or system settings")
        return False
    
    # Default to config/secrets.env
    if env_file is None:
        # Find project root (directory containing src/)
        current_file = Path(__file__).resolve()
        src_dir = current_file.parent  # Go up from src/env_loader.py to src/
        project_root = src_dir.parent  # Go up from src/ to project root
        env_file = str(project_root / "config" / "secrets.env")
    
    env_path = Path(env_file)
    
    if not env_path.exists():
        if verbose:
            print(f"⚠️  Environment file not found: {env_path}")
            print(f"   Create it by copying config/secrets.env.example")
        return False
    
    try:
        load_dotenv(dotenv_path=str(env_path), override=True)
        if verbose:
            print(f"✅ Loaded environment variables from {env_path}")
        return True
    except Exception as e:
        if verbose:
            print(f"⚠️  Failed to load environment file: {e}")
        return False


# Auto-load on module import
_loaded = load_environment_variables(verbose=False)


def is_environment_loaded() -> bool:
    """Check if environment variables were successfully loaded."""
    return _loaded


def get_api_key(key_name: str, required: bool = False) -> Optional[str]:
    """
    Get API key from environment variables.
    
    Args:
        key_name: Name of the environment variable (e.g., "FRED_API_KEY")
        required: If True, raise error if key not found
        
    Returns:
        API key string or None if not found
        
    Raises:
        ValueError: If required=True and key not found
    """
    key_value = os.getenv(key_name)
    
    if required and not key_value:
        raise ValueError(
            f"Required API key '{key_name}' not found in environment variables. "
            f"Add it to config/secrets.env or set it manually."
        )
    
    return key_value
