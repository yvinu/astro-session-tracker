"""HTTP access to the library service, using only the standard library.

Kept behind a small class so the commands can be driven by a stand-in
in tests, and so nothing else in the CLI builds URLs or headers.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class ApiError(Exception):
    def __init__(self, status, detail):
        super().__init__(f"{detail} (HTTP {status})" if status else detail)
        self.status = status
        self.detail = detail


class Api:
    def __init__(self, server, token):
        self.server = server.rstrip("/")
        self.token = token

    def _send(self, method, path, data=None, headers=None, timeout=60):
        request = urllib.request.Request(self.server + path, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode() or "null")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                detail = json.loads(body).get("detail", body)
            except (ValueError, AttributeError):
                detail = body
            raise ApiError(e.code, detail)
        except urllib.error.URLError as e:
            raise ApiError(None, f"Cannot reach {self.server}: {e.reason}")

    def get_json(self, path):
        return self._send("GET", path)

    def post_json(self, path, body):
        return self._send("POST", path, json.dumps(body).encode(), {"Content-Type": "application/json"})

    def put_file(self, path, params, file_path):
        """Upload one file as the request body, streamed from disk."""
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        with open(file_path, "rb") as f:
            headers = {"Content-Type": "application/octet-stream", "Content-Length": str(os.path.getsize(file_path))}
            return self._send("PUT", f"{path}?{query}", f, headers, timeout=3600)
