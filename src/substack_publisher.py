import json
import os
import re

import requests

from src.utils import setup_logger, PROJECT_ROOT

logger = setup_logger("substack_publisher")

SESSION_FILE = PROJECT_ROOT / "config" / "substack_session.json"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# One-time interactive setup
# ---------------------------------------------------------------------------

def setup_substack_auth() -> None:
    """Send a Substack magic link, follow it with requests, and save the full
    session cookie jar to config/substack_session.json."""

    publication_url = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
    if not publication_url:
        publication_url = input("Substack publication URL (e.g. https://yourblog.substack.com): ").strip().rstrip("/")

    email = input("Substack account email address: ").strip()

    s = requests.Session()
    s.headers["User-Agent"] = _UA

    # Step 1 — ask Substack to send a magic-link email
    try:
        r = s.post(
            "https://substack.com/api/v1/email-login",
            json={"email": email, "redirect": "/"},
            timeout=15,
        )
        if r.status_code == 200:
            print(f"\nMagic link sent to {email}. Check your inbox.")
        else:
            print(f"\n(Email-login API returned {r.status_code})")
            print("Please open https://substack.com/sign-in in your browser and sign in manually.")
    except Exception as exc:
        print(f"\n(Could not reach Substack login API: {exc})")
        print("Please open https://substack.com/sign-in in your browser and sign in manually.")

    print("\nStep 2: Open the email from Substack and copy the full login link.")
    print("Paste the complete URL here (it starts with https://substack.com/account/login or https://email.mg):")
    magic_url = input("> ").strip()

    if magic_url:
        try:
            r = s.get(magic_url, timeout=20, allow_redirects=True)
            print(f"Followed magic link → HTTP {r.status_code} ({r.url})")
        except Exception as exc:
            print(f"Error following magic link: {exc}")
            return

    # Step 3 — verify we got a useful session
    cookies = {c.name: c.value for c in s.cookies}
    auth_names = {"connect.sid", "substack.sid"}
    found = auth_names & set(cookies.keys())

    if not found:
        print("\nWARNING: No session cookie found. Auth may have failed.")
        print("Cookies received:", list(cookies.keys()))
        print("Try again — make sure to paste the full URL from the email.")
        return

    print(f"\nSession established. Found: {sorted(found)}")

    # Step 4 — save to JSON
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"publication_url": publication_url, "cookies": cookies}
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Session saved to: {SESSION_FILE}")
    print("\nYou can now run:  py main.py article")


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

class SubstackPublisher:
    def __init__(self):
        if not SESSION_FILE.exists():
            raise FileNotFoundError(
                f"Substack session not found at {SESSION_FILE}\n"
                "Run  py main.py substack-setup  to authenticate first."
            )

        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.publication_url = data.get("publication_url", "").rstrip("/")
        if not self.publication_url:
            raise ValueError("publication_url missing from session file. Re-run substack-setup.")

        # Build a requests.Session with the saved cookies
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _UA,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": self.publication_url + "/publish/post",
            "Origin": self.publication_url,
        })
        for name, value in data["cookies"].items():
            self.session.cookies.set(name, value, domain=".substack.com")

    # ------------------------------------------------------------------
    # Markdown → Tiptap JSON
    # ------------------------------------------------------------------

    def _parse_inline(self, text: str) -> list:
        nodes = []
        for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
            if not part:
                continue
            if re.match(r"^\*\*[^*]+\*\*$", part):
                nodes.append({"type": "text", "marks": [{"type": "bold"}], "text": part[2:-2]})
            elif re.match(r"^\*[^*]+\*$", part):
                nodes.append({"type": "text", "marks": [{"type": "italic"}], "text": part[1:-1]})
            else:
                nodes.append({"type": "text", "text": part})
        return nodes or [{"type": "text", "text": text}]

    def _parse_markdown_to_nodes(self, markdown_text: str) -> list:
        """Convert Markdown text to a list of Tiptap content nodes."""
        nodes = []
        lines = markdown_text.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].rstrip()

            m = re.match(r"^(#{1,3})\s+(.+)$", line)
            if m:
                nodes.append({
                    "type": "heading",
                    "attrs": {"level": len(m.group(1))},
                    "content": self._parse_inline(m.group(2)),
                })
                i += 1
                continue

            if re.match(r"^[-*]\s+", line):
                items = []
                while i < len(lines) and re.match(r"^[-*]\s+", lines[i].rstrip()):
                    item_text = re.sub(r"^[-*]\s+", "", lines[i].rstrip())
                    items.append({
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": self._parse_inline(item_text)}],
                    })
                    i += 1
                nodes.append({"type": "bulletList", "content": items})
                continue

            if not line:
                i += 1
                continue

            nodes.append({"type": "paragraph", "content": self._parse_inline(line)})
            i += 1

        return nodes

    def _markdown_to_tiptap(self, markdown_text: str) -> str:
        doc = {"type": "doc", "content": self._parse_markdown_to_nodes(markdown_text)}
        return json.dumps(doc)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, title: str, content: str, tags: list[str], subtitle: str = "") -> dict:
        """Create a draft and publish it publicly on Substack.

        Returns dict with at least a "url" key pointing to the published post.
        """
        # Step 1: Create draft
        # publication_id is returned in the response — no need to fetch separately
        draft_payload = {
            "draft_title": title,
            "draft_subtitle": subtitle,
            "draft_body": self._markdown_to_tiptap(content),
            "type": "newsletter",
            "audience": "everyone",
            "draft_bylines": [],  # empty = use publication default author
        }

        logger.info(f"Creating Substack draft: {title}")
        resp = self.session.post(
            f"{self.publication_url}/api/v1/drafts",
            json=draft_payload,
            timeout=30,
        )
        if resp.status_code in (302, 401, 403):
            raise RuntimeError(
                f"Authentication failed (HTTP {resp.status_code}). "
                "Session may have expired — re-run  py main.py substack-setup"
            )
        resp.raise_for_status()

        draft = resp.json()
        draft_id = draft.get("id")
        pub_id = draft.get("publication_id")
        if not draft_id:
            raise ValueError(f"No draft ID returned: {draft}")
        logger.info(f"Draft created (ID: {draft_id}, publication_id: {pub_id})")

        # Step 2: Publish
        publish_payload = {
            "send_email": True,
            "audience": "everyone",
            "publication_id": pub_id,
        }
        resp = self.session.post(
            f"{self.publication_url}/api/v1/drafts/{draft_id}/publish",
            json=publish_payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        post_url = (
            data.get("url")
            or data.get("canonical_url")
            or f"{self.publication_url}/p/{data.get('slug', draft_id)}"
        )
        logger.info(f"Published: {post_url}")
        return {"url": post_url, **data}

    def publish_paywalled(
        self,
        title: str,
        free_content: str,
        paid_content: str,
        tags: list[str],
        subtitle: str = "",
    ) -> dict:
        """Create a draft with a paywall node and publish it on Substack.

        Content before the paywall is visible to everyone; content after is
        visible only to paid subscribers.

        Returns dict with at least a "url" key pointing to the published post.
        """
        doc = {
            "type": "doc",
            "content": (
                self._parse_markdown_to_nodes(free_content)
                + [{"type": "paywall"}]
                + self._parse_markdown_to_nodes(paid_content)
            ),
        }

        # Substack requires audience="only_paid" when the body contains a paywall node
        draft_payload = {
            "draft_title": title,
            "draft_subtitle": subtitle,
            "draft_body": json.dumps(doc),
            "type": "newsletter",
            "audience": "only_paid",
            "draft_bylines": [],
        }

        logger.info(f"Creating paywalled Substack draft: {title}")
        resp = self.session.post(
            f"{self.publication_url}/api/v1/drafts",
            json=draft_payload,
            timeout=30,
        )
        if resp.status_code in (302, 401, 403):
            raise RuntimeError(
                f"Authentication failed (HTTP {resp.status_code}). "
                "Session may have expired — re-run  py main.py substack-setup"
            )
        resp.raise_for_status()

        draft = resp.json()
        draft_id = draft.get("id")
        pub_id = draft.get("publication_id")
        if not draft_id:
            raise ValueError(f"No draft ID returned: {draft}")
        logger.info(f"Paywalled draft created (ID: {draft_id}, publication_id: {pub_id})")

        publish_payload = {
            "send_email": True,
            "audience": "only_paid",
            "publication_id": pub_id,
        }
        resp = self.session.post(
            f"{self.publication_url}/api/v1/drafts/{draft_id}/publish",
            json=publish_payload,
            timeout=30,
        )
        if not resp.ok:
            logger.error(f"Publish failed {resp.status_code}: {resp.text}")
            resp.raise_for_status()
        data = resp.json()

        post_url = (
            data.get("url")
            or data.get("canonical_url")
            or f"{self.publication_url}/p/{data.get('slug', draft_id)}"
        )
        logger.info(f"Paywalled post published: {post_url}")
        return {"url": post_url, **data}
