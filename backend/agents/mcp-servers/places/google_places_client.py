"""
Google Places API Client
========================
Handles communication with Google Places API for restaurants and attractions.
"""

import requests
from typing import Dict, List


class GooglePlacesClient:
    """
    Wrapper for Google Places API
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place"
        print("[GooglePlacesClient] ✅ Initialized successfully")
    
    def search_restaurants(self, location: str, max_results: int = 15) -> List[Dict]:
        """Search for restaurants in specific location"""
        try:
            print(f"[GooglePlacesClient] Searching restaurants in {location}")
            
            url = f"{self.base_url}/textsearch/json"
            params = {
                'query': f'best restaurants in {location} city',
                'key': self.api_key,
                'type': 'restaurant'
            }
            
            # Add region hint if available
            region = self._get_country_code(location)
            if region:
                params['region'] = region
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') != 'OK':
                print(f"[GooglePlacesClient] API status: {data.get('status')}")
                return []
            
            restaurants = []
            for place in data.get('results', [])[:max_results]:
                # Basic filter - just use top results
                restaurants.append({
                    "id": place.get('place_id'),
                    "name": place.get('name'),
                    "rating": place.get('rating', 0),
                    "price": place.get('price_level', 2),
                    "cuisine": ', '.join(place.get('types', [])[:2]),
                    "address": place.get('formatted_address', 'N/A')
                })
            
            print(f"[GooglePlacesClient] Found {len(restaurants)} restaurants")
            return restaurants
            
        except Exception as e:
            print(f"[GooglePlacesClient] ERROR: {e}")
            return []
    
    def search_attractions(self, location: str, max_results: int = 15) -> List[Dict]:
        """Search for tourist attractions in specific location"""
        try:
            print(f"[GooglePlacesClient] Searching attractions in {location}")
            
            url = f"{self.base_url}/textsearch/json"
            params = {
                'query': f'top tourist attractions in {location} city',
                'key': self.api_key,
                'type': 'tourist_attraction'
            }
            
            # Add region hint if available
            region = self._get_country_code(location)
            if region:
                params['region'] = region
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') != 'OK':
                print(f"[GooglePlacesClient] API status: {data.get('status')}")
                return []
            
            attractions = []
            for place in data.get('results', [])[:max_results]:
                attractions.append({
                    "id": place.get('place_id'),
                    "name": place.get('name'),
                    "rating": place.get('rating', 0),
                    "type": ', '.join(place.get('types', [])[:2]),
                    "price": self._estimate_price(place),
                    "address": place.get('formatted_address', 'N/A')
                })
            
            print(f"[GooglePlacesClient] Found {len(attractions)} attractions")
            return attractions
            
        except Exception as e:
            print(f"[GooglePlacesClient] ERROR: {e}")
            return []
    
    def _estimate_price(self, place: Dict) -> str:
        """Estimate price for attractions"""
        if 'price_level' in place:
            return '$' * place['price_level']
        # Default pricing based on type
        types = place.get('types', [])
        if 'museum' in types:
            return '$$'
        elif 'park' in types:
            return 'Free'
        else:
            return '$'
    
    def _get_country_code(self, location: str) -> str:
        """Get country code hint for better location targeting"""
        location_codes = {
            # Spain
            'MAD': 'es', 'madrid': 'es',
            'BCN': 'es', 'barcelona': 'es',
            # USA
            'LAX': 'us', 'los angeles': 'us',
            'JFK': 'us', 'NYC': 'us', 'new york': 'us',
            'SFO': 'us', 'san francisco': 'us',
            # France
            'CDG': 'fr', 'paris': 'fr',
            # UK
            'LHR': 'gb', 'london': 'gb'
        }
        return location_codes.get(location.lower(), '')