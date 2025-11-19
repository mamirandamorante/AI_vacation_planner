from typing import Dict, Any, List
import json
from datetime import datetime, timedelta
from .base_agent import BaseAgent


class ItineraryAgent(BaseAgent):
    """
    Creates day-by-day itinerary from all vacation data
    """
    
    def __init__(self, gemini_api_key: str):
        super().__init__("ItineraryAgent", gemini_api_key)
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.log("Generating itinerary...")
            
            # Extract data
            flights = input_data.get('flights', [])
            hotels = input_data.get('hotels', [])
            restaurants = input_data.get('restaurants', [])
            attractions = input_data.get('attractions', [])
            departure_date = input_data.get('departure_date')
            return_date = input_data.get('return_date')
            
            # Generate day-by-day itinerary
            itinerary = self._generate_itinerary(
                departure_date, return_date, 
                flights, hotels, restaurants, attractions
            )
            
            return {
                "success": True,
                "itinerary": itinerary,
                "agent": self.name
            }
            
        except Exception as e:
            self.log(f"Error: {str(e)}", "ERROR")
            return self.format_error(e)
    
    def _generate_itinerary(self, start_date, end_date, flights, hotels, restaurants, attractions):
        """Generate AI-powered day-by-day itinerary"""
        
        # Calculate number of days
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        num_days = (end - start).days
        
        self.log(f"Creating {num_days}-day itinerary...")
        
        # Prepare context for AI
        context = f"""Create a detailed day-by-day itinerary for a {num_days}-day trip.

AVAILABLE OPTIONS:
Restaurants: {json.dumps(restaurants[:10])}
Attractions: {json.dumps(attractions[:10])}

Create a realistic daily schedule with:
- Morning activities (9 AM - 12 PM)
- Lunch recommendations (12 PM - 2 PM)
- Afternoon activities (2 PM - 6 PM)
- Dinner recommendations (7 PM - 9 PM)

Format as JSON array of days:
[
  {{
    "day": 1,
    "date": "{start_date}",
    "morning": {{"activity": "...", "location": "..."}},
    "lunch": {{"restaurant": "...", "cuisine": "..."}},
    "afternoon": {{"activity": "...", "location": "..."}},
    "dinner": {{"restaurant": "...", "cuisine": "..."}}
  }}
]

Use REAL restaurants and attractions from the lists. Be specific and practical."""

        try:
            response = self.ask_ai(context)
            # Clean and parse JSON
            clean_json = response.replace('```json', '').replace('```', '').strip()
            itinerary = json.loads(clean_json)
            return itinerary
        except Exception as e:
            self.log(f"AI generation failed: {e}, using fallback", "WARN")
            return self._generate_simple_itinerary(num_days, start_date, restaurants, attractions)
    
    def _generate_simple_itinerary(self, num_days, start_date, restaurants, attractions):
        """Fallback simple itinerary"""
        itinerary = []
        start = datetime.strptime(start_date, '%Y-%m-%d')
        
        for day in range(num_days):
            current_date = (start + timedelta(days=day)).strftime('%Y-%m-%d')
            itinerary.append({
                "day": day + 1,
                "date": current_date,
                "morning": {"activity": attractions[day % len(attractions)]['name'] if attractions else "Explore the city"},
                "lunch": {"restaurant": restaurants[day % len(restaurants)]['name'] if restaurants else "Local cuisine"},
                "afternoon": {"activity": attractions[(day + 1) % len(attractions)]['name'] if len(attractions) > 1 else "Continue exploring"},
                "dinner": {"restaurant": restaurants[(day + 1) % len(restaurants)]['name'] if len(restaurants) > 1 else "Dinner spot"}
            })
        
        return itinerary