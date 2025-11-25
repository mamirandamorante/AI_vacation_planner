"""
Amadeus Hotel API Client with SSL Configuration
================================================
Handles all communication with the Amadeus Hotel API.
Includes SSL certificate verification fix.
"""

import os
import ssl
import certifi
from amadeus import Client, ResponseError
from typing import Dict, List, Optional
from datetime import datetime


class AmadeusHotelClient:
    """
    Wrapper for Amadeus Hotel API with SSL certificate handling
    """
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize Amadeus client with SSL configuration
        """
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Configure SSL context to use certifi's certificate bundle
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        # Create Amadeus client with SSL configuration
        self.client = Client(
            client_id=api_key,
            client_secret=api_secret,
            hostname='test',
            ssl=ssl_context  # Add SSL context to client
        )
        
        print("[AmadeusHotelClient] ✅ Initialized successfully")
    
    def search_hotels(
        self,
        city_code: str,
        check_in_date: str,
        check_out_date: str,
        adults: int = 2,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Search for hotels in a city
        
        Two-step process:
        1. Search by city to get hotel IDs
        2. Get offers (prices) for those hotels
        """
        try:
            print(f"[AmadeusHotelClient] Searching hotels in {city_code}")
            print(f"[AmadeusHotelClient] Check-in: {check_in_date}, Check-out: {check_out_date}")
            
            # STEP 1: Search for hotels by city
            hotel_search = self.client.reference_data.locations.hotels.by_city.get(
                cityCode=city_code
            )
            
            hotel_ids = [hotel['hotelId'] for hotel in hotel_search.data[:max_results]]
            
            if not hotel_ids:
                print(f"[AmadeusHotelClient] No hotels found in {city_code}")
                return []
            
            print(f"[AmadeusHotelClient] Found {len(hotel_ids)} hotels, getting offers...")
            
            # STEP 2: Get hotel offers (prices, availability)
            try:
                offers_response = self.client.shopping.hotel_offers_search.get(
                    hotelIds=','.join(hotel_ids[:10]),
                    checkInDate=check_in_date,
                    checkOutDate=check_out_date,
                    adults=adults,
                    currency='USD'
                )
                
                # Check if we got data
                if not hasattr(offers_response, 'data') or offers_response.data is None:
                    print(f"[AmadeusHotelClient] No offers data returned")
                    return []
                
                hotels = []
                for offer_data in offers_response.data:
                    formatted_hotel = self._format_hotel_offer(offer_data)
                    if formatted_hotel:
                        hotels.append(formatted_hotel)
                
                print(f"[AmadeusHotelClient] Returning {len(hotels)} hotel offers")
                return hotels
                
            except ResponseError as e:
                print(f"[AmadeusHotelClient] Offers API ERROR: {e}")
                return []
            except Exception as e:
                print(f"[AmadeusHotelClient] Offers ERROR: {e}")
                import traceback
                traceback.print_exc()
                return []
            
        except ResponseError as error:
            print(f"[AmadeusHotelClient] API ERROR: {error}")
            print(f"[AmadeusHotelClient] Error details: {error.response.body if hasattr(error, 'response') else 'No details'}")
            return []
            
        except Exception as error:
            print(f"[AmadeusHotelClient] ERROR: {error}")
            return []
    
    def _format_hotel_offer(self, offer: Dict) -> Dict:
        """
        Format Amadeus hotel offer into simplified structure
        """
        try:
            hotel = offer.get('hotel', {})
            offers = offer.get('offers', [])
            
            # Get the first (usually cheapest) offer
            first_offer = offers[0] if offers else {}
            
            # Extract price
            price_info = first_offer.get('price', {})
            price = float(price_info.get('total', 0))
            currency = price_info.get('currency', 'USD')
            
            # Extract room info
            room_info = first_offer.get('room', {})
            room_type = room_info.get('description', {}).get('text', 'Standard Room')
            
            return {
                "id": hotel.get('hotelId', 'unknown'),
                "name": hotel.get('name', 'Unknown Hotel'),
                "rating": int(hotel.get('rating', 0)) if hotel.get('rating') else 0,
                "price": price,
                "currency": currency,
                "room_type": room_type,
                "location": {
                    "lat": hotel.get('latitude'),
                    "lng": hotel.get('longitude')
                }
            }
            
        except Exception as e:
            print(f"[AmadeusHotelClient] Error formatting hotel: {e}")
            return {
                "id": "unknown",
                "name": "Unknown Hotel",
                "rating": 0,
                "price": 0,
                "currency": "USD",
                "room_type": "Standard",
                "location": {}
            }