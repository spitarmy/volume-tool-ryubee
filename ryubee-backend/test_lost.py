import httpx

def run_test():
    base = "http://localhost:8000"
    with httpx.Client(base_url=base) as client:
        # Login
        resp = client.post("/v1/auth/login", json={
            "email": "test_e2e@example.com",
            "password": "password123"
        })
            
        data = resp.json()
        token = data.get("token")
        if not token:
            print("Auth Failed:", data)
            return
            
        print("Auth Success!")
        client.headers.update({"Authorization": f"Bearer {token}"})

        # Create Normal Job
        resp1 = client.post("/v1/jobs", json={
            "job_name": "Normal Job",
            "customer_name": "Customer 1",
            "price_total": 40000,
            "status": "pending"
        })
        print("Create Normal:", resp1.status_code)

        # Create Lost Job
        resp2 = client.post("/v1/jobs", json={
            "job_name": "Lost Job",
            "customer_name": "Customer 2",
            "price_total": 100000,
            "status": "lost"
        })
        print("Create Lost:", resp2.status_code)

        # Get Admin Summary
        resp = client.get("/v1/admin/summary")
        summary = resp.json()
        print("Admin Summary:")
        print("Total Month Sales (should exclude the 100k):", summary.get("month_sales"))
        print("Total Job Count:", summary.get("month_jobs"))
        
        # Get Admin Chart
        resp = client.get("/v1/admin/sales-chart")
        chart = resp.json()
        print("Today's chart sale (should exclude the 100k):", chart[-1].get("sales"))

if __name__ == "__main__":
    run_test()
