from typing import Dict, Any, List
import json
import sys
from pathlib import Path
from .base_agent import BaseAgent

# Add mcp-servers to path
mcp_path = Path(__file__).parent.parent.parent / 'mcp-servers'
sys.path.insert(0, str(mcp_path))

from places.google_places_client import GooglePlacesClient


class RestaurantAgent(BaseAgent):
    def __init__(self, gemini_api_key: str, places_api_key: str):
        super().__init__("RestaurantAgent", gemini_api_key)
        self.places_client = GooglePlacesClient(places_api_key)
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.log("Starting restaurant search...")
            req = self._parse_requirements(input_data)
            restaurants = self._search_restaurants(req)
            filtered = self._filter_restaurants(restaurants, req)
            summary = self._generate_summary(filtered, req)
            
            return {
                "success": True,
                "restaurants": filtered,
                "summary": summary,
                "agent": self.name
            }
        except Exception as e:
            self.log(f"Error: {str(e)}", "ERROR")
            return self.format_error(e)
    
    def _parse_requirements(self, input_data: Dict) -> Dict:
        return {
            'city': input_data.get('city', 'Unknown'),
            'cuisine': input_data.get('cuisine'),
            'min_rating': input_data.get('min_rating', 4.0),
            'price_level': input_data.get('price_level', 2)
        }
    
    def _search_restaurants(self, req: Dict) -> List[Dict]:
        self.log(f"Searching real restaurants in {req['city']}...")
        return self.places_client.search_restaurants(req['city'], max_results=15)
    
    def _filter_restaurants(self, restaurants: List[Dict], req: Dict) -> List[Dict]:
        filtered = [r for r in restaurants if r.get('rating', 0) >= req['min_rating']]
        return filtered[:10]
    
    def _generate_summary(self, restaurants: List[Dict], req: Dict) -> str:
        if not restaurants:
            return f"No restaurants found in {req['city']}."
        
        try:
            prompt = f"Summarize these {len(restaurants)} restaurants in {req['city']} in 2 engaging sentences:\n{json.dumps(restaurants[:5])}"
            return self.ask_ai(prompt)
        except:
            return f"Found {len(restaurants)} great restaurants to explore!"