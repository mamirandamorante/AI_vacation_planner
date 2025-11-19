from typing import Dict, Any, List
import json
import os
import sys
from pathlib import Path
from .base_agent import BaseAgent

# Add mcp-servers to path
mcp_path = Path(__file__).parent.parent.parent / 'mcp-servers'
sys.path.insert(0, str(mcp_path))

from places.google_places_client import GooglePlacesClient


class AttractionsAgent(BaseAgent):
    def __init__(self, gemini_api_key: str, places_api_key: str):
        super().__init__("AttractionsAgent", gemini_api_key)
        self.places_client = GooglePlacesClient(places_api_key)
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.log("Starting attractions search...")
            req = self._parse_requirements(input_data)
            attractions = self._search_attractions(req)
            filtered = self._filter_attractions(attractions, req)
            summary = self._generate_summary(filtered, req)
            
            return {
                "success": True,
                "attractions": filtered,
                "summary": summary,
                "agent": self.name
            }
        except Exception as e:
            self.log(f"Error: {str(e)}", "ERROR")
            return self.format_error(e)
    
    def _parse_requirements(self, input_data: Dict) -> Dict:
        return {
            'city': input_data.get('city', 'Unknown'),
            'interests': input_data.get('interests', []),
            'min_rating': input_data.get('min_rating', 4.0)
        }
    
    def _search_attractions(self, req: Dict) -> List[Dict]:
        self.log(f"Searching real attractions in {req['city']}...")
        return self.places_client.search_attractions(req['city'], max_results=15)
    
    def _filter_attractions(self, attractions: List[Dict], req: Dict) -> List[Dict]:
        filtered = [a for a in attractions if a.get('rating', 0) >= req['min_rating']]
        return filtered[:10]
    
    def _generate_summary(self, attractions: List[Dict], req: Dict) -> str:
        if not attractions:
            return f"No attractions found in {req['city']}."
        
        try:
            prompt = f"Summarize these {len(attractions)} attractions in {req['city']} in 2 engaging sentences:\n{json.dumps(attractions[:5])}"
            return self.ask_ai(prompt)
        except:
            return f"Found {len(attractions)} amazing attractions to explore!"