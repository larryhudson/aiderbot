import pytest
from flask import Flask
from app import create_app  # Assuming your main Flask app is in app.py

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home_page(client):
    """Test that the home page loads correctly"""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Welcome to the Flask App" in response.data

def test_factorial_calculation(client):
    """Test the factorial calculation endpoint"""
    response = client.get('/factorial/5')
    assert response.status_code == 200
    assert b"120" in response.data  # 5! = 120

def test_invalid_factorial_input(client):
    """Test the factorial calculation with invalid input"""
    response = client.get('/factorial/-1')
    assert response.status_code == 400
    assert b"Invalid input" in response.data

# Add more tests as needed for other core functionalities
