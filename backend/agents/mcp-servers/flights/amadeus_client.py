"""
Amadeus API Client with SSL Configuration
==========================================
Handles all communication with the Amadeus Flight API.
Includes SSL certificate verification fix.
"""

import os
import ssl
import certifi
from amadeus import Client, ResponseError
from typing import Dict, List, Optional
from datetime import datetime


class AmadeusFlightClient:
    """
    Wrapper for Amadeus Flight API with SSL certificate handling
    """
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize Amadeus client with SSL configuration
        
        SSL Fix: Creates SSL context using certifi's certificate bundle
        to prevent SSL certificate verification errors
        """
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Configure SSL context to use certifi's certificate bundle
        # This fixes: SSL: CERTIFICATE_VERIFY_FAILED errors
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        # Create Amadeus client with SSL configuration
        self.client = Client(
            client_id=api_key,
            client_secret=api_secret,
            hostname='test',
            ssl=ssl_context  # Add SSL context to client
        )
        
        print("[AmadeusClient] ✅ Initialized successfully")
    
    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        max_results: int = 5
    ) -> List[Dict]:
        """
        Search for flights via Amadeus API
        
        Args:
            origin: Origin airport code (e.g., "SFO")
            destination: Destination airport code (e.g., "BCN")
            departure_date: Departure date (YYYY-MM-DD)
            return_date: Return date (YYYY-MM-DD), optional
            adults: Number of adult passengers
            max_results: Maximum number of results to return
            
        Returns:
            List of flight dictionaries with structured data
        """
        try:
            print(f"[AmadeusClient] Searching flights: {origin} → {destination} on {departure_date}")
            
            # Build API request parameters
            search_params = {
                'originLocationCode': origin.upper(),
                'destinationLocationCode': destination.upper(),
                'departureDate': departure_date,
                'adults': adults,
                'max': max_results,
                'currencyCode': 'USD'
            }
            
            # Add return date if provided (round trip)
            if return_date:
                search_params['returnDate'] = return_date
            
            # Call Amadeus API
            response = self.client.shopping.flight_offers_search.get(**search_params)
            
            # Extract and format flight offers
            flight_offers = response.data
            print(f"[AmadeusClient] Found {len(flight_offers)} flight offers")
            
            formatted_flights = []
            for offer in flight_offers:
                formatted_flight = self._format_flight_offer(offer)
                formatted_flights.append(formatted_flight)
            
            return formatted_flights
            
        except ResponseError as error:
            # Log detailed error information for debugging
            print("[AmadeusClient] ERROR repr:", repr(error))
            print("[AmadeusClient] ERROR args:", getattr(error, "args", None))
            print("[AmadeusClient] ERROR dict:", getattr(error, "__dict__", None))

            if getattr(error, "response", None):
                print("[AmadeusClient] Error status:", error.response.status_code)
                print("[AmadeusClient] Error body:", error.response.body)
                
                http_resp = error.response.http_response
                print("[AmadeusClient] http_response repr:", repr(http_resp))
                if hasattr(http_resp, "reason"):
                    print("[AmadeusClient] http_response.reason:", repr(http_resp.reason))

            raise Exception(f"Amadeus API error: {error}")
            
        except Exception as error:
            print(f"[AmadeusClient] ERROR: {error}")
            raise
    
    def _format_flight_offer(self, offer: Dict) -> Dict:
        """
        Format Amadeus flight offer into simplified structure
        
        Converts complex Amadeus response into clean, easy-to-use format
        """
        try:
            # Extract price
            price = float(offer['price']['total'])
            currency = offer['price']['currency']
            
            # Extract itineraries (outbound and return)
            itineraries = offer['itineraries']
            
            # Format outbound flight
            outbound = self._format_itinerary(itineraries[0])
            
            # Format return flight if exists
            return_flight = None
            if len(itineraries) > 1:
                return_flight = self._format_itinerary(itineraries[1])
            
            return {
                "id": offer['id'],
                "price": price,
                "currency": currency,
                "outbound": outbound,
                "return": return_flight
            }
            
        except Exception as e:
            print(f"[AmadeusClient] Error formatting flight: {e}")
            return {
                "id": offer.get('id', 'unknown'),
                "price": 0,
                "currency": "USD",
                "outbound": {},
                "return": None,
                "error": "Formatting error"
            }
    
    def _format_itinerary(self, itinerary: Dict) -> Dict:
        """
        Format a single itinerary (outbound or return)
        
        Extracts key information from multi-segment journey
        """
        segments = itinerary['segments']
        
        # Get first and last segment for overall journey
        first_segment = segments[0]
        last_segment = segments[-1]
        
        # Extract airline info
        carrier_code = first_segment.get('carrierCode', 'N/A')
        flight_number = first_segment.get('number', 'N/A')
        
        # Calculate stops
        stops = len(segments) - 1
        
        return {
            "airline": carrier_code,
            "flight": f"{carrier_code}{flight_number}",
            "from": first_segment['departure']['iataCode'],
            "to": last_segment['arrival']['iataCode'],
            "departure": first_segment['departure']['at'],
            "arrival": last_segment['arrival']['at'],
            "duration": itinerary.get('duration', 'N/A'),
            "stops": stops
        }