import os
import sys

# Ensure project root is on sys.path so `import app.*` works when running this script directly.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.rest_api.main import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5100"))
    debug = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)

