"""Small interactive helper to generate TikTok OAuth URL and exchange code.

Usage:
  python scripts/tiktok_auth_test.py

It reads `config/config.yaml` for `tiktok.client_key`, `tiktok.client_secret`,
and `tiktok.redirect_uri` if present. Otherwise it prompts for values.
"""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

import yaml

from src.tiktok_uploader import TikTokUploader


def load_config():
    cfg_path = Path("config/config.yaml")
    if cfg_path.exists():
        return yaml.safe_load(cfg_path.read_text()) or {}
    return {}


def main():
    cfg = load_config()
    tcfg = cfg.get("tiktok", {})
    client_key = tcfg.get("client_key") or input("TikTok client_key: ")
    client_secret = tcfg.get("client_secret") or input("TikTok client_secret: ")
    redirect_uri = tcfg.get("redirect_uri") or input("Redirect URI: ")

    uploader = TikTokUploader(client_key=client_key, client_secret=client_secret, redirect_uri=redirect_uri)
    auth_url = uploader.build_authorize_url()
    print("Open this URL in your browser and authorize the app:")
    print(auth_url)
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    code = input("After authorizing, paste the `code` parameter from the redirect URL here: ")
    if not code:
        print("No code provided; exiting.")
        sys.exit(1)

    token_resp = uploader.exchange_code_for_access_token(code)
    print("Token response (store securely):")
    print(token_resp)


if __name__ == "__main__":
    main()
