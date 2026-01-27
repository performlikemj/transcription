"""
Download the Parakeet ASR model from Hugging Face with resume support.
"""

import os
import threading
import time
import logging
import urllib.request
import urllib.error
from pathlib import Path
from PyObjCTools import AppHelper

DOWNLOAD_URL = (
    "https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/resolve/main/"
    "parakeet-tdt-0.6b-v3.nemo"
)
MODEL_FILENAME = "parakeet-tdt-0.6b-v3.nemo"
PART_SUFFIX = ".part"
CHUNK_SIZE = 1024 * 1024  # 1 MB
REQUIRED_FREE_SPACE = 3 * 1024 * 1024 * 1024  # 3 GB
PROGRESS_THROTTLE = 0.25  # seconds between UI updates


class ModelDownloader:
    """Downloads the Parakeet model in a background thread with resume support."""

    def __init__(self, dest_dir, on_progress=None, on_complete=None, on_error=None):
        """
        Args:
            dest_dir: Path to directory where model will be saved.
            on_progress: callback(bytes_downloaded, total_bytes, speed_bps)
            on_complete: callback(model_path)
            on_error: callback(error_msg)
        """
        self._dest_dir = Path(dest_dir)
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._cancel_event = threading.Event()
        self._thread = None

    @property
    def model_path(self):
        return self._dest_dir / MODEL_FILENAME

    @property
    def part_path(self):
        return self._dest_dir / (MODEL_FILENAME + PART_SUFFIX)

    def start(self):
        """Start the download in a background thread."""
        self._cancel_event.clear()
        self._thread = threading.Thread(target=self._download, daemon=True)
        self._thread.start()

    def cancel(self):
        """Signal the download to stop. The .part file is preserved for resume."""
        self._cancel_event.set()

    def _dispatch_progress(self, downloaded, total, speed):
        if self._on_progress:
            AppHelper.callAfter(self._on_progress, downloaded, total, speed)

    def _dispatch_complete(self, path):
        if self._on_complete:
            AppHelper.callAfter(self._on_complete, str(path))

    def _dispatch_error(self, msg):
        if self._on_error:
            AppHelper.callAfter(self._on_error, msg)

    def _check_disk_space(self):
        """Return True if enough disk space is available."""
        stat = os.statvfs(str(self._dest_dir))
        free = stat.f_bavail * stat.f_frsize
        return free >= REQUIRED_FREE_SPACE

    def _download(self):
        try:
            self._dest_dir.mkdir(parents=True, exist_ok=True)

            if not self._check_disk_space():
                self._dispatch_error(
                    "Not enough disk space. At least 3 GB free is required."
                )
                return

            part = self.part_path
            existing_size = part.stat().st_size if part.exists() else 0

            # Build request with optional Range header for resume
            req = urllib.request.Request(DOWNLOAD_URL)
            if existing_size > 0:
                req.add_header("Range", f"bytes={existing_size}-")
                logging.info(
                    "MODEL_DL: Resuming download from byte %d", existing_size
                )

            try:
                resp = urllib.request.urlopen(req, timeout=30)
            except urllib.error.HTTPError as e:
                if e.code == 416:
                    # Range not satisfiable — file already complete
                    logging.info("MODEL_DL: File already fully downloaded")
                    part.rename(self.model_path)
                    self._dispatch_complete(self.model_path)
                    return
                raise

            # Determine total size
            content_length = resp.getheader("Content-Length")
            status_code = resp.getcode()
            if status_code == 206:
                # Partial content — resumed
                total_bytes = existing_size + (
                    int(content_length) if content_length else 0
                )
            else:
                # Full download (server may not support Range)
                total_bytes = int(content_length) if content_length else 0
                existing_size = 0  # start fresh

            downloaded = existing_size
            last_ui_update = 0.0
            speed_window_start = time.monotonic()
            speed_window_bytes = 0

            mode = "ab" if existing_size > 0 and status_code == 206 else "wb"
            with open(part, mode) as f:
                while True:
                    if self._cancel_event.is_set():
                        logging.info("MODEL_DL: Download cancelled")
                        resp.close()
                        return

                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)
                    speed_window_bytes += len(chunk)

                    now = time.monotonic()
                    elapsed = now - speed_window_start
                    if elapsed > 0:
                        speed_bps = speed_window_bytes / elapsed
                    else:
                        speed_bps = 0

                    # Reset speed window every 2 seconds for responsive average
                    if elapsed >= 2.0:
                        speed_window_start = now
                        speed_window_bytes = 0

                    # Throttle UI updates
                    if now - last_ui_update >= PROGRESS_THROTTLE:
                        last_ui_update = now
                        self._dispatch_progress(downloaded, total_bytes, speed_bps)

            resp.close()

            # Final progress update
            self._dispatch_progress(downloaded, total_bytes, 0)

            # Rename .part → final
            if self.model_path.exists():
                self.model_path.unlink()
            part.rename(self.model_path)
            logging.info("MODEL_DL: Download complete: %s", self.model_path)
            self._dispatch_complete(self.model_path)

        except Exception as e:
            logging.error("MODEL_DL: Download error: %s", e)
            self._dispatch_error(str(e))
