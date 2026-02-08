from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

_HTML = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Hello</title>
  </head>
  <body>
    <h1>Hello World</h1>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    # UI route
    return _HTML


@app.get("/api/hello", response_class=HTMLResponse)
def api_hello() -> str:
    # API route (useful if you want to call it with token auth).
    return _HTML


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/sample")
def sample() -> dict:
    return {
        "status": "ok",
        "message": "Hello from API sample",
        "path": "/api/sample",
    }
