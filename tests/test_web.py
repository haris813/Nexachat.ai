def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"NexaChat AI" in response.data
