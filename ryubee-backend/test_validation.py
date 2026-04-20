from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print(client.get("/v1/health").json())
