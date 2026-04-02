#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    args = parser.parse_args()

    url = "https://places.googleapis.com/v1/places:searchText"
    payload = json.dumps(
        {
            "textQuery": "farmacia urbanova sao jose dos campos",
            "maxResultCount": 1,
            "languageCode": "pt-BR",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": args.api_key,
            "X-Goog-FieldMask": "places.id,places.displayName",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        places = data.get("places", [])
        print(
            json.dumps(
                {
                    "ok": True,
                    "places_returned": len(places),
                    "message": "API key valida para Places API (New).",
                },
                ensure_ascii=False,
            )
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({"ok": False, "http_code": exc.code, "error": body}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == "__main__":
    main()

