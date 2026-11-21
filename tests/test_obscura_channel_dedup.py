"""Offline tests for the Obscura channel-based duplicate guard (branch obscura-channel-dedup).

Run:  python -m unittest tests.test_obscura_channel_dedup -v      (pytest also works)

Nothing here talks to YouTube, Claude or any network service, and nothing is uploaded:
the YouTube client, script generator, video builder and uploader are fakes.

Fixture policy (no secrets, no real data beyond the minimum):
- Real channel videos appear by video ID and title ONLY (the 2026-11-20 incident cases).
- Every description and tag below is SYNTHETIC, written for this test from the pipeline's
  own templates ("This episode investigates {topic}, ...") — not copied from YouTube.
- Filler videos (for pagination) have made-up IDs.
- The upload registry is a temporary file built here; the repo's real registry is not read.
- YOUTUBE_API_KEY_OBSCURA is set to a dummy value only so src.config_obscura imports.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.environ.setdefault("YOUTUBE_API_KEY_OBSCURA", "dummy-not-a-key")

import main as mainmod  # noqa: E402
import src.obscura_pipeline as op  # noqa: E402
import src.obscura_shorts_generator as sg  # noqa: E402

ROOPKUND = "The Skeleton Lake of Roopkund"
OAKVILLE = "The Oakville Blobs Mystery"


def _video(vid: str, title: str, duration: str, privacy: str, description: str = "", tags: list[str] | None = None) -> dict:
    return {
        "id": vid,
        "snippet": {"title": title, "description": description, "tags": tags or [],
                    "publishedAt": "2026-01-01T00:00:00Z"},
        "status": {"privacyStatus": privacy},
        "contentDetails": {"duration": duration},
    }


def _episode(topic: str) -> str:  # same sentence _build_obscura_description writes (synthetic)
    return f"Synthetic test text.\n\nThis episode investigates {topic}, one of the most disturbing unresolved cases in dark history."


# Real IDs + titles; descriptions/tags are synthetic.
REAL = [
    # 2026-05-08, private, never in the committed registry -> the 2026-11-20 duplicate.
    _video("HMwWmtynfvE", "Why Are There 800 Skeletons at the Bottom of This Himalayan Lake? | Unsolved Mystery",
           "PT9M45S", "private", _episode(ROOPKUND)),
    _video("AbXkmFvve0w", "Why Are 800 Skeletons in This Lake? — No #Shorts #DarkHistory #Mystery",
           "PT57S", "private", "Synthetic short text.", ["SkeletonLake"]),
    # In the (temporary) registry, public.
    _video("ZeQNkeerAhM", "Mysterious Blobs Fell From the Sky—Then Everyone Got Sick | Unsolved Mystery",
           "PT10M16S", "public", _episode(OAKVILLE)),
    # Public long-form missing from the registry.
    _video("JOsCVvmDbHs", "The Isdal Woman: Europe's Most Disturbing Cold Case — No Name, 9 Identities, No Answers",
           "PT10M1S", "public", "Synthetic: the Isdal Woman case."),
    # Short whose topic is only in a joined (CamelCase) tag.
    _video("G0xouLFWxvk", "The Crew Vanished Mid-Breakfast #Shorts #DarkHistory #Mystery",
           "PT59S", "public", "Synthetic: the Mary Celeste was found adrift.", ["GhostShip"]),
    _video("1J41qtnoRrY", "Someone Hijacked Live TV in 1987 — Curse #Shorts #DarkHistory #Mystery",
           "PT59S", "public", "Synthetic short text.", ["MaxHeadroom", "BroadcastIntrusion"]),
    # Mentions Philadelphia: must NOT count as the Delphi case.
    _video("IvTxixJgaHs", "No One Claimed His Body for 65 Years — America's Most Disturbing Cold Case",
           "PT11M4S", "public", "Synthetic: the Boy in the Box, found in Philadelphia in 1957."),
]
FILLER = [_video(f"FAKE{i:07d}", f"Synthetic filler {i} #Shorts", "PT45S", "public") for i in range(60)]
VIDEOS = REAL + FILLER  # 67 > 50: two pages


class FakeYouTube:
    """Minimal stand-in for the googleapiclient resource used by fetch_obscura_channel_videos."""

    def __init__(self, videos: list[dict], fail: bool = False):
        self.videos_data, self.fail = videos, fail

    class _Req:
        def __init__(self, value):
            self.value = value

        def execute(self):
            return self.value

    def channels(self):
        if self.fail:
            raise RuntimeError("synthetic API failure")
        outer = self
        return type("C", (), {"list": lambda _s, **k: outer._Req(
            {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU_FAKE"}}}]})})()

    def playlistItems(self):
        outer = self

        def lst(_s, pageToken=None, **k):
            start = int(pageToken or 0)
            page = outer.videos_data[start:start + 50]
            out = {"items": [{"contentDetails": {"videoId": v["id"]}} for v in page]}
            if start + 50 < len(outer.videos_data):
                out["nextPageToken"] = str(start + 50)
            return outer._Req(out)
        return type("P", (), {"list": lst})()

    def videos(self):
        outer = self
        by_id = {v["id"]: v for v in outer.videos_data}
        return type("V", (), {"list": lambda _s, id, **k: outer._Req({"items": [by_id[i] for i in id.split(",")]})})()


class _TempRegistry(unittest.TestCase):
    """Each test gets its own temporary PROJECT_ROOT with a small synthetic registry."""

    REGISTRY_ROWS = [
        {"video_id": "ZeQNkeerAhM", "title": "(synthetic row)", "topic": OAKVILLE, "file_path": "", "sha256": "x" * 64},
    ]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="obscura_test_"))
        analytics = self.tmp / "output" / "analytics"
        analytics.mkdir(parents=True)
        self.registry = analytics / "obscura_upload_registry.jsonl"
        self.registry.write_text("".join(json.dumps(r) + "\n" for r in self.REGISTRY_ROWS), encoding="utf-8")
        self._saved = {
            (op, "PROJECT_ROOT"): op.PROJECT_ROOT, (sg, "PROJECT_ROOT"): sg.PROJECT_ROOT,
            (op, "OBSCURA_TOPICS"): list(op.OBSCURA_TOPICS),
        }
        op.PROJECT_ROOT = self.tmp
        sg.PROJECT_ROOT = self.tmp

    def tearDown(self):
        for (mod, name), value in self._saved.items():
            if name == "OBSCURA_TOPICS":
                op.OBSCURA_TOPICS[:] = value
            else:
                setattr(mod, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)


class _Gen(op.ObscuraScriptGenerator):
    """Script generator without Claude."""

    def __init__(self):
        pass

    def generate(self, topic):
        return {"topic": topic, "title": f"Synthetic title for {topic}", "script": "synthetic", "description": "", "tags": []}


# ── helpers ──────────────────────────────────────────────────────────────────

class HelperTests(unittest.TestCase):
    def test_iso_duration(self):
        self.assertEqual(op._iso_duration_seconds("PT9M45S"), 585)
        self.assertEqual(op._iso_duration_seconds("PT57S"), 57)
        self.assertEqual(op._iso_duration_seconds("PT1H2M"), 3720)
        self.assertEqual(op._iso_duration_seconds("garbage"), 0)

    def test_gha_warning_escaping(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            op.gha_warning("A: b, c", "line1\nline2 100%")
        self.assertIn("::warning title=A%3A b%2C c::line1%0Aline2 100%25", buf.getvalue())

    def test_split_camel(self):
        self.assertEqual(op._split_camel("YubaCountyFive"), "Yuba County Five")
        self.assertEqual(op._split_camel("Cicada3301"), "Cicada 3301")
        self.assertEqual(op._split_camel("TVShow"), "TV Show")


class FetchTests(unittest.TestCase):
    def test_fetch_paginates_and_keeps_private(self):
        got = op.fetch_obscura_channel_videos(FakeYouTube(VIDEOS))
        self.assertEqual(len(got), len(VIDEOS))
        self.assertIn("HMwWmtynfvE", {v["id"] for v in got})

    def test_fetch_raises_on_api_error(self):
        with self.assertRaises(RuntimeError):
            op.fetch_obscura_channel_videos(FakeYouTube(VIDEOS, fail=True))


# ── topic matching ───────────────────────────────────────────────────────────

class MatchingTests(unittest.TestCase):
    def test_title_alone_misses_roopkund(self):  # the 2026-11-20 cause
        self.assertFalse(op._history_matches_topic(ROOPKUND, REAL[0]["snippet"]["title"]))

    def test_description_finds_roopkund(self):
        used = op._channel_used_topics(VIDEOS)
        self.assertIn("HMwWmtynfvE", used[ROOPKUND])

    def test_whole_word_no_substring(self):
        m = op._history_matches_topic
        self.assertFalse(m("The Delphi Murders Mystery", "found in Philadelphia in 1957"))
        self.assertTrue(m("The Delphi Murders Mystery", "two girls near Delphi, Indiana"))
        self.assertTrue(m(ROOPKUND, "800 skeletons in Roopkund lake"))  # plural kept
        self.assertFalse(m("The Mary Celeste Ghost Ship", "a ghostship"))

    def test_camelcase_tags_still_count(self):
        used = op._channel_used_topics(VIDEOS)
        self.assertIn("G0xouLFWxvk", used.get("The Mary Celeste Ghost Ship", []))
        self.assertIn("1J41qtnoRrY", used.get("The Max Headroom Broadcast Intrusion", []))

    def test_philadelphia_video_is_not_delphi(self):
        used = op._channel_used_topics(VIDEOS)
        self.assertNotIn("The Delphi Murders Mystery", used)


# ── registry backfill ────────────────────────────────────────────────────────

class BackfillTests(_TempRegistry):
    def test_backfill_adds_only_missing_long_form(self):
        before = self.registry.read_text(encoding="utf-8")
        added = op._backfill_registry_from_channel(VIDEOS)
        # Missing long-form only: not ZeQNkeerAhM (already in), not Shorts, not filler Shorts.
        self.assertEqual(sorted(added), ["HMwWmtynfvE", "IvTxixJgaHs", "JOsCVvmDbHs"])
        after = self.registry.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before), "append only")
        rows = {json.loads(l)["video_id"]: json.loads(l) for l in after.splitlines() if l.strip()}
        self.assertEqual(rows["HMwWmtynfvE"]["topic"], ROOPKUND)
        self.assertEqual(rows["HMwWmtynfvE"]["privacy"], "private")
        self.assertEqual(rows["HMwWmtynfvE"]["source"], "channel_backfill")
        self.assertEqual(rows["JOsCVvmDbHs"]["topic"], "The Isdal Woman Mystery")

    def test_backfill_is_idempotent(self):
        op._backfill_registry_from_channel(VIDEOS)
        self.assertEqual(op._backfill_registry_from_channel(VIDEOS), [])

    def test_registry_learns_roopkund(self):
        self.assertNotIn(ROOPKUND, op._recent_registry_topics())
        op._backfill_registry_from_channel(VIDEOS)
        self.assertIn(ROOPKUND, op._recent_registry_topics())

    def test_short_never_links_private_backfilled_long_form(self):
        op._backfill_registry_from_channel(VIDEOS)
        self.assertIsNone(sg._find_longform_video_id(ROOPKUND))
        self.assertEqual(sg._find_longform_video_id(OAKVILLE), "ZeQNkeerAhM")  # pipeline row: unchanged


# ── topic choice ─────────────────────────────────────────────────────────────

class TopicChoiceTests(_TempRegistry):
    def test_never_picks_a_channel_covered_topic(self):
        used = set(op._channel_used_topics(VIDEOS)) | {OAKVILLE}
        for _ in range(20):
            self.assertNotIn(_Gen().generate_random(VIDEOS)["topic"], used)

    def test_picks_from_what_is_left(self):
        op.OBSCURA_TOPICS[:] = [ROOPKUND, OAKVILLE, "The Amber Room Disappearance"]
        for _ in range(5):
            self.assertEqual(_Gen().generate_random(VIDEOS)["topic"], "The Amber Room Disappearance")

    def test_all_used_raises_instead_of_reusing(self):
        op.OBSCURA_TOPICS[:] = [ROOPKUND, OAKVILLE]
        with self.assertRaises(op.ObscuraNoUnusedTopic):
            _Gen().generate_random(VIDEOS)


# ── run_obscura_pipeline end to end (all fakes) ──────────────────────────────

class PipelineTests(_TempRegistry):
    def setUp(self):
        super().setUp()
        test = self

        class FakeUploader:
            instances = 0

            def __init__(self):
                FakeUploader.instances += 1
                self.youtube = FakeYouTube(VIDEOS, fail=test.yt_fail)
                self.duplicate_of = None

            def upload(self, path, meta):
                self.duplicate_of = test.dup
                return test.dup or "NEWVIDEO001"

        class FakeVideo:
            builds = 0

            def generate(self, data):
                FakeVideo.builds += 1
                return test.tmp / "synthetic.mp4"

        self.FakeUploader, self.FakeVideo = FakeUploader, FakeVideo
        self.dup, self.yt_fail = None, False
        for name, value in (("ObscuraYouTubeUploader", FakeUploader), ("ObscuraScriptGenerator", _Gen),
                            ("ObscuraVideoGenerator", FakeVideo),
                            ("_acquire_obscura_run_lock", lambda: self.tmp / "lock"),
                            ("_release_obscura_run_lock", lambda p: None)):
            self._saved[(op, name)] = getattr(op, name)
            setattr(op, name, value)
        self._saved_env = os.environ.pop("OBSCURA_SKIP_UPLOAD", None)

    def tearDown(self):
        os.environ.pop("OBSCURA_SKIP_UPLOAD", None)
        if self._saved_env is not None:
            os.environ["OBSCURA_SKIP_UPLOAD"] = self._saved_env
        super().tearDown()

    def run_pipeline(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            result = op.run_obscura_pipeline(**kw)
        return result, buf.getvalue()

    def test_normal_upload(self):
        r, out = self.run_pipeline()
        self.assertEqual(r["video_id"], "NEWVIDEO001")
        self.assertFalse(r.get("skipped"))
        self.assertNotIn("::warning", out)

    def test_late_duplicate_is_skipped_loudly(self):
        self.dup = "HMwWmtynfvE"
        r, out = self.run_pipeline()
        self.assertTrue(r["skipped"])
        self.assertEqual(r["reason"], "duplicate_upload")
        self.assertIsNone(r["video_id"])
        self.assertEqual(r["existing_video_id"], "HMwWmtynfvE")
        self.assertIn("::warning title=Obscura long-form skipped (duplicate)::", out)

    def test_explicit_used_topic_skipped_before_any_build(self):
        r, out = self.run_pipeline(topic=ROOPKUND)
        self.assertEqual(r["reason"], "duplicate_topic")
        self.assertIsNone(r["video_id"])
        self.assertEqual(self.FakeVideo.builds, 0)
        self.assertIn("::warning", out)

    def test_channel_api_error_degrades_to_registry(self):
        self.yt_fail = True
        r, out = self.run_pipeline()
        self.assertEqual(r["video_id"], "NEWVIDEO001")
        self.assertIn("Obscura channel check unavailable", out)

    def test_no_unused_topic(self):
        op.OBSCURA_TOPICS[:] = [ROOPKUND, OAKVILLE]
        r, out = self.run_pipeline()
        self.assertEqual(r["reason"], "no_unused_topic")
        self.assertIn("::warning", out)

    def test_skip_upload_does_not_authenticate(self):
        os.environ["OBSCURA_SKIP_UPLOAD"] = "1"
        r, _ = self.run_pipeline()
        self.assertEqual(r["reason"], "skip_upload")
        self.assertEqual(self.FakeUploader.instances, 0)


# ── main.py exit codes ───────────────────────────────────────────────────────

class CommandTests(unittest.TestCase):
    def setUp(self):
        self.calls: list[dict] = []
        self._saved = (op.run_obscura_pipeline, sg.run_obscura_shorts_pipeline)
        sg.run_obscura_shorts_pipeline = lambda **k: self.calls.append(k) or {"video_id": "S", "duration": 1.0}

    def tearDown(self):
        op.run_obscura_pipeline, sg.run_obscura_shorts_pipeline = self._saved

    def run_cmd(self, result, fn=None):
        op.run_obscura_pipeline = lambda topic=None: result
        buf, code = io.StringIO(), None
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            try:
                (fn or mainmod.cmd_obscura_run)()
            except SystemExit as exc:
                code = exc.code
        return code, buf.getvalue()

    def test_skipped_exit_codes_and_no_short(self):
        for reason, want in (("duplicate_upload", 1), ("duplicate_topic", 1),
                             ("duplicate_run_locked", 1), ("no_unused_topic", 3)):
            with self.subTest(reason=reason):
                code, out = self.run_cmd({"video_id": None, "existing_video_id": "HMwWmtynfvE", "topic": "X",
                                          "skipped": True, "reason": reason})
                self.assertEqual(code, want)
                self.assertEqual(self.calls, [])
                self.assertIn("::warning title=Obscura Short not generated::", out)
                self.assertNotIn("run complete", out)

    def test_single_obscura_command_exit_3(self):
        code, _ = self.run_cmd({"video_id": None, "topic": "X", "skipped": True, "reason": "no_unused_topic"},
                               fn=lambda: mainmod.cmd_obscura(None))
        self.assertEqual(code, 3)

    def test_normal_run_links_short(self):
        code, _ = self.run_cmd({"video_id": "NEW", "topic": "Y", "title": "t", "video_path": "p"})
        self.assertIsNone(code)
        self.assertEqual(self.calls[-1], {"topic": "Y", "long_form_video_id": "NEW"})

    def test_skip_upload_still_builds_short(self):
        code, _ = self.run_cmd({"video_id": None, "topic": "Z", "skipped": True, "reason": "skip_upload"})
        self.assertIsNone(code)
        self.assertEqual(self.calls[-1]["topic"], "Z")


# ── Shorts description ───────────────────────────────────────────────────────

class ShortsDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.build = sg._build_obscura_shorts_description
        self.cta = sg.config_shorts.SUBSCRIBE_CTA
        self.hashtags = " ".join(sg.config_shorts.REQUIRED_HASHTAGS + sg.config_shorts.OPTIONAL_HASHTAGS[:3])
        self.ask = "Want the full investigation? Comment FULL CASE below."
        self.link = "https://www.youtube.com/watch?v=FAKELONG001"

    def test_generate_then_rebuild_once(self):
        first = self.build("Synthetic test description.", "T")          # in generate()
        second = self.build(first, "T", long_form_url=self.link)      # rebuilt with the link
        self.assertEqual(second.count(self.cta), 1)
        self.assertEqual(second.count(self.hashtags), 1)
        self.assertEqual(second.count(self.link), 1)
        self.assertNotIn(self.ask, second)
        self.assertTrue(second.startswith("Synthetic test description."))
        self.assertEqual(self.build(second, "T", long_form_url=self.link), second)
        self.assertEqual(self.build(first, "T"), first)

    def test_repairs_the_doubled_shape(self):
        # Same SHAPE as the 2026-11-20 Short (synthetic first paragraph, fake link).
        doubled = "\n\n".join(["Synthetic test description.", self.ask, self.cta, self.hashtags,
                               "🔍 Full investigation: https://www.youtube.com/watch?v=FAKEOLD0001",
                               self.cta, self.hashtags])
        fixed = self.build(doubled, "T", long_form_url=self.link)
        self.assertEqual(fixed.count(self.cta), 1)
        self.assertEqual(fixed.count(self.hashtags), 1)
        self.assertEqual(fixed.count("Full investigation"), 1)
        self.assertNotIn("FAKEOLD0001", fixed)
        self.assertNotIn(self.ask, fixed)


# ── workflow + ledger ────────────────────────────────────────────────────────

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        import yaml
        wf = yaml.safe_load((REPO / ".github/workflows/obscura_daily.yml").read_text(encoding="utf-8"))
        steps = next(iter(wf["jobs"].values()))["steps"]
        self.run_step = next(s for s in steps if s.get("id") == "obscura_run")
        self.retry = next(s for s in steps if s.get("name") == "Retry Obscura pipeline on failure")

    def test_retry_skips_exit_3(self):
        self.assertIn("failure()", self.retry["if"])
        self.assertIn("steps.obscura_run.outputs.exit_code != '3'", self.retry["if"])

    def test_run_step_records_and_propagates_exit_code(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not available")
        cmd = "bash .github/scripts/run_with_memory_cap.sh python main.py obscura-run"
        self.assertIn(cmd, self.run_step["run"])
        with tempfile.TemporaryDirectory() as tmp:
            for rc in (0, 1, 3):
                with self.subTest(rc=rc):
                    out_file = Path(tmp) / f"out_{rc}"
                    script = self.run_step["run"].replace(cmd, f"(exit {rc})")
                    p = subprocess.run([bash, "-e", "-c", script], env={**os.environ, "GITHUB_OUTPUT": str(out_file)})
                    self.assertEqual(p.returncode, rc)
                    self.assertEqual(out_file.read_text().strip(), f"exit_code={rc}")


class LedgerTests(unittest.TestCase):
    def test_obscura_topics_left_item(self):
        sys.path.insert(0, str(REPO / ".github/actions/quiet-pipelines"))
        from quiet_pipelines import config as qp_config, ledger as qp_ledger
        cfg = qp_config.load(REPO / "config/quiet-pipelines.yml")
        item = next(i for i in cfg.ledger_items if i.get("id") == "obscura_topics_left")
        expires = qp_ledger.as_date(item["expires"])
        self.assertIsNotNone(expires, "expires must be a date")
        rep = qp_ledger.evaluate(cfg.ledger_items, expires - timedelta(days=20), cfg.warn_within_days, cfg.stale_after_days)
        self.assertEqual(rep.invalid, [])
        self.assertIn("obscura_topics_left", [r["id"] for r in rep.expiring_soon])


if __name__ == "__main__":
    unittest.main(verbosity=2)
