from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.models import User
from app import auth
from sqlalchemy.orm import Session

client = TestClient(app)

# Override auth dependency to simulate our test user
def override_get_current_user():
    db = next(get_db())
    # find test user
    user = db.query(User).filter(User.email == "test@yamabun.com").first()
    return user

app.dependency_overrides[auth.get_current_user] = override_get_current_user

response = client.get("/v1/customers")
print("Status Code:", response.status_code)
if response.status_code != 200:
    print("Error:", response.json())
else:
    print("Success. Found", len(response.json()), "customers")

app.dependency_overrides.clear()
