"""Security utilities for input validation and sanitization."""

import argparse
import datetime
import re
from urllib.parse import urlparse


def sanitize_path_input(value: str, max_length: int = 100) -> str:
    """
    Sanitize user input to prevent path traversal attacks.
    """
    if not value:
        raise ValueError("Input cannot be empty")
        
    if re.search(r'[<>:"/\\|?*]', value) or '..' in value:
        raise ValueError(f"Input '{value}' contains invalid characters")
    
    # Windows reserved names
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    # Remove null bytes and control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '', value)
    
    # Remove leading dots that could be path traversal
    sanitized = re.sub(r'^\.+', '', sanitized)
    
    # Collapse multiple spaces into one
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Trim whitespace
    sanitized = sanitized.strip()
    
    # Check for reserved names
    base_name = sanitized.upper().split('.')[0] if '.' in sanitized else sanitized.upper()
    if base_name in reserved_names:
        raise ValueError(f"'{value}' is a reserved name and cannot be used")
    
    # Check length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    if not sanitized:
        raise ValueError(f"Input '{value}' contains only invalid characters")
    
    return sanitized

def validate_git_url(url: str) -> str:
    """
    Validate and sanitize a Git repository URL.
    """
    if not url:
        raise ValueError("Git URL cannot be empty")
    
    url = url.strip()
    
    # Reject URLs starting with dash (flag injection)
    if url.startswith('-'):
        raise ValueError("URL cannot start with '-' (potential flag injection)")
    
    # Reject file:// protocol (local file access)
    if url.lower().startswith('file://'):
        raise ValueError("file:// URLs are not allowed")
    
    # Validate HTTPS URLs
    if url.startswith('https://') or url.startswith('http://'):
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                raise ValueError("Invalid URL: missing host")
            return url
        except Exception as e:
            raise ValueError(f"Invalid URL format: {e}")
    
    # Validate SSH URLs (git@host:path)
    if url.startswith('git@'):
        if ':' not in url or '/' not in url:
            raise ValueError("Invalid SSH URL format. Expected: git@host:path/repo.git")
        return url
    
    # Validate git:// protocol
    if url.startswith('git://'):
        return url
    
    # If it looks like a simple path/repo, assume GitHub HTTPS
    if re.match(r'^[\w-]+/[\w.-]+$', url):
        return f"https://github.com/{url}"
    
    raise ValueError(
        f"Unrecognized URL format: {url}\n"
        "Supported formats:\n"
        "  - https://github.com/user/repo.git\n"
        "  - git@github.com:user/repo.git\n"
        "  - git://github.com/user/repo.git"
    )

def validate_path_component(value: str, max_length: int = 255) -> str:
    """Validate a value that must remain one filesystem path component."""
    original = value.strip()
    sanitized = sanitize_path_input(original, max_length=max_length)
    if sanitized != original or original.endswith("."):
        raise ValueError(f"Input '{value}' is not a valid path component")
    return sanitized


def validate_project_name(value: str) -> str:
    """
    Argparse validator for project names.
    """
    try:
        return sanitize_path_input(value, max_length=100)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))

def validate_client_name(value: str) -> str:
    """
    Argparse validator for client names.
    """
    try:
        return sanitize_path_input(value, max_length=50)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))

def validate_date(value: str) -> str:
    """
    Argparse validator for date strings.
    """
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: '{value}'. Use YYYY-MM-DD format."
        )
