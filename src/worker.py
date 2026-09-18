from nexusmind.cloud.app import app
from workers import asgi

Default = asgi.entrypoint(app)
