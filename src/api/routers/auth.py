"""
Authentication routes for GitHub OAuth.
"""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from src.api.auth import oauth, get_oauth_config

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Redirect to GitHub for authentication."""
    redirect_uri = request.url_for('auth_callback')
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request):
    """Handle GitHub OAuth callback."""
    try:
        token = await oauth.github.authorize_access_token(request)
        resp = await oauth.github.get('user', token=token)
        user_data = resp.json()

        config = get_oauth_config()
        if user_data['login'] not in config['allowed_users']:
            return RedirectResponse(url="/?error=unauthorized")

        request.session['user'] = {
            'username': user_data['login'],
            'avatar_url': user_data.get('avatar_url'),
        }
        return RedirectResponse(url="/")
    except Exception as e:
        return RedirectResponse(url=f"/?error={str(e)}")


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to home."""
    request.session.clear()
    return RedirectResponse(url="/")
