from fastapi.testclient import TestClient
from app.main import app
import sys

client = TestClient(app)

login_data = {
    "email": "test@yamabun.com",
    "password": "password123"
}
res = client.post("/v1/auth/login", json=login_data)
if res.status_code != 200:
    print("Login failed:", res.text)
    sys.exit(1)

token = res.json().get("token")
print("Login ok")

# get an invoice for testing, by calling the API
res = client.get("/v1/invoices", headers={"Authorization": f"Bearer {token}"})
if res.status_code != 200 or not res.json():
    print("Failed to get invoices:", res.text)
    sys.exit(1)

invoice_id = res.json()[0]["id"]
print("Using invoice ID:", invoice_id)

try:
    send_res = client.post(f"/v1/invoices/{invoice_id}/send", json={"subject": "Test", "body": "Body"}, headers={"Authorization": f"Bearer {token}"})
    print("Status:", send_res.status_code)
    print("Response:", send_res.text)
except Exception as e:
    import traceback
    traceback.print_exc()

