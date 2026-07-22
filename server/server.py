#!/usr/bin/env python3
"""HTTP API server for the IT8951 e-paper display.

Endpoints:
  GET  /                  — health check + device info
  GET  /info              — device info (panel size, FW, LUT, VCOM)
  POST /text              — display text (JSON: {"text": "...", "font_size": 48})
  POST /image             — display image (multipart upload, auto-scaled)
  POST /clear             — clear screen to white
  POST /raw               — display raw 4bpp data (JSON base64, advanced)

Run:
  sudo python3 server.py --host 0.0.0.0 --port 8888
"""
import argparse, json, base64, time, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler

# it8951_driver is in the parent directory
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from it8951_driver import IT8951, GC16_MODE, INIT_MODE

# Global display instance
_epd = None


def get_epd():
    global _epd
    if _epd is None:
        _epd = IT8951()
        _epd.init()
    return _epd


class EPDHandler(BaseHTTPRequestHandler):
    def _send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length > 0 else b""

    def log_message(self, fmt, *args):
        print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % args))

    def do_GET(self):
        if self.path in ("/", "/info"):
            try:
                epd = get_epd()
                info = epd.get_info()
                info["vcom"] = epd.get_vcom()
                self._send_json(200, {"ok": True, "device": info})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        try:
            if self.path == "/text":
                self._handle_text()
            elif self.path == "/image":
                self._handle_image()
            elif self.path == "/clear":
                self._handle_clear()
            elif self.path == "/raw":
                self._handle_raw()
            else:
                self._send_json(404, {"ok": False, "error": "not found"})
        except Exception as e:
            traceback.print_exc()
            self._send_json(500, {"ok": False, "error": str(e)})

    def _handle_text(self):
        body = self._read_body()
        params = json.loads(body)
        text = params.get("text", "")
        font_size = params.get("font_size", 48)
        font_path = params.get("font_path")
        bg = params.get("bg_color", 255)
        fg = params.get("fg_color", 0)

        if not text:
            self._send_json(400, {"ok": False, "error": "text is required"})
            return

        epd = get_epd()
        epd.display_text(text, font_size=font_size, font_path=font_path,
                         bg_color=bg, fg_color=fg)
        self._send_json(200, {"ok": True, "displayed": text[:100]})

    def _handle_image(self):
        ct = self.headers.get("Content-Type", "")
        if "multipart/form-data" in ct:
            # Parse multipart upload
            body = self._read_body()
            image_data = self._parse_multipart(body, ct)
        else:
            # Raw image bytes
            image_data = self._read_body()

        if not image_data:
            self._send_json(400, {"ok": False, "error": "no image data"})
            return

        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_data))

        epd = get_epd()
        epd.display_image(img)
        self._send_json(200, {"ok": True, "size": img.size, "scaled_to": [epd.panel_w, epd.panel_h]})

    def _handle_clear(self):
        epd = get_epd()
        epd.clear()
        self._send_json(200, {"ok": True})

    def _handle_raw(self):
        body = self._read_body()
        params = json.loads(body)
        data_b64 = params.get("data", "")
        w = params.get("w")
        h = params.get("h")
        mode = params.get("mode", GC16_MODE)

        img_bytes = base64.b64decode(data_b64)
        epd = get_epd()
        epd.display_4bpp(list(img_bytes), w=w, h=h, mode=mode)
        self._send_json(200, {"ok": True, "bytes": len(img_bytes)})

    def _parse_multipart(self, body, content_type):
        """Extract file data from multipart/form-data."""
        # Find boundary
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):].strip('"')
                break
        if not boundary:
            return None

        boundary_bytes = ("--" + boundary).encode()
        parts = body.split(boundary_bytes)
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            # Find header/body separator
            sep = part.find(b"\r\n\r\n")
            if sep < 0:
                continue
            file_data = part[sep + 4:]
            # Strip trailing \r\n
            if file_data.endswith(b"\r\n"):
                file_data = file_data[:-2]
            return file_data
        return None


def main():
    parser = argparse.ArgumentParser(description="IT8951 e-paper API server")
    parser.add_argument("--host", default="0.0.0.0", help="bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8888, help="port (default: 8888)")
    args = parser.parse_args()

    print("IT8951 e-paper API server starting on %s:%d" % (args.host, args.port))
    server = HTTPServer((args.host, args.port), EPDHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        if _epd:
            _epd.clear()
            _epd.close()
        server.server_close()


if __name__ == "__main__":
    main()