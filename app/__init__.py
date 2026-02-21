from flask import Flask

def create_app():
    app = Flask(__name__)

    # Import submodules (registers routes, starts background workers)
    from . import main  # noqa: F401

    return app

