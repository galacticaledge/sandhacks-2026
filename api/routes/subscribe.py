"""Alert subscriptions: contact + receptor + language + channel only. One-click unsubscribe."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from db import store
from model.run import receptors

router = APIRouter(prefix="/api")


class Sub(BaseModel):
    contact: str = Field(min_length=3, max_length=200)
    channel: str = Field("email", pattern="^email$")  # SMS was cut from scope
    language: str = Field("en", pattern="^(en|es)$")
    receptor_id: str


@router.post("/subscribe")
def subscribe(s: Sub):
    if s.receptor_id not in {r["id"] for r in receptors() if r["kind"] != "monitor"}:
        raise HTTPException(400, "unknown neighborhood or school")
    if "@" not in s.contact or "." not in s.contact.split("@")[-1]:
        raise HTTPException(400, "enter a valid email address")
    token = secrets.token_urlsafe(24)
    store.add_subscription({"id": uuid.uuid4().hex, "contact": s.contact.strip().lower(), "channel": s.channel,
                            "language": s.language, "receptor_id": s.receptor_id,
                            "created_at": datetime.now(timezone.utc), "token": token})
    return {"ok": True, "unsubscribe_url": f"/api/unsubscribe/{token}"}


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str):
    ok = store.remove_subscription(token)
    msg = ("You are unsubscribed. We deleted your contact details. / Se canceló su suscripción y borramos sus datos."
           if ok else "This link was already used or is invalid. / Este enlace ya se usó o no es válido.")
    return f"<!doctype html><meta charset=utf-8><title>Smellcast</title><body style='font-family:system-ui;max-width:36rem;margin:3rem auto;padding:0 1rem'><h1>Smellcast</h1><p>{msg}</p><p><a href='/'>Smellcast</a></p>"
