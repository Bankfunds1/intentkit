"""Twitter OAuth2 callback handler."""

from datetime import datetime, timezone

import tweepy
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse

from app.config.config import config
from app.services.twitter.oauth2 import oauth2_user_handler
from models.agent import Agent, AgentData
from models.db import get_db

router = APIRouter(prefix="/callback/auth", tags=["Callback"])


@router.get("/twitter")
async def twitter_oauth_callback(
    state: str,
    code: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Handle Twitter OAuth2 callback.

    This endpoint is called by Twitter after the user authorizes the application.
    It exchanges the authorization code for access and refresh tokens, then stores
    them in the database.

    Args:
        state: Agent ID from authorization request
        code: Authorization code from Twitter
        background_tasks: FastAPI background tasks
        db: Database session from FastAPI dependency injection

    Returns:
        JSONResponse with success message

    Raises:
        HTTPException: If state/code is missing or token exchange fails
    """
    if not state or not code:
        raise HTTPException(status_code=400, detail="Missing state or code parameter")

    try:
        agent_id = state
        agent = await db.get(Agent, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        agent_data = await db.get(AgentData, agent_id)

        if not agent_data:
            agent_data = AgentData(id=agent_id)
            await db.add(agent_data)

        # Exchange code for tokens
        authorization_response = (
            f"{config.twitter_oauth2_redirect_uri}?state={state}&code={code}"
        )
        token = oauth2_user_handler.get_token(authorization_response)

        # Store tokens in database
        agent_data.twitter_access_token = token["access_token"]
        agent_data.twitter_refresh_token = token["refresh_token"]
        agent_data.twitter_access_token_expires_at = datetime.fromtimestamp(
            token["expires_at"], tz=timezone.utc
        )

        # Get user info
        client = tweepy.Client(bearer_token=token["access_token"])
        me = client.get_me(user_auth=False)

        if me and "data" in me:
            agent_data.twitter_id = me.get("data").get("id")
            agent_data.twitter_username = me.get("data").get("username")
            agent_data.twitter_name = me.get("data").get("name")

        # Commit changes
        await db.commit()
        await db.refresh(agent_data)

        return JSONResponse(
            content={"message": "Authentication successful, you can close this window"},
            status_code=200,
        )
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions to preserve their status codes
        raise http_exc
    except Exception as e:
        # For unexpected errors, use 500 status code
        raise HTTPException(status_code=500, detail=str(e))
