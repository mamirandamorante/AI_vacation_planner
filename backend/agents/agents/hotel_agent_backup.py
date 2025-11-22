"""
Hotel Agent
===========
Specialized agent for searching and recommending hotels.

Similar to FlightAgent but focuses on accommodations.

What this agent does:
1. Takes user requirements (location, dates, budget, preferences)
2. Searches for hotels (via Amadeus API)
3. Uses AI to filter and rank results
4. Returns top recommendations with a summary
"""

from typing import Dict, Any, List
import json
from .base_agent import BaseAgent


class HotelAgent(BaseAgent):
    """
    Hotel Agent - Finds the Best Hotels
    
    Inherits from BaseAgent, so it automatically has:
    - self.model (Gemini AI)
    - self.log() method
    - self.ask_ai() method
    - self.format_error() method
    
    This agent's job:
    - Understand what hotels the user needs
    - Search for available hotels
    - Use AI to pick the best options
    - Explain the recommendations
    """
    
    def __init__(self, gemini_api_key: str):
        """
        Initialize the Hotel Agent
        
        Args:
            gemini_api_key: Your Google Gemini API key
        """
        # Call parent class constructor with agent name
        super().__init__("HotelAgent", gemini_api_key)
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main Execution Method - Search for Hotels
        
        Flow:
        1. Parse input (validate user requirements)
        2. Search hotels (call Amadeus via client)
        3. Filter with AI (pick best options)
        4. Generate summary (explain recommendations)
        5. Return results
        
        Args:
            input_data: Dictionary with hotel requirements:
            {
                'city_code': 'NYC' or 'LAX',
                'check_in_date': '2025-12-15',
                'check_out_date': '2025-12-20',
                'adults': 2,
                'budget_per_night': 200,
                'preferences': {
                    'min_rating': 4,
                    'amenities': ['wifi', 'pool']
                }
            }
            
        Returns:
            Dictionary with results:
            {
                "success": True,
                "hotels": [ ... list of hotel options ... ],
                "summary": "AI-generated summary",
                "agent": "HotelAgent"
            }
        """
        try:
            # STEP 1: Log that we're starting
            self.log("Starting hotel search...")
            
            # STEP 2: Parse and validate the input
            requirements = self._parse_requirements(input_data)
            self.log(f"Requirements: {requirements}")
            
            # STEP 3: Search for hotels via Amadeus
            hotel_data = self._search_hotels_amadeus(requirements)
            
            # STEP 4: Use AI to filter and rank the results
            filtered_hotels = self._filter_with_ai(hotel_data, requirements)
            
            # STEP 5: Generate a human-friendly summary
            summary = self._generate_summary(filtered_hotels, requirements)
            
            # STEP 6: Return the results
            return {
                "success": True,
                "hotels": filtered_hotels,
                "summary": summary,
                "agent": self.name
            }
            
        except Exception as e:
            # If anything goes wrong, log it and return formatted error
            self.log(f"Error in hotel search: {str(e)}", "ERROR")
            return self.format_error(e)
    
    def _parse_requirements(self, input_data: Dict) -> Dict:
        """
        Parse and Validate User Input
        
        Args:
            input_data: Raw user input dictionary
            
        Returns:
            Clean, validated requirements dictionary
            
        Raises:
            ValueError: If required fields are missing
        """
        # Define required fields
        required_fields = ['city_code', 'check_in_date', 'check_out_date']
        
        # Check each required field is present
        for field in required_fields:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Build clean requirements dictionary
        return {
            # Required fields
            'city_code': input_data['city_code'].upper(),
            'check_in_date': input_data['check_in_date'],
            'check_out_date': input_data['check_out_date'],
            
            # Optional fields with defaults
            'adults': input_data.get('adults', 2),
            'budget_per_night': input_data.get('budget_per_night'),
            
            # Extract preferences
            'min_rating': input_data.get('preferences', {}).get('min_rating', 3),
            'amenities': input_data.get('preferences', {}).get('amenities', [])
        }
    
    def _search_hotels_amadeus(self, req: Dict) -> List[Dict]:
        """
        Search for Hotels via Amadeus API
        
        Args:
            req: Parsed requirements dictionary
            
        Returns:
            List of hotel dictionaries from Amadeus
        """
        self.log("Calling Amadeus Hotel API...")
        
        # Import Amadeus client
        import sys
        import os
        
        # Add MCP server path to import amadeus_hotel_client
        mcp_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'mcp-servers', 'hotels'
        )
        sys.path.insert(0, mcp_path)
        
        from amadeus_hotel_client import AmadeusHotelClient
        from dotenv import load_dotenv
        
        # Load environment
        env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
        load_dotenv(env_path)
        
        # Get credentials
        api_key = os.getenv('AMADEUS_API_KEY')
        api_secret = os.getenv('AMADEUS_API_SECRET')
        
        # Create Amadeus client
        amadeus = AmadeusHotelClient(api_key, api_secret)
        
        # Search hotels
        try:
            hotels = amadeus.search_hotels(
                city_code=req['city_code'],
                check_in_date=req['check_in_date'],
                check_out_date=req['check_out_date'],
                adults=req.get('adults', 2),
                max_results=15  # Get more results for AI to filter
            )
            
            self.log(f"Amadeus returned {len(hotels)} hotels")
            return hotels
            
        except Exception as e:
            self.log(f"Amadeus call failed: {e}, using mock data", "WARN")
            # Fall back to mock data if API fails
            return self._get_mock_hotels(req)
    
    def _get_mock_hotels(self, req: Dict) -> List[Dict]:
        """
        Mock hotel data for testing
        
        Used as fallback when Amadeus API is unavailable
        """
        self.log("Using mock hotel data...")
        
        return [
            {
                "id": "HOTEL001",
                "name": "Grand Plaza Hotel",
                "rating": 4,
                "price": 180.0,
                "currency": "USD",
                "room_type": "Deluxe Double Room",
                "location": {"lat": 40.7128, "lng": -74.0060}
            },
            {
                "id": "HOTEL002",
                "name": "City Center Inn",
                "rating": 3,
                "price": 120.0,
                "currency": "USD",
                "room_type": "Standard Queen Room",
                "location": {"lat": 40.7580, "lng": -73.9855}
            }
        ]
    
    def _filter_with_ai(self, hotels: List[Dict], req: Dict) -> List[Dict]:
        """
        Filter and Rank Hotels
        
        Args:
            hotels: List of all available hotels
            req: User requirements with preferences
            
        Returns:
            Top 5 filtered and ranked hotels
        """
        self.log("Filtering hotels...")

        # DEBUG: Print raw hotel data
        self.log(f"DEBUG: Raw hotels from Amadeus: {json.dumps(hotels, indent=2)}")
        
        # FILTER 1: Budget constraint
        if req.get('budget_per_night'):
            hotels = [h for h in hotels if h['price'] <= req['budget_per_night']]
            self.log(f"After budget filter: {len(hotels)} hotels")
        
        # FILTER 2: Minimum rating
        if req.get('min_rating'):
            hotels = [h for h in hotels if h['rating'] >= req['min_rating']]
            self.log(f"After rating filter: {len(hotels)} hotels")
        
        # Sort by rating (highest first), then price (lowest first)
        hotels.sort(key=lambda h: (-h['rating'], h['price']))
        
        # Return top 5
        return hotels[:5]
    
    def _generate_summary(self, hotels: List[Dict], req: Dict) -> str:
        """
        Generate Human-Friendly Summary
        
        Args:
            hotels: Filtered list of hotel options
            req: Original requirements for context
            
        Returns:
            Natural language summary string
        """
        self.log("Generating summary...")
        
        # Edge case: No hotels found
        if not hotels:
            return f"No hotels found in {req['city_code']} matching your criteria. Try adjusting your dates or budget."
        
        # Build a prompt for Gemini
        prompt = f"""You are a helpful travel agent. Create a brief, friendly summary 
        of these hotel options in {req['city_code']} for check-in on {req['check_in_date']}.
        
        Hotel options:
        {json.dumps(hotels, indent=2)}
        
        Write 2-3 sentences highlighting:
        - The best value option
        - The highest-rated option
        - Price range per night
        
        Keep it concise and conversational."""
        
        try:
            # Ask Gemini to generate the summary
            summary = self.ask_ai(prompt)
            return summary
            
        except Exception as e:
            # If AI fails, generate a simple fallback summary
            self.log(f"AI summary failed, using fallback: {e}", "WARN")
            prices = [h['price'] for h in hotels]
            ratings = [h['rating'] for h in hotels]
            return (f"Found {len(hotels)} hotels in {req['city_code']} from "
                   f"${min(prices)} to ${max(prices)} per night. "
                   f"Ratings range from {min(ratings)} to {max(ratings)} stars.")