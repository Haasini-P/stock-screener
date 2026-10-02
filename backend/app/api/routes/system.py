"""
StockMind AI — Dev Service Restart
Lets the Settings page restart the backend/frontend dev servers instead of
switching to a terminal — this is a local-dev-only convenience (kills and
relaunches the uvicorn/next processes via shell scripts in `scripts/`) and
has no effect against the Docker Compose stack.
"""

import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.core.logging import get_logger
from app.models.user import User

router = APIRouter(prefix="/api/system", tags=["System"])
logger = get_logger(__name__)

# backend/app/api/routes/system.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = {
    "backend": REPO_ROOT / "scripts" / "restart-backend.sh",
    "frontend": REPO_ROOT / "scripts" / "restart-frontend.sh",
}


class RestartRequest(BaseModel):
    service: Literal["backend", "frontend", "both"]


def _launch(script: Path) -> None:
    log_path = REPO_ROOT / "logs" / f"{script.stem}.trigger.log"
    log_path.parent.mkdir(exist_ok=True)
    with open(log_path, "a") as log_file:
        subprocess.Popen(
            ["/bin/bash", str(script)],
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,  # detach — must outlive this request (and, for the backend script, this process)
        )


@router.post("/restart")
async def restart_service(body: RestartRequest, user: User = Depends(get_current_user)):
    """
    Kick off a restart of the given dev server(s) and return immediately.
    The backend restart kills *this* process a second after responding, so
    the client sees this response before the connection drops — expect the
    next request or two to fail while the new process comes up.
    """
    targets = ["backend", "frontend"] if body.service == "both" else [body.service]
    for name in targets:
        script = SCRIPTS[name]
        if not script.exists():
            raise HTTPException(status_code=500, detail=f"Restart script missing: {script}")
        _launch(script)
        logger.info("service_restart_triggered", service=name, user=user.email)

    return {"status": "restarting", "service": body.service}
