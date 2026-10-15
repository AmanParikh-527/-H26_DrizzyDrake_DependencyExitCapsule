#!/usr/bin/env python3
"""
app.py - Lightweight production server for DigitalOcean App Platform and Droplet deployment.

Features:
  - Serves interactive visual report (capsule_output/report.html) at '/'
  - Serves machine-readable artifacts (/capsule.json, /capsule.md, /intermediate/*)
  - Provides '/health' endpoint for DigitalOcean App Platform health checks
  - Zero external web framework dependencies (stdlib http.server)
"""

from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
import socketserver
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "capsule_output"
PORT = int(os.environ.get("PORT", 8080))


class CapsuleHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler serving reports and health status."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)

    def do_GET(self) -> None:
        # DigitalOcean health check endpoint
        if self.path in ("/health", "/healthz", "/ping"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            payload = {
                "status": "healthy",
                "service": "dependency-exit-capsule",
                "capsule_available": (OUTPUT_DIR / "capsule.json").exists(),
                "report_available": (OUTPUT_DIR / "report.html").exists(),
            }
            self.wfile.write(json.dumps(payload, indent=2).encode("utf-8"))
            return

        # Default root serves report.html if available
        if self.path in ("/", "/index.html"):
            report_file = OUTPUT_DIR / "report.html"
            if report_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(report_file.read_bytes())
                return
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = """<!doctype html><html><head><title>Dependency Exit Capsule</title>
<style>body{font-family:sans-serif;margin:40px;background:#0d1117;color:#c9d1d9;}
h1{color:#58a6ff;}code{background:#161b22;padding:4px 8px;border-radius:4px;}
</style></head><body><h1>Dependency Exit Capsule</h1>
<p>No report has been generated yet.</p>
<p>Run the pipeline against your target repository to generate the capsule:</p>
<pre><code>python dependency-exit-capsule/scripts/run_pipeline.py --repo dependency-exit-capsule/target/LinkWatch --dependency Jinja2</code></pre>
</body></html>"""
                self.wfile.write(html.encode("utf-8"))
                return

        super().do_GET()

    def log_message(self, format: str, *args) -> None:
        # Standard format logging
        sys.stdout.write(f"[{self.log_date_time_string()}] {format % args}\n")
        sys.stdout.flush()


def run_server(port: int = PORT) -> None:
    """Start the HTTP server on the specified port."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with socketserver.TCPServer(("", port), CapsuleHTTPHandler) as httpd:
        print("=" * 60)
        print("Dependency Exit Capsule - DigitalOcean Server")
        print("=" * 60)
        print(f"Listening on port: http://0.0.0.0:{port}")
        print(f"Serving directory: {OUTPUT_DIR}")
        print(f"Health check:      http://0.0.0.0:{port}/health")
        print("=" * 60)
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


def main() -> None:
    parser = argparse.ArgumentParser(description="DigitalOcean App server for Dependency Exit Capsule.")
    parser.add_argument("--port", type=int, default=PORT, help=f"HTTP port (default: {PORT})")
    parser.add_argument("--run", action="store_true", help="Run the pipeline once before starting the server")
    parser.add_argument("--repo", default="dependency-exit-capsule/target/LinkWatch", help="Target repository path")
    parser.add_argument("--dependency", default="Jinja2", help="Dependency to analyze")
    args = parser.parse_args()

    if args.run:
        pipeline_script = BASE_DIR / "dependency-exit-capsule" / "scripts" / "run_pipeline.py"
        print(f"Executing pipeline on {args.repo} for {args.dependency}...")
        cmd = [sys.executable, str(pipeline_script), "--repo", args.repo, "--dependency", args.dependency, "--output", str(OUTPUT_DIR)]
        subprocess.run(cmd, check=False)

    run_server(args.port)


if __name__ == "__main__":
    main()
