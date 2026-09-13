"""Create or update the demo restaurant and its menu through the partner API."""

import json
import os
import time

import httpx

CORE_BASE_URL = os.environ.get("CORE_BASE_URL", "http://kitchen-core:8000")
SEED_FILE = "/app/establishment_id.json"
PARTNER_ID = "mario-demo"
PARTNER_API_KEY = os.environ.get("PARTNER_API_KEY", "demo-mario-partner-key-0001")


def wait_for_core() -> None:
    for _ in range(30):
        try:
            if httpx.get(f"{CORE_BASE_URL}/health", timeout=2.0).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("kitchen-core is not reachable")


def main() -> None:
    wait_for_core()
    establishment_response = httpx.put(
        f"{CORE_BASE_URL}/establishments/{PARTNER_ID}",
        json={
            "name": "Пиццерия Марио",
            "description": "Демонстрационное заведение для тестового задания",
            "callback_url": "http://establishment-service:8001",
            "partner_api_key": PARTNER_API_KEY,
            "status": "open",
        },
        timeout=5.0,
    )
    establishment_response.raise_for_status()
    establishment_id = establishment_response.json()["id"]

    menu = [
        {
            "external_id": "margarita",
            "name": "Маргарита",
            "price": "590.00",
            "stock": 20,
            "is_available": True,
        },
        {
            "external_id": "pepperoni",
            "name": "Пепперони",
            "price": "690.00",
            "stock": 15,
            "is_available": True,
        },
        {
            "external_id": "cola-05",
            "name": "Кола 0.5",
            "price": "150.00",
            "stock": 0,
            "is_available": True,
        },
    ]
    for product in menu:
        external_id = product.pop("external_id")
        response = httpx.put(
            f"{CORE_BASE_URL}/establishments/{establishment_id}/products/external/{external_id}",
            json=product,
            timeout=5.0,
        )
        response.raise_for_status()

    with open(SEED_FILE, "w", encoding="utf-8") as file:
        json.dump({"establishment_id": establishment_id}, file)
    print(f"Seeded establishment_id={establishment_id}")


if __name__ == "__main__":
    main()