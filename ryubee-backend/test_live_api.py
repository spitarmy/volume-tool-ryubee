import requests

login_data = {
    "email": "test@yamabun.com",
    "password": "password123"
}
login_res = requests.post("https://ryubee-api-new.onrender.com/v1/auth/login", json=login_data)
if login_res.status_code != 200:
    print("Login failed:", login_res.text)
    exit(1)

token = login_res.json().get("token")
print("Login successful.")

cust_res = requests.get("https://ryubee-api-new.onrender.com/v1/customers", headers={"Authorization": f"Bearer {token}"})
print("Customers API status:", cust_res.status_code)
if cust_res.status_code != 200:
    print("Error:", cust_res.text)
else:
    docs = cust_res.json()
    print("Fetched", len(docs), "customers.")
