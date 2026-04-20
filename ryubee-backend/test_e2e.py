import httpx

def run_test():
    base = "http://localhost:8000"
    with httpx.Client(base_url=base) as client:
        # Register or Login
        resp = client.post("/v1/auth/register", json={
            "company_name": "Test E2E Co",
            "email": "test_e2e@example.com",
            "password": "password123",
            "name": "Test User E2E"
        })
        
        if resp.status_code == 400: # User already exists
            print("User exists, trying login...")
            # We must use proper payload for /v1/auth/login.
            # In api.js we saw `email` and `password` but let's see what backend wants.
            resp = client.post("/v1/auth/login", json={
                "email": "test_e2e@example.com",
                "password": "password123"
            })
            
        print("Auth Body:", resp.text)
        data = resp.json()
        token = data.get("token")
        if not token:
            print("Auth Failed:", data)
            return
            
        print("Auth Success!")
        client.headers.update({"Authorization": f"Bearer {token}"})

        # Update Settings
        resp = client.put("/v1/settings", json={"base_price_m3": 18000})
        print("Update Settings:", resp.status_code)

        # Create Job
        resp = client.post("/v1/jobs", json={
            "job_name": "Test Job E2E",
            "customer_name": "E2E Customer",
            "price_total": 36000,
            "total_volume_m3": 2.0
        })
        print("Create Job:", resp.status_code)

        # Get Jobs
        resp = client.get("/v1/jobs")
        jobs = resp.json()
        print("Get Jobs:", len(jobs), "jobs found. Latest:", jobs[0].get("job_name"))

        # Get Admin Summary
        resp = client.get("/v1/admin/summary")
        print("Admin Summary:", resp.json())

if __name__ == "__main__":
    run_test()
