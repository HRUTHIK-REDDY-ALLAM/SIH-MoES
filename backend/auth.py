"""
Varsha — Officer authentication (prototype).

HTTP Basic auth against OFFICER_USERNAME / OFFICER_PASSWORD from the
environment. Production should replace this with the state's SSO / JWT and
per-district roles.
"""

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic(auto_error=False)


def require_officer(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
    user = os.getenv("OFFICER_USERNAME", "officer")
    password = os.getenv("OFFICER_PASSWORD", "varsha2024")
    ok = credentials is not None and secrets.compare_digest(credentials.username, user) \
        and secrets.compare_digest(credentials.password, password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Officer login required",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials.username
