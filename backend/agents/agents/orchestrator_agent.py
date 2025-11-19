from typing import Dict, Any
import json
from .base_agent import BaseAgent


class OrchestratorAgent(BaseAgent):
    """
    Master agent that coordinates all specialized agents
    """
    
    def __init__(self, gemini_api_key: str, flight_agent, hotel_agent, restaurant_agent, attractions_agent):
        super().__init__("OrchestratorAgent", gemini_api_key)
        self.flight_agent = flight_agent
        self.hotel_agent = hotel_agent
        self.restaurant_agent = restaurant_agent
        self.attractions_agent = attractions_agent
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrate all agents to create complete vacation plan
        """
        try:
            self.log("Starting orchestration...")
            
            # Extract travel details
            origin = input_data.get('origin')
            destination = input_data.get('destination')
            departure_date = input_data.get('departure_date')
            return_date = input_data.get('return_date')
            passengers = input_data.get('passengers', 2)
            budget = input_data.get('budget')
            preferences = input_data.get('preferences', {})
            
            results = {}
            
            # 1. Get Flights
            self.log("Calling FlightAgent...")
            results['flights'] = self.flight_agent.execute({
                'origin': origin,
                'destination': destination,
                'departure_date': departure_date,
                'return_date': return_date,
                'passengers': passengers,
                'budget': budget,
                'preferences': preferences
            })
            
            # 2. Get Hotels
            self.log("Calling HotelAgent...")
            results['hotels'] = self.hotel_agent.execute({
                'city_code': destination,
                'check_in_date': departure_date,
                'check_out_date': return_date,
                'adults': passengers,
                'budget_per_night': budget // 5 if budget else 300,
                'preferences': preferences
            })
            
            # 3. Get Restaurants
            self.log("Calling RestaurantAgent...")
            results['restaurants'] = self.restaurant_agent.execute({
                'city': destination,
                'min_rating': preferences.get('min_rating', 4.0)
            })
            
            # 4. Get Attractions
            self.log("Calling AttractionsAgent...")
            results['attractions'] = self.attractions_agent.execute({
                'city': destination,
                'min_rating': 4.0
            })
            
            # 5. Generate comprehensive summary
            summary = self._generate_comprehensive_summary(results, input_data)
            
            return {
                "success": True,
                "results": results,
                "summary": summary,
                "agent": self.name
            }
            
        except Exception as e:
            self.log(f"Orchestration error: {str(e)}", "ERROR")
            return self.format_error(e)
    
    def _generate_comprehensive_summary(self, results: Dict, travel_details: Dict) -> str:
        """Generate AI summary of complete vacation plan"""
        try:
            prompt = f"""Create a brief, engaging 3-4 sentence summary of this vacation plan:

Destination: {travel_details.get('origin')} to {travel_details.get('destination')}
Dates: {travel_details.get('departure_date')} to {travel_details.get('return_date')}

Available:
- {len(results['flights'].get('flights', []))} flight options
- {len(results['hotels'].get('hotels', []))} hotel options  
- {len(results['restaurants'].get('restaurants', []))} restaurant recommendations
- {len(results['attractions'].get('attractions', []))} attractions to visit

Make it exciting and highlight the best options!"""
            
            return self.ask_ai(prompt)
        except:
            return "Your complete vacation plan is ready with flights, hotels, restaurants, and attractions!"