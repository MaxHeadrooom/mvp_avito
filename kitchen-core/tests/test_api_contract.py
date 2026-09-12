from app.main import app


def test_openapi_exposes_the_client_and_partner_contracts() -> None:
    paths = app.openapi()["paths"]

    assert "/client/orders" in paths
    assert "post" in paths["/client/orders"]
    assert "/establishments/{partner_id}" in paths
    assert "put" in paths["/establishments/{partner_id}"]
    assert "/establishments/{establishment_id}/products/external/{external_id}" in paths
    assert "put" in paths["/establishments/{establishment_id}/products/external/{external_id}"]


def test_order_contract_requires_a_delivery_address() -> None:
    schemas = app.openapi()["components"]["schemas"]
    assert "delivery_address" in schemas["OrderCreate"]["required"]

