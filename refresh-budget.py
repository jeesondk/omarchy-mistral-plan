#!/usr/bin/python3
"""Save Mistral's plan and Vibe budget for the Agents panel.

Reads the public billing API Vibe's own footer uses (/v1/billing/subscription and
/v1/billing/budget) and writes the fields to merge into the panel's Vibe record.
Service.qml does the merging. Exits non-zero on a failure worth retrying soon.
"""

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

API_BASE = "https://api.mistral.ai/v1/billing/"
KEY_NAME = "MISTRAL_API_KEY"
MAX_RESPONSE_BYTES = 64 * 1024
MAX_AMOUNT = 1_000_000_000
PLAN_NAME = re.compile(r"[A-Za-z0-9_ -]{1,40}")
CURRENCY = re.compile(r"[A-Z]{3}")


class Refused(Exception):
  """The key was refused, or may not read the budget."""


def state_home():
  return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")


def budget_path():
  return state_home() / "omarchy" / "mistral-plan" / "budget.json"


def vibe_home():
  configured = os.environ.get("VIBE_HOME", "").strip()
  return Path(configured).expanduser() if configured else Path.home() / ".vibe"


def api_key():
  """The key Vibe would use: the environment first, then Vibe's .env."""
  key = os.environ.get(KEY_NAME, "").strip()
  if key:
    return key
  try:
    lines = (vibe_home() / ".env").read_text().splitlines()
  except (OSError, UnicodeDecodeError):
    return ""
  for line in lines:
    name, _, value = line.removeprefix("export ").partition("=")
    if name.strip() == KEY_NAME:
      return value.strip().strip("'\"")
  return ""


def fetch(key, path):
  request = urllib.request.Request(
    API_BASE + path,
    headers={
      "Authorization": f"Bearer {key}",
      "Accept": "application/json",
      "User-Agent": "omarchy-mistral-plan",
    },
  )
  try:
    with urllib.request.urlopen(request, timeout=15) as response:
      raw = response.read(MAX_RESPONSE_BYTES + 1)
  except urllib.error.HTTPError as error:
    if error.code in (401, 403):
      raise Refused(f"{path} answered HTTP {error.code}") from None
    raise
  if len(raw) > MAX_RESPONSE_BYTES:
    raise ValueError(f"{path} answer is too large")
  return json.loads(raw)


def number(value):
  """A finite, sane non-negative amount, or None."""
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return None
  return float(value) if math.isfinite(value) and 0 <= value <= MAX_AMOUNT else None


def read_pool(detail):
  """One budget pool as (used %, total, currency, reset), or None if implausible."""
  if not isinstance(detail, dict):
    return None
  used, total = number(detail.get("usage_percentage")), number(detail.get("initial_budget"))
  currency, reset = detail.get("currency"), detail.get("reset_at")
  if used is None or not total or not isinstance(currency, str) or not CURRENCY.fullmatch(currency):
    return None
  try:
    datetime.fromisoformat(reset)
  except (TypeError, ValueError):
    return None
  return used, total, currency, reset


def meter(title, pool):
  return {"label": f"{title} budget", "title": title, "percent": pool[0] / 100, "resetsAt": pool[3]}


def build_patch(budget, subscription, now_ms):
  """The record fields for a budget answer, or None if it isn't a plausible one.

  A plan includes a monthly Vibe Code pool and a smaller API pool, each consumed
  first. Pay-as-you-go credits pay for anything past them, but the API only says
  whether PAYG is on, not what it has cost: usage_percentage is documented as 0-100.
  The Vibe pool gets the balance block, as the panel only has one per agent; the API
  pool gets a meter.
  """
  if not isinstance(budget, dict):
    return None
  vibe = read_pool(budget.get("vibe_budget"))
  if vibe is None:
    return None
  used, total, currency, _ = vibe
  spent = total * used / 100

  limits = [meter("Vibe", vibe)]
  api = read_pool(budget.get("api_budget"))
  if api is not None:
    limits.append(meter("API", api))

  patch = {
    "ready": True,
    "limits": limits,
    "limitsFetchedAt": now_ms,
    "balance": {
      "remaining": round(max(0.0, total - spent), 2),
      "funded": round(total, 2),
      "spent": round(spent, 2),
      "currency": currency,
    },
  }

  name = subscription.get("plan_name") if isinstance(subscription, dict) else None
  if isinstance(name, str) and PLAN_NAME.fullmatch(name.strip()):
    plan = name.strip().capitalize()
    payg = subscription.get("vibe_payg_enabled") is True or subscription.get("payg_enabled") is True
    patch["tierLabel"] = f"{plan} · PAYG" if payg else plan
  return patch


def save(patch):
  path = budget_path()
  path.parent.mkdir(parents=True, exist_ok=True)
  fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".budget.")
  try:
    with os.fdopen(fd, "w") as handle:
      json.dump(patch, handle)
    os.replace(tmp, path)
  except BaseException:
    os.unlink(tmp)
    raise


def forget():
  """Stop showing a budget we can no longer vouch for, and clean the record."""
  try:
    budget_path().unlink()
  except FileNotFoundError:
    return
  try:
    subprocess.run(["omarchy-agent-usage-update", "vibe"], timeout=120, check=True)
  except (OSError, subprocess.SubprocessError) as error:
    print(f"mistral-plan: could not refresh the panel: {error}", file=sys.stderr)


def main():
  key = api_key()
  if not key:
    print(f"mistral-plan: no {KEY_NAME} in the environment or Vibe's .env", file=sys.stderr)
    forget()
    return 0

  try:
    budget = fetch(key, "budget")
  except Refused as error:
    print(f"mistral-plan: {error}", file=sys.stderr)
    forget()
    return 0
  except (OSError, ValueError) as error:
    print(f"mistral-plan: budget unavailable: {type(error).__name__}", file=sys.stderr)
    return 1

  try:
    subscription = fetch(key, "subscription")
  except (Refused, OSError, ValueError):
    subscription = None

  patch = build_patch(budget, subscription, int(time.time() * 1000))
  if patch is None:
    print("mistral-plan: budget answer was not recognisable", file=sys.stderr)
    return 1
  save(patch)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
