"""Reports from visitors, the admin page's API, and counting page views."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import admin, jobs, social
from app.middleware.auth import require_username
from app.routes.community import listener

router = APIRouter(tags=["admin"])


def require_admin(me: str = Depends(require_username)) -> str:
    if not admin.is_admin(me):
        raise HTTPException(status_code=403, detail="Only the site's admins can see this.")
    return me


# ---- reporting (anyone) -------------------------------------------------------------------

class ReportRequest(BaseModel):
    kind: str = Field(..., description="map, profile, pin, track or constellation")
    target: str = Field(..., min_length=1, max_length=100, description="Share id, username, pin id or track id")
    reason: str = Field(..., description=", ".join(admin.REASONS))
    details: Optional[str] = Field(None, max_length=1000)


@router.post("/reports", dependencies=[Depends(jobs.rate_limit("report", 30))])
def make_report(req: ReportRequest, voter: Optional[str] = Depends(listener)) -> dict:
    """Tell the site's admins something breaks the rules."""
    if not voter:
        raise HTTPException(status_code=400, detail="Sign in or send an X-Listener-Id header to report.")
    try:
        return admin.report(req.kind, req.target, req.reason, req.details, voter)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/reports/reasons")
def report_reasons() -> dict:
    return {"reasons": [{"id": k, "label": v} for k, v in admin.REASONS.items()]}


# ---- visitor stats (anyone sends, admins read) ----------------------------------------------

class ViewRequest(BaseModel):
    path: str = Field(..., max_length=200)
    referrer: Optional[str] = Field(None, max_length=500)


@router.post("/stats/view", dependencies=[Depends(jobs.rate_limit("view", 600))])
def page_view(req: ViewRequest, request: Request) -> dict:
    """Count one page view (sent by the website as pages open)."""
    if request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return {"ok": False}
    kept = admin.record_view(req.path, req.referrer, jobs.client_ip(request),
                             request.headers.get("user-agent", ""), request.headers.get("host"))
    return {"ok": kept}


# ---- admin page --------------------------------------------------------------------------

@router.get("/admin/stats")
def admin_stats(days: int = 30, me: str = Depends(require_admin)) -> dict:
    return admin.stats(days)


@router.get("/admin/reports")
def admin_reports(status: str = "open", me: str = Depends(require_admin)) -> dict:
    if status not in ("open", "removed", "dismissed"):
        raise HTTPException(status_code=400, detail="status is open, removed or dismissed")
    return {"reports": admin.reports(status), "reasons": admin.REASONS}


class ResolveRequest(BaseModel):
    action: str = Field(..., description="remove or dismiss")


@router.post("/admin/reports/{report_id}")
def admin_resolve(report_id: int, req: ResolveRequest, me: str = Depends(require_admin)) -> dict:
    try:
        return admin.resolve(report_id, req.action, me)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/users/{username}/delete")
def admin_delete_user(username: str, me: str = Depends(require_admin)) -> dict:
    """Delete someone's account and everything it made (for repeat offenders)."""
    u = social.user_row(username)
    if not u:
        raise HTTPException(status_code=404, detail="No such account.")
    if admin.is_admin(u["username"]):
        raise HTTPException(status_code=400, detail="Admins can't be deleted from here. Remove them from SM_ADMINS first.")
    return social.delete_account(u["username"])
