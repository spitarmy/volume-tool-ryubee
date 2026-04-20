import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_live():
    # Login
    login_url = "https://ryubee-api-new.onrender.com/v1/auth/login"
    login_data = json.dumps({"email": "test@yamabun.com", "password": "password123"}).encode('utf-8')
    req = urllib.request.Request(login_url, data=login_data, headers={'Content-Type': 'application/json'})
    
    try:
        response = urllib.request.urlopen(req, context=ctx)
        data = json.loads(response.read().decode('utf-8'))
        token = data.get("token")
        print("Login OK")
    except Exception as e:
        print("Login failed:", e)
        return

    # Fetch Customers
    cust_url = "https://ryubee-api-new.onrender.com/v1/customers"
    req2 = urllib.request.Request(cust_url, headers={'Authorization': f'Bearer {token}'})
    
    try:
        res2 = urllib.request.urlopen(req2, context=ctx)
        customers = json.loads(res2.read().decode('utf-8'))
        print("Customers API OK, Count:", len(customers))
    except urllib.error.HTTPError as e:
        print("Customers HTTP Error:", e.code, e.read().decode('utf-8'))
    except Exception as e:
        print("Customers Exception:", e)

fetch_live()
