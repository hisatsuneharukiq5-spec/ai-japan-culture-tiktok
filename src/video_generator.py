import os
import re
import json
import shutil
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import List

import requests
import edge_tts
import whisper
import math
from urllib.parse import quote_plus

from src.utils import get_config, setup_logger, PROJECT_ROOT

logger = setup_logger("video_generator")


def _chunk_narration(text: str, max_chars: int = 1200) -> List[str]:
    sentences = re.split(r'(?<=[。.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [text]

    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = sentence
        else:
            chunks.append(sentence)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _split_into_scenes(narration: str, target_seconds: int = 7, wps: float = 2.2) -> List[str]:
    # Split into paragraphs first
    parts = [p.strip() for p in narration.split("\n\n") if p.strip()]
    if not parts:
        # Fallback: split on sentence boundaries
        parts = re.split(r'(?<=[。.!?])\s+', narration)
        parts = [p.strip() for p in parts if p.strip()]

    # Merge small parts so estimated duration per part is within 5-10s
    scenes: List[str] = []
    for p in parts:
        if not scenes:
            scenes.append(p)
            continue
        # estimate words
        wcount = len(p.split())
        est_sec = wcount / wps
        if est_sec < 4 and scenes:
            # merge with previous scene
            scenes[-1] = scenes[-1] + " " + p
        else:
            scenes.append(p)

    # ensure each scene is not too long; split long scenes by sentence
    final = []
    for s in scenes:
        words = s.split()
        if len(words) > target_seconds * wps * 1.8:
            # split by sentences
            subs = re.split(r'(?<=[。.!?])\s+', s)
            final.extend([x.strip() for x in subs if x.strip()])
        else:
            final.append(s)

    return final


class VideoGenerator:
    def __init__(self):
        self.config = get_config()
        self.video_config = self.config.get("video", {})
        self.videos_dir = PROJECT_ROOT / self.config["output"]["videos_dir"]
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.target_duration_sec = int(float(self.video_config.get("target_duration_minutes", 10)) * 60)
        self.pexels_key = os.getenv("PEXELS_API_KEY")
        if not self.pexels_key:
            logger.warning("PEXELS_API_KEY not set; B-roll download will be skipped.")

    def _probe_duration(self, media_path: Path) -> float:
        import subprocess

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(media_path),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            return 0.0
        try:
            return float(res.stdout.decode().strip())
        except Exception:
            return 0.0

    def _create_silent_audio(self, out_audio: Path, duration: float):
        """Create a silent audio file using ffmpeg for fallback when TTS fails."""
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=mono",
            "-t",
            str(duration),
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(out_audio),
        ]
        try:
            subprocess_run(cmd)
            logger.info(f"Created silent audio fallback: {out_audio}")
        except Exception as e:
            logger.warning(f"Failed to create silent audio: {e}")

    def _download_pexels_clip(self, query: str, out_path: Path, max_duration: int = 10) -> bool:
        if os.getenv("DISABLE_PEXELS", "0") == "1":
            return False
        if not self.pexels_key:
            return False
        headers = {"Authorization": self.pexels_key}
        params = {"query": query, "per_page": 40}  # 取得数を増やす
        resp = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for v in data.get("videos", []):
            # pick a file with mp4 and reasonable resolution
            files = v.get("video_files", [])
            files_sorted = sorted(files, key=lambda x: x.get("height", 0), reverse=True)
            for f in files_sorted:
                link = f.get("link")
                if link and f.get("fps", 0) >= 24:
                    try:
                        with requests.get(link, stream=True, timeout=60) as r:
                            r.raise_for_status()
                            with open(out_path, "wb") as fh:
                                shutil.copyfileobj(r.raw, fh)
                        return True
                    except Exception:
                        continue
        return False

    def _synthesize_narration(self, text: str, out_audio: Path, voice: str = None):
        # Use Edge TTS with rate control.
        # For long narrations, synthesize in chunks to avoid long request hangs.
        voice = voice or os.getenv("EDGE_TTS_VOICE", "en-US-JennyNeural")
        logger.info(f"Synthesizing narration with voice={voice}")
        chunks = _chunk_narration(text, max_chars=1200)
        tts_timeout = int(os.getenv("TTS_CHUNK_TIMEOUT", "120"))  # Max 120s per chunk

        if len(chunks) == 1:
            try:
                communicate = edge_tts.Communicate(chunks[0], voice, rate="-10%")
                asyncio.run(asyncio.wait_for(communicate.save(str(out_audio)), timeout=tts_timeout))
            except asyncio.TimeoutError:
                logger.error("TTS synthesis timeout on single chunk; creating silent audio as fallback")
                self._create_silent_audio(out_audio, 10)
            return

        tts_dir = out_audio.parent / "tts_chunks"
        tts_dir.mkdir(parents=True, exist_ok=True)
        chunk_files: List[Path] = []
        for i, chunk in enumerate(chunks):
            chunk_path = tts_dir / f"chunk_{i:03d}.mp3"
            try:
                communicate = edge_tts.Communicate(chunk, voice, rate="-10%")
                asyncio.run(asyncio.wait_for(communicate.save(str(chunk_path)), timeout=tts_timeout))
                logger.info(f"TTS chunk {i} completed")
                chunk_files.append(chunk_path)
            except asyncio.TimeoutError:
                logger.warning(f"TTS synthesis timeout on chunk {i}; creating silent segment")
                self._create_silent_audio(chunk_path, 5)
                chunk_files.append(chunk_path)
            except Exception as e:
                logger.warning(f"TTS synthesis failed on chunk {i}: {e}; creating silent segment")
                self._create_silent_audio(chunk_path, 5)
                chunk_files.append(chunk_path)

        concat_list = tts_dir / "concat.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for path in chunk_files:
                f.write(f"file '{path.as_posix()}'\n")

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(out_audio),
        ]
        subprocess_run(cmd)

    def _generate_subtitles_srt(self, audio_path: Path, srt_path: Path):
        # Use Whisper to transcribe and write SRT
        logger.info("Running Whisper transcription for subtitles...")
        model_name = os.getenv("WHISPER_MODEL", "small")
        model = whisper.load_model(model_name)
        result = model.transcribe(str(audio_path))
        segments = result.get("segments", [])
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, start=1):
                start = seg["start"]
                end = seg["end"]
                text = seg["text"].strip()
                def fmt(t):
                    h = int(t // 3600)
                    m = int((t % 3600) // 60)
                    s = int(t % 60)
                    ms = int((t - int(t)) * 1000)
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                f.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n")

    def _generate_subtitles_ass(self, audio_path: Path, ass_path: Path):
        """
        Generate an ASS subtitle file from the Whisper transcription with a readable style.
        """
        logger.info("Generating ASS subtitles via Whisper...")
        model_name = os.getenv("WHISPER_MODEL", "small")
        model = whisper.load_model(model_name)
        result = model.transcribe(str(audio_path))
        segments = result.get("segments", [])

        header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1920\n"
            "PlayResY: 1080\n"
            "Timer: 100.0000\n\n"
        )
        styles = (
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,40,1\n\n"
        )
        events_header = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

        def fmt_time(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            cs = int((t - int(t)) * 100)
            return f"{h:01d}:{m:02d}:{s:02d}.{cs:02d}"

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write(styles)
            f.write(events_header)
            for seg in segments:
                start = fmt_time(seg["start"]) 
                end = fmt_time(seg["end"]) 
                text = seg["text"].replace("\n", " ").replace("{", "(").replace("}", ")")
                line = f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"
                f.write(line)

    def _fetch_cc0_bgm(self, out_path: Path) -> bool:
        """
        Try to fetch a CC0-licensed audio track from archive.org and save to out_path.
        Returns True on success.
        """
        try:
            query = quote_plus('licenseurl:"https://creativecommons.org/publicdomain/zero/1.0/" AND mediatype:audio')
            url = f"https://archive.org/advancedsearch.php?q={query}&fl[]=identifier&sort[]=-downloads&output=json&rows=20"
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            results = r.json().get("response", {}).get("docs", [])
            for doc in results:
                identifier = doc.get("identifier")
                if not identifier:
                    continue
                meta_url = f"https://archive.org/metadata/{identifier}"
                mr = requests.get(meta_url, timeout=20)
                mr.raise_for_status()
                files = mr.json().get("files", [])
                candidates = [f for f in files if f.get("format") and f.get("format").lower() in ("mp3","ogg","m4a")]
                if not candidates:
                    continue
                cand = sorted(candidates, key=lambda x: x.get("size", 0), reverse=True)[0]
                file_name = cand.get("name")
                if not file_name:
                    continue
                download_url = f"https://archive.org/download/{identifier}/{file_name}"
                with requests.get(download_url, stream=True, timeout=60) as dr:
                    dr.raise_for_status()
                    with open(out_path, "wb") as fh:
                        for chunk in dr.iter_content(chunk_size=8192):
                            fh.write(chunk)
                return True
        except Exception as e:
            logger.warning(f"CC0 BGM fetch failed: {e}")
        return False

    def generate(self, script_data: dict) -> Path:
        """
        Generate a high‑quality video locally using:
          1) Edge TTS for narration
          2) Pexels for B-roll clips (per scene)
          3) ffmpeg for composition, fades, 1080p output
          4) Whisper for transcription -> subtitles

        Returns Path to the final MP4 file, or raises on error.
        """
        title = script_data.get("title", "video")
        narration = script_data.get("script") or ""
        if not narration.strip():
            raise ValueError("No narration text provided to video generator.")

        # Sanitize and truncate filename to avoid long path issues (especially with Japanese characters)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:30].strip()
        if not safe_title:
            safe_title = "video"
        outname = f"{safe_title}.mp4"
        final_path = self.videos_dir / outname

        with tempfile.TemporaryDirectory() as td:
            tdpath = Path(td)
            audio_path = tdpath / "narration.mp3"
            clips_dir = tdpath / "clips"
            clips_dir.mkdir()

            # 1) Synthesize narration
            self._synthesize_narration(narration, audio_path, voice=self.video_config.get("voice"))
            narration_sec = self._probe_duration(audio_path)
            target_video_sec = min(self.target_duration_sec, max(30, int(math.ceil(narration_sec))))

            # 2) Split narration into scenes
            scenes = _split_into_scenes(narration)
            if not scenes:
                scenes = [narration]


            # --- 動画時間に合わせて最適化 ---
            # max_scenesをさらに大きめに（例: 80）
            max_scenes = int(self.video_config.get("max_scenes", 80))
            if len(scenes) > max_scenes:
                step = len(scenes) / max_scenes
                selected_indices = [min(len(scenes) - 1, int(i * step)) for i in range(max_scenes)]
                scenes = [scenes[i] for i in selected_indices]

            # durationを合計がtarget_video_secに必ず一致するよう配分
            n = len(scenes)
            if n == 0:
                scenes = [narration]
                n = 1
            # 各シーンの単語数に応じて重み付け
            word_counts = [max(1, len(s.split())) for s in scenes]
            total_words = sum(word_counts)
            if total_words == 0:
                scene_durations = [target_video_sec // n for _ in range(n)]
                scene_durations[-1] += target_video_sec - sum(scene_durations)
            else:
                # 各シーンのdurationを単語数比率で配分
                raw_durations = [target_video_sec * wc / total_words for wc in word_counts]
                # 四捨五入して整数化、端数は最後のクリップに足す
                scene_durations = [int(round(d)) for d in raw_durations]
                diff = target_video_sec - sum(scene_durations)
                scene_durations[-1] += diff
                # 最低2秒保証
                for i in range(n):
                    if scene_durations[i] < 2:
                        scene_durations[i] = 2
                # 再度合計調整
                diff = target_video_sec - sum(scene_durations)
                scene_durations[-1] += diff

            clip_paths: List[Path] = []
            # 各シーンに最大3クリップを割り当てる
            max_clips_per_scene = 3
            for i, scene_text in enumerate(scenes):
                q = " ".join(scene_text.split()[:10]) or title
                scene_duration = scene_durations[i]
                per_clip_duration = max(2, scene_duration // max_clips_per_scene)
                got_count = 0
                for j in range(max_clips_per_scene):
                    clip_out = clips_dir / f"clip_{i:02d}_{j:02d}.mp4"
                    got = False
                    try:
                        got = self._download_pexels_clip(q, clip_out)
                    except Exception as e:
                        logger.warning(f"Failed to download Pexels clip for scene {i}-{j}: {e}")
                    if not got:
                        # プレースホルダー
                        clip_out = clips_dir / f"placeholder_{i:02d}_{j:02d}.mp4"
                        cmd = [
                            "ffmpeg",
                            "-y",
                            "-f",
                            "lavfi",
                            "-i",
                            "color=size=1920x1080:rate=25:color=black",
                            "-t",
                            str(per_clip_duration),
                            str(clip_out),
                        ]
                        logger.info(f"Creating placeholder clip: {' '.join(cmd)}")
                        subprocess_run(cmd)
                    clip_paths.append(clip_out)
                    got_count += 1
                    # シーンdurationを超えないように
                    if (got_count * per_clip_duration) >= scene_duration:
                        break

            # 3) Trim/scale each clip to target scene length and apply short fades

            processed = []
            processed_durations = []
            for i, cp in enumerate(clip_paths):
                proc = tdpath / f"proc_{i:02d}.mp4"
                duration = scene_durations[i]
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(cp),
                    "-vf",
                    "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p,fade=t=in:st=0:d=0.5,fade=t=out:st=" + str(max(0, duration - 0.6)) + ":d=0.5",
                    "-t",
                    str(duration),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "23",
                    str(proc),
                ]
                logger.info(f"Processing clip {i}: {' '.join(cmd[:6])}...")
                subprocess_run(cmd)
                processed.append(proc)
                processed_durations.append(duration)

            # ループせず、足りない場合はそのまま（映像が足りない場合はプレースホルダーが多くなる可能性あり）

            # 4) Concatenate processed clips
            concat_list = tdpath / "concat.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for p in processed:
                    f.write(f"file '{p.as_posix()}'\n")

            concat_out = tdpath / "concat.mp4"
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                str(concat_out),
            ]
            subprocess_run(cmd)

            # 5) Mix narration (and optional BGM) into final audio
            final_audio = tdpath / "final_audio.mp3"
            bg_url = self.video_config.get("background_music_url")
            bg_path = tdpath / "bg.mp3"
            if bg_url:
                try:
                    with requests.get(bg_url, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(bg_path, "wb") as fh:
                            shutil.copyfileobj(r.raw, fh)
                except Exception as e:
                    logger.warning(f"Failed to download BGM from config URL: {e}")

            if not bg_path.exists():
                got_bg = self._fetch_cc0_bgm(bg_path)
                if not got_bg:
                    logger.info("No BGM found; using narration only.")

            if bg_path.exists():
                # mix bg at approx -20dB relative to narration
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(audio_path),
                    "-i",
                    str(bg_path),
                    "-filter_complex",
                    "[1]volume=0.1[a1];[0][a1]amix=inputs=2:duration=longest",
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(final_audio),
                ]
                subprocess_run(cmd)
            else:
                shutil.copy(audio_path, final_audio)

            # 6) Transcribe narration to ASS (preferred) with improved styling
            ass_path = tdpath / "subs.ass"
            skip_whisper = os.getenv("SKIP_WHISPER", "0") == "1"
            if skip_whisper:
                logger.info("Skipping Whisper transcription (SKIP_WHISPER=1)")
                ass_path = None
            else:
                try:
                    self._generate_subtitles_ass(final_audio, ass_path)
                except Exception as e:
                    logger.warning(f"Whisper/ASS transcription failed: {e}; continuing without subtitles.")
                    ass_path = None

            # 7) Burn-in subtitles (if available) while muxing final audio and video
            if ass_path and ass_path.exists():
                # For ffmpeg subtitles filter on Windows, convert to forward slashes
                # Quote the path in the filter expression to handle colons and spaces
                normalized_ass = str(ass_path).replace('\\', '/')
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(concat_out),
                    "-i",
                    str(final_audio),
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    "-vf",
                    f"subtitles='{normalized_ass}'",
                    str(final_path),
                ]
            else:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(concat_out),
                    "-i",
                    str(final_audio),
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    str(final_path),
                ]

            subprocess_run(cmd)

        logger.info(f"Final video written to: {final_path}")
        return final_path


def subprocess_run(cmd: List[str]):
    logger.info("Running: %s", " ".join(cmd[:6]) + " ...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        logger.error("Command failed: %s\nSTDOUT: %s\nSTDERR: %s", " ".join(cmd), res.stdout.decode(errors='replace'), res.stderr.decode(errors='replace'))
        raise RuntimeError(f"Command failed: {cmd[0]}")
