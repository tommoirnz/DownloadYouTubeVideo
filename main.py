"""
YouTube Video Downloader - hardened version.

Fixes over the original:
  * Download runs on a worker thread, so the GUI never freezes.
  * Progress hook uses byte counts, not the fragile '_percent_str' string.
  * Format selector degrades gracefully when the requested height doesn't exist.
  * Detects missing ffmpeg and falls back to progressive (pre-muxed) streams.
  * Optional browser cookies for age-restricted / sign-in-required videos.
  * Windows-safe filenames and length-capped titles.

Requires:  pip install -U yt-dlp
Recommended: ffmpeg on PATH (winget install Gyan.FFmpeg)
"""

import os
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yt_dlp

QUALITIES = ["144", "240", "360", "480", "720", "1080", "1440", "2160"]
BROWSERS = ["none", "chrome", "firefox", "edge", "brave", "opera", "vivaldi"]


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.worker = None
        self.cancel_flag = threading.Event()
        self.has_ffmpeg = shutil.which("ffmpeg") is not None

        self._build_ui()
        self.root.after(100, self._pump_events)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        r = self.root
        r.title("YouTube Video Downloader")
        r.geometry("560x420")
        r.config(bg="#2E8BC0")

        label_kw = dict(bg="#2E8BC0", fg="white", font=("Helvetica", 11))

        tk.Label(r, text="Video URL:", **label_kw).pack(pady=(14, 4))
        self.url_entry = tk.Entry(r, width=58, font=("Helvetica", 11),
                                  bd=2, relief="sunken")
        self.url_entry.pack(pady=4)

        row = tk.Frame(r, bg="#2E8BC0")
        row.pack(pady=10)

        tk.Label(row, text="Max height (p):", **label_kw).grid(row=0, column=0, padx=6)
        self.quality_var = tk.StringVar(r, value="1080")
        tk.OptionMenu(row, self.quality_var, *QUALITIES).grid(row=0, column=1, padx=6)

        tk.Label(row, text="Cookies from:", **label_kw).grid(row=0, column=2, padx=6)
        self.browser_var = tk.StringVar(r, value="none")
        tk.OptionMenu(row, self.browser_var, *BROWSERS).grid(row=0, column=3, padx=6)

        self.audio_only = tk.BooleanVar(r, value=False)
        tk.Checkbutton(r, text="Audio only (m4a)", variable=self.audio_only,
                       bg="#2E8BC0", fg="white", selectcolor="#2E8BC0",
                       activebackground="#2E8BC0", font=("Helvetica", 10)).pack()

        self.download_button = tk.Button(
            r, text="Download", command=self.start_download,
            bg="#F18F01", fg="white", font=("Helvetica", 12, "bold"),
            relief="raised", bd=3, width=16)
        self.download_button.pack(pady=14)

        self.progress = ttk.Progressbar(r, orient=tk.HORIZONTAL,
                                        length=480, mode="determinate")
        self.progress.pack(pady=6)

        self.status_var = tk.StringVar(r, value="Idle")
        tk.Label(r, textvariable=self.status_var, bg="#2E8BC0", fg="white",
                 font=("Helvetica", 9), wraplength=520,
                 justify="left").pack(pady=6)

        if not self.has_ffmpeg:
            self.status_var.set(
                "ffmpeg not found on PATH - limited to pre-muxed streams "
                "(usually 360p/720p max). Install ffmpeg for full quality.")

    # ------------------------------------------------- thread-safe plumbing

    def _pump_events(self):
        """Drain worker messages on the main thread. Tkinter is not thread-safe."""
        try:
            while True:
                kind, payload = self.events.get_nowait()

                if kind == "progress":
                    if self.progress["mode"] != "determinate":
                        self.progress.stop()
                        self.progress.config(mode="determinate")
                    self.progress["value"] = payload

                elif kind == "pulse":
                    if self.progress["mode"] != "indeterminate":
                        self.progress.config(mode="indeterminate")
                        self.progress.start(12)

                elif kind == "status":
                    self.status_var.set(payload)

                elif kind == "done":
                    self.progress.stop()
                    self.progress.config(mode="determinate")
                    self.progress["value"] = 100
                    self.download_button.config(state=tk.NORMAL, text="Download")
                    self.status_var.set("Finished")
                    messagebox.showinfo("Success", f"Saved to:\n{payload}")

                elif kind == "error":
                    self.progress.stop()
                    self.progress.config(mode="determinate")
                    self.progress["value"] = 0
                    self.download_button.config(state=tk.NORMAL, text="Download")
                    self.status_var.set("Failed")
                    messagebox.showerror("Error", payload)

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._pump_events)

    def _hook(self, d):
        status = d.get("status")

        if status == "downloading":
            done = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                self.events.put(("progress", done / total * 100.0))
            else:
                # Live streams and some HLS manifests report no size at all.
                self.events.put(("pulse", None))

            speed = d.get("speed")
            speed_txt = f"{speed / 1e6:.1f} MB/s" if speed else "-"
            self.events.put(("status", f"Downloading... {speed_txt}"))

        elif status == "finished":
            self.events.put(("progress", 100.0))
            self.events.put(("status", "Merging / post-processing..."))

    # -------------------------------------------------------------- options

    def _build_opts(self, download_path):
        height = self.quality_var.get()

        if self.audio_only.get():
            fmt = "bestaudio[ext=m4a]/bestaudio/best"
        elif self.has_ffmpeg:
            # '<=?' makes the height a *preference*, not a hard requirement,
            # so a video whose only stream is 240p still downloads.
            fmt = (
                f"bestvideo[height<=?{height}]+bestaudio/"
                f"best[height<=?{height}]/"
                f"best"
            )
        else:
            # No muxer available: only formats that already contain both tracks.
            fmt = f"best[height<=?{height}][acodec!=none][vcodec!=none]/best"

        opts = {
            "format": fmt,
            "outtmpl": os.path.join(download_path, "%(title).150B [%(id)s].%(ext)s"),
            "progress_hooks": [self._hook],
            "windowsfilenames": True,
            "noplaylist": True,  # a URL with &list= won't grab 200 videos
            "retries": 10,
            "fragment_retries": 10,
            "concurrent_fragment_downloads": 4,
            "continuedl": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }

        if self.has_ffmpeg and not self.audio_only.get():
            opts["merge_output_format"] = "mp4"

        browser = self.browser_var.get()
        if browser != "none":
            opts["cookiesfrombrowser"] = (browser,)

        return opts

    # --------------------------------------------------------------- worker

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a video URL first.")
            return

        download_path = filedialog.askdirectory(title="Save video to...")
        if not download_path:
            return

        self.download_button.config(state=tk.DISABLED, text="Working...")
        self.progress["value"] = 0
        self.status_var.set("Resolving formats...")

        self.worker = threading.Thread(
            target=self._run, args=(url, download_path), daemon=True)
        self.worker.start()

    def _run(self, url, download_path):
        try:
            opts = self._build_opts(download_path)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.events.put(("done", download_path))

        except yt_dlp.utils.DownloadError as e:
            self.events.put(("error", self._explain(str(e))))
        except Exception as e:
            self.events.put(("error", f"{type(e).__name__}: {e}"))

    @staticmethod
    def _explain(msg):
        """Turn common yt-dlp failures into something actionable."""
        low = msg.lower()
        hints = []
        if "sign in" in low or "bot" in low or "age" in low or "confirm" in low:
            hints.append("Age-restricted or bot-checked. Set 'Cookies from' to a "
                         "browser you're logged into on this machine.")
        if "ffmpeg" in low or "postprocess" in low:
            hints.append("ffmpeg is required to merge separate video+audio "
                         "streams. Install it and make sure it's on PATH.")
        if "requested format" in low or "no video formats" in low:
            hints.append("No stream matched. Try a different max height, or the "
                         "video may be live/DRM-protected.")
        if "unable to extract" in low or "nsig" in low or "player" in low:
            hints.append("Extractor is out of date. Run: pip install -U yt-dlp")
        if "private" in low or "unavailable" in low or "removed" in low:
            hints.append("Video is private, deleted, or region-blocked.")

        return msg if not hints else msg + "\n\n" + "\n\n".join(hints)


if __name__ == "__main__":
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()
