"""
Unit tests for the supermusic.web.app FastAPI application.
"""

import pytest
from fastapi.testclient import TestClient
from web.app import app

# Create a test client for the FastAPI app
client = TestClient(app)

def test_index_route_returns_200():
    """
    Check that the index route ("/") returns HTTP 200.
    """
    response = client.get("/")
    assert response.status_code == 200

def test_index_contains_title():
    """
    Check that the index route contains the SuperMusic title in the HTML.
    """
    response = client.get("/")
    assert "SuperMusic" in response.text
