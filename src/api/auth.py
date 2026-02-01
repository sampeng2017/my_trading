"""
GitHub OAuth authentication module.
"""
import os
from typing import Optional
from fastapi import Request
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()


def get_oauth_config():
    """Read OAuth config from environment."""
    return {
        'github_client_id': os.environ.get('GITHUB_CLIENT_ID'),
        'github_client_secret': os.environ.get('GITHUB_CLIENT_SECRET'),
        'allowed_users': [u.strip() for u in os.environ.get('GITHUB_ALLOWED_USERS', '').split(',') if u.strip()],
        'session_secret': os.environ.get('SESSION_SECRET'),
    }


def init_oauth():
    """Register GitHub OAuth client. Call once at app startup."""
    config = get_oauth_config()
    oauth.register(
        name='github',
        client_id=config['github_client_id'],
        client_secret=config['github_client_secret'],
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'read:user'},
    )


async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session, or None if not logged in."""
    return request.session.get('user')
