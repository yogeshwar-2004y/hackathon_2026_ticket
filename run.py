import os
import sys

# Ensure project root is on sys.path so `import app.*` works when running this script directly.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.rest_api.main import create_app

app = create_app()

if __name__ == "__main__":
    # Development server; for production use a WSGI server
    # Allow overriding port via environment variable to avoid conflicts.
    port = int(os.getenv("PORT", "5100"))
    # Disable the reloader to avoid spawning a second process which would
    # also start background threads (causing duplicate workers and port conflicts).
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)

