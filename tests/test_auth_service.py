import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from app.models.user import User, UserSession, UserRole, UserStatus
from app.core.exceptions import TokenReuseDetectedException
from app.core.security import hash_token, create_refresh_token
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_token_reuse_detection_kills_all_sessions():
    mock_db = AsyncMock()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    user = User(
        id=user_id,
        email="compromised@test.com",
        role=UserRole.CUSTOMER,
        status=UserStatus.ACTIVE,
    )

    token = create_refresh_token(user_id=user_id, session_id=session_id)
    t_hash = hash_token(token)

    # Session in DB marked as ALREADY REVOKED (attacker presenting stolen old token)
    revoked_session = UserSession(
        id=session_id,
        user_id=user_id,
        token_hash=t_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        is_revoked=True,  # REVOKED!
    )

    mock_user_res = MagicMock()
    mock_user_res.scalar_one_or_none.return_value = user

    mock_sess_res = MagicMock()
    mock_sess_res.scalar_one_or_none.return_value = revoked_session

    mock_db.execute.side_effect = [mock_user_res, mock_sess_res, None]

    with patch("app.services.auth_service.notification_service.send_security_alert", new_callable=AsyncMock) as mock_alert:
        with pytest.raises(TokenReuseDetectedException):
            await AuthService.refresh_tokens(mock_db, refresh_token=token)

        # Verify emergency alert was dispatched
        mock_alert.assert_called_once()
        # Verify db was executed to kill all sessions
        assert mock_db.execute.call_count >= 3
