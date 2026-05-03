import requests

login_data = {
    "email": "koji.yamabun@outlook.jp",
    "password": "koji0321"
}
login_res = requests.post("https://ryubee-api-v2.onrender.com/v1/auth/login", json=login_data)
if login_res.status_code != 200:
    print("Login failed:", login_res.text)
    exit(1)

token = login_res.json()["token"]
print("Login successful")

invoice_id = "2dc490b1-25d8-4e40-a520-081f9a3926c5"
send_data = {
    "subject": "Test",
    "body": "Test body"
}
res = requests.post(
    f"https://ryubee-api-v2.onrender.com/v1/invoices/{invoice_id}/send",
    json=send_data,
    headers={"Authorization": f"Bearer {token}"}
)
print("Status:", res.status_code)
print("Response:", res.text)
