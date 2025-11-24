"""
Google Places API Client (Enhanced)
===================================
Handles communication with Google Places API (v1) for restaurants and attractions.
Supports structured constraints, proximity search, and detailed field masking.
"""

import requests
import logging
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger("GooglePlacesClient")
logger.setLevel(logging.INFO)

class GooglePlacesClient:
    """
    Wrapper for Google Places API (New v1 Text Search)
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Switched to the NEW Places API endpoint for better natural language processing
        self.base_url = "https://places.googleapis.com/v1/places:searchText"
        print("[GooglePlacesClient] ✅ Initialized successfully")
    
    def _search(self, query: str, max_results: int = 15) -> List[Dict]:
        """Internal helper to perform the actual API request."""
        if not self.api_key:
            print("[GooglePlacesClient] ⚠️ No API Key. Returning Mock Data.")
            return self._get_mock_data(query)

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            # Request specific fields to optimize data usage
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.priceLevel,places.rating,places.userRatingCount,places.types,places.photos,places.accessibilityOptions"
        }
        
        payload = {
            "textQuery": query,
            "maxResultCount": max_results
        }

        try:
            print(f"[GooglePlacesClient] 🌐 API Query: '{query}'")
            response = requests.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for place in data.get('places', []):
                results.append(self._format_place(place))
            
            print(f"[GooglePlacesClient] Found {len(results)} results")
            return results
            
        except Exception as e:
            print(f"[GooglePlacesClient] ❌ ERROR: {e}")
            return []

    def _format_place(self, place: Dict) -> Dict:
        """Normalizes API response into a clean dictionary."""
        return {
            "id": place.get('id'),
            "name": place.get('displayName', {}).get('text'),
            "formatted_address": place.get('formattedAddress'),
            "rating": place.get('rating', 0),
            "user_ratings_total": place.get('userRatingCount', 0),
            "price_level": self._map_price_level(place.get('priceLevel')),
            "types": place.get('types', []),
            "accessibility": place.get('accessibilityOptions', {}),
            "photos": place.get('photos', [])
        }

    def _map_price_level(self, level_str: str) -> int:
        """Maps Google's PRICE_LEVEL_X enum to integer 1-4."""
        mapping = {
            "PRICE_LEVEL_INEXPENSIVE": 1,
            "PRICE_LEVEL_MODERATE": 2,
            "PRICE_LEVEL_EXPENSIVE": 3,
            "PRICE_LEVEL_VERY_EXPENSIVE": 4
        }
        return mapping.get(level_str, 2) # Default to Moderate (2) if unknown

    # =========================================================================
    # RESTAURANT SEARCH (Matching Agent Signature)
    # =========================================================================

    def search_restaurants(self, city: str, constraints: Optional[Dict] = None, proximity_location: Optional[str] = None, target_datetime: Optional[str] = None, max_results: int = 15) -> List[Dict]:
        """
        Search for restaurants using natural language construction.
        Accepts: city, constraints dict, proximity string, target_datetime.
        """
        # 1. Start with base
        query_parts = [f"restaurants in {city}"]
        
        # 2. Add Constraints (Cuisine, Diet, Atmosphere)
        if constraints:
            if constraints.get('cuisine_types'):
                # e.g., "Italian restaurants..."
                query_parts[0] = f"{', '.join(constraints['cuisine_types'])} restaurants in {city}"
            
            if constraints.get('dietary_restrictions'):
                query_parts.append(f"with {' '.join(constraints['dietary_restrictions'])} options")
            
            if constraints.get('atmosphere'):
                query_parts.append(f"with {' '.join(constraints['atmosphere'])} atmosphere")

        # 3. Add Proximity (Context)
        if proximity_location:
            query_parts.append(f"near {proximity_location}")

        # 4. Execute
        full_query = " ".join(query_parts)
        return self._search(full_query, max_results)

    # =========================================================================
    # ATTRACTION SEARCH (Matching Agent Signature)
    # =========================================================================

    def search_attractions(self, city: str, constraints: Optional[Dict] = None, proximity_location: Optional[str] = None, target_date: Optional[str] = None, max_results: int = 15) -> List[Dict]:
        """
        Search for attractions using natural language construction.
        Accepts: city, constraints dict, proximity string, target_date.
        """
        # 1. Base
        query_parts = [f"things to do in {city}"]
        
        # 2. Add Constraints (Types, Interests)
        if constraints:
            if constraints.get('attraction_types'):
                query_parts[0] = f"{', '.join(constraints['attraction_types'])} in {city}"
            
            if constraints.get('interests'):
                query_parts.append(f"related to {' '.join(constraints['interests'])}")
            
            if constraints.get('is_indoor_outdoor'):
                query_parts.append(constraints['is_indoor_outdoor'])
                
            if constraints.get('wheelchair_accessible'):
                query_parts.append("wheelchair accessible")

        # 3. Add Proximity
        if proximity_location:
            query_parts.append(f"near {proximity_location}")

        # 4. Execute
        full_query = " ".join(query_parts)
        return self._search(full_query, max_results)

    # =========================================================================
    # MOCK FALLBACK
    # =========================================================================
    def _get_mock_data(self, query: str) -> List[Dict]:
        """Returns mock data if API key is missing."""
        return [
            {"id": "MOCK1", "name": f"Mock Place A for {query}", "rating": 4.5, "formatted_address": "123 Mock St", "price_level": 2, "types": ["restaurant"], "photos": []},
            {"id": "MOCK2", "name": f"Mock Place B for {query}", "rating": 4.2, "formatted_address": "456 Fake Ave", "price_level": 3, "types": ["restaurant"], "photos": []},
            {"id": "MOCK3", "name": f"Mock Place C for {query}", "rating": 4.8, "formatted_address": "789 Test Blvd", "price_level": 1, "types": ["restaurant"], "photos": []},
        ]