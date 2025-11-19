"""
Amadeus API Client
==================
This class handles all communication with the Amadeus Flight API.

What it does:
- Authenticates with Amadeus (gets access token)
- Searches for flights based on requirements
- Converts city names to airport codes
- Handles errors and rate limits
- Returns clean, structured flight data

Why wrap the API?
- Cleaner code (agents don't need to know API details)
- Easier to test (can mock this class)
- Centralized error handling
- Can add caching, retries, etc. in one place
"""

import os
from amadeus import Client, ResponseError
from typing import Dict, List, Optional
from datetime import datetime


class AmadeusFlightClient:
    """
    Wrapper for Amadeus Flight API
    
    Handles authentication and flight searches
    """
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize Amadeus client
        
        What happens:
        1. Store credentials
        2. Create Amadeus client (handles authentication automatically)
        3. Client is ready to make API calls
        
        Args:
            api_key: Your Amadeus API key
            api_secret: Your Amadeus API secret
        """
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Create Amadeus client
        # This handles OAuth authentication automatically
        self.client = Client(
            client_id=api_key,
            client_secret=api_secret,
            hostname='test'
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
        Search for flights
        
        This is the main method that searches Amadeus for flight options.
        
        How it works:
        1. Validate inputs
        2. Call Amadeus API with parameters
        3. Parse response
        4. Format data into clean structure
        5. Return list of flights
        
        Args:
            origin: Origin airport code (e.g., "SFO")
            destination: Destination airport code (e.g., "BCN")
            departure_date: Departure date (YYYY-MM-DD)
            return_date: Return date (YYYY-MM-DD), optional for one-way
            adults: Number of adult passengers
            max_results: Maximum number of results to return
            
        Returns:
            List of flight dictionaries with structured data
            
        Raises:
            Exception: If API call fails
        """
        try:
            print(f"[AmadeusClient] Searching flights: {origin} → {destination} on {departure_date}")
            
            # STEP 1: Build API request parameters
            search_params = {
                'originLocationCode': origin.upper(),
                'destinationLocationCode': destination.upper(),
                'departureDate': departure_date,
                'adults': adults,
                'max': max_results,
                'currencyCode': 'USD'  # Return prices in USD
            }
            
            # Add return date if provided (round trip)
            if return_date:
                search_params['returnDate'] = return_date
            
            # STEP 2: Call Amadeus API
            # flight_offers_search is the Amadeus endpoint for searching flights
            response = self.client.shopping.flight_offers_search.get(**search_params)
            
            # STEP 3: Extract data from response
            # response.data contains the list of flight offers
            flight_offers = response.data
            
            print(f"[AmadeusClient] Found {len(flight_offers)} flight offers")
            
            # STEP 4: Format each flight offer into our structure
            formatted_flights = []
            for offer in flight_offers:
                formatted_flight = self._format_flight_offer(offer)
                formatted_flights.append(formatted_flight)
            
            return formatted_flights
            
        except ResponseError as error:
            import traceback

            print("[AmadeusClient] ERROR repr:", repr(error))
            print("[AmadeusClient] ERROR args:", getattr(error, "args", None))
            print("[AmadeusClient] ERROR dict:", getattr(error, "__dict__", None))
            print("[AmadeusClient] ERROR cause:", repr(getattr(error, "__cause__", None)))
            print("[AmadeusClient] ERROR context:", repr(getattr(error, "__context__", None)))

            if getattr(error, "response", None):
                print("[AmadeusClient] Error status:", error.response.status_code)
                print("[AmadeusClient] Error body:", error.response.body)

            if getattr(error, "response", None):
                http_resp = error.response.http_response
                print("[AmadeusClient] http_response repr:", repr(http_resp))
                print("[AmadeusClient] http_response dir:", dir(http_resp))
                if hasattr(http_resp, "reason"):
                    print("[AmadeusClient] http_response.reason:", repr(http_resp.reason))

            raise Exception(f"Amadeus API error: {error}")

            
            
        except Exception as error:
            # General error (network, parsing, etc.)
            print(f"[AmadeusClient] ERROR: {error}")
            raise
    
    def _format_flight_offer(self, offer: Dict) -> Dict:
        """
        Format Amadeus flight offer into our standard structure
        
        Why format?
        - Amadeus response is complex and nested
        - We want a simple, clean structure for our agents
        - Easier to work with in frontend
        
        Amadeus structure is complex:
        {
            "id": "1",
            "price": { "total": "1250.00", "currency": "USD" },
            "itineraries": [
                {
                    "segments": [
                        {
                            "departure": { "iataCode": "SFO", "at": "2025-12-15T10:30:00" },
                            "arrival": { "iataCode": "BCN", "at": "2025-12-15T19:45:00" },
                            "carrierCode": "UA",
                            "number": "87",
                            "duration": "PT11H15M"
                        }
                    ]
                }
            ]
        }
        
        We simplify it to:
        {
            "id": "1",
            "price": 1250,
            "currency": "USD",
            "outbound": { ... simple structure ... },
            "return": { ... simple structure ... }
        }
        
        Args:
            offer: Raw Amadeus flight offer
            
        Returns:
            Formatted flight dictionary
        """
        try:
            # Extract price
            price = float(offer['price']['total'])
            currency = offer['price']['currency']
            
            # Extract itineraries (outbound and return)
            itineraries = offer['itineraries']
            
            # Format outbound flight (first itinerary)
            outbound = self._format_itinerary(itineraries[0])
            
            # Format return flight (second itinerary, if exists)
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
            # Return a basic structure if formatting fails
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
        
        An itinerary can have multiple segments (flights with stops).
        We extract the most important information.
        
        Args:
            itinerary: Amadeus itinerary object
            
        Returns:
            Simplified itinerary dictionary
        """
        segments = itinerary['segments']
        
        # Get first and last segment for overall journey info
        first_segment = segments[0]
        last_segment = segments[-1]
        
        # Extract airline info from first segment
        carrier_code = first_segment.get('carrierCode', 'N/A')
        flight_number = first_segment.get('number', 'N/A')
        
        # Calculate number of stops (segments - 1)
        stops = len(segments) - 1
        
        return {
            "airline": carrier_code,  # e.g., "UA" for United Airlines
            "flight": f"{carrier_code}{flight_number}",  # e.g., "UA87"
            "from": first_segment['departure']['iataCode'],  # e.g., "SFO"
            "to": last_segment['arrival']['iataCode'],  # e.g., "BCN"
            "departure": first_segment['departure']['at'],  # ISO datetime
            "arrival": last_segment['arrival']['at'],  # ISO datetime
            "duration": itinerary.get('duration', 'N/A'),  # e.g., "PT11H15M"
            "stops": stops  # 0 for non-stop, 1+ for stops
        }