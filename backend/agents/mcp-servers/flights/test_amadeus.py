"""
Test Script for Amadeus Client
Simple script to test if Amadeus API is working
"""

import os
from dotenv import load_dotenv
from amadeus_client import AmadeusFlightClient

# Load environment
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path)

# Get credentials
api_key = os.getenv('AMADEUS_API_KEY')
api_secret = os.getenv('AMADEUS_API_SECRET')

print("Testing Amadeus Flight Search...")
print(f"API Key: {api_key[:10]}... (hidden)")
print()

# Create client
client = AmadeusFlightClient(api_key, api_secret)

# Test search
print("Searching for flights: SFO → BCN on 2025-12-15")
try:
    flights = client.search_flights(
        origin="JFK",
        destination="LAX",
        departure_date="2025-12-01",
        return_date="2025-12-08",
        adults=1,
        max_results=3
    )
    
    print(f"\n✅ Success! Found {len(flights)} flights:")
    for i, flight in enumerate(flights, 1):
        print(f"\n--- Flight {i} ---")
        print(f"Price: ${flight['price']} {flight['currency']}")
        print(f"Outbound: {flight['outbound']['airline']} {flight['outbound']['flight']}")
        print(f"  {flight['outbound']['from']} → {flight['outbound']['to']}")
        print(f"  Stops: {flight['outbound']['stops']}")
        if flight.get('return'):
            print(f"Return: {flight['return']['airline']} {flight['return']['flight']}")
            print(f"  {flight['return']['from']} → {flight['return']['to']}")
            print(f"  Stops: {flight['return']['stops']}")
    
except Exception as e:
    print(f"\n❌ Error occurred")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")
    
    # If it's a ResponseError from Amadeus, print more details
    if hasattr(e, 'response'):
        print(f"\nAmadeus Response Details:")
        print(f"Status Code: {e.response.status_code if hasattr(e.response, 'status_code') else 'N/A'}")
        print(f"Response Body: {e.response.body if hasattr(e.response, 'body') else 'N/A'}")
    
    # Print the full exception for debugging
    import traceback
    print(f"\nFull traceback:")
    traceback.print_exc()
  