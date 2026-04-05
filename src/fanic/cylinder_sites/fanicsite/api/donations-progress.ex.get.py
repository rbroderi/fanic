import math
from typing import cast

import requests

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import json_response
from fanic.settings import get_settings


def _as_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    try:
        parsed = float(text)
    except ValueError:
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _support_amount_from_item(item: dict[str, object]) -> float:
    coffees_count = _as_float(item.get("support_coffees"))
    coffee_price = _as_float(item.get("support_coffee_price"))
    amount = coffees_count * coffee_price
    if amount > 0:
        return amount

    fallback_keys = (
        "support_amount",
        "amount",
        "total_amount",
        "donation_amount",
    )
    for key in fallback_keys:
        fallback_amount = _as_float(item.get(key))
        if fallback_amount > 0:
            return fallback_amount
    return 0.0


def _sum_supporter_amount(payload: dict[str, object]) -> float:
    data_obj = payload.get("data")
    if not isinstance(data_obj, list):
        return 0.0
    data = cast(list[object], data_obj)

    total = 0.0
    for item_obj in data:
        if not isinstance(item_obj, dict):
            continue
        item = cast(dict[str, object], item_obj)
        total += _support_amount_from_item(item)
    return total


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/api/donations-progress":
        return json_response(response, {"detail": "Not found"}, 404)

    settings = get_settings()
    goal_amount = _as_float(settings.buymeacoffee_goal_amount)
    if goal_amount <= 0:
        goal_amount = 1.0

    api_key = settings.buymeacoffee_api_key.strip()
    if not api_key:
        return json_response(
            response,
            {
                "ok": True,
                "label": "Keep the website running",
                "current_total": 0.0,
                "goal_total": goal_amount,
                "progress_ratio": 0.0,
                "currency": "USD",
                "source": "disabled",
            },
        )

    api_url = settings.buymeacoffee_api_url.strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    try:
        upstream = requests.get(api_url, headers=headers, timeout=8)
        upstream.raise_for_status()
        payload_obj: object = upstream.json()
    except (requests.RequestException, ValueError):
        return json_response(
            response,
            {
                "ok": False,
                "label": "Keep the website running",
                "current_total": 0.0,
                "goal_total": goal_amount,
                "progress_ratio": 0.0,
                "currency": "USD",
                "source": "error",
            },
            502,
        )

    payload_map = cast(dict[str, object], payload_obj) if isinstance(payload_obj, dict) else {}
    current_total = _sum_supporter_amount(payload_map)
    if current_total < 0:
        current_total = 0.0

    progress_ratio = current_total / goal_amount
    if progress_ratio < 0:
        progress_ratio = 0.0
    if progress_ratio > 1:
        progress_ratio = 1.0

    return json_response(
        response,
        {
            "ok": True,
            "label": "Keep the website running",
            "current_total": round(current_total, 2),
            "goal_total": round(goal_amount, 2),
            "progress_ratio": round(progress_ratio, 4),
            "currency": "USD",
            "source": "buymeacoffee",
        },
    )
