"""
Flight Agent
============
Specialized agent for searching and recommending flights.

This agent inherits from BaseAgent, which means it gets all the 
base functionality (logging, AI, error handling) for free.

What this agent does:
1. Takes user requirements (where, when, budget)
2. Searches for flights (via MCP server - we'll add this later)
3. Uses AI to filter and rank results
4. Returns top recommendations with a summary
"""

from typing import Dict, Any, List
import json
from .base_agent import BaseAgent  # Import our base class


class FlightAgent(BaseAgent):
    """
    Flight Agent - Finds the Best Flights
    
    Inherits from BaseAgent, so it automatically has:
    - self.model (Gemini AI)
    - self.log() method
    - self.ask_ai() method
    - self.format_error() method
    
    This agent's job:
    - Understand what flights the user needs
    - Search for available flights
    - Use AI to pick the best options
    - Explain the recommendations
    """
    
    def __init__(self, gemini_api_key: str):
        """
        Initialize the Flight Agent
        
        What happens:
        1. Call the parent class (BaseAgent) constructor
        2. BaseAgent sets up AI connection
        3. Agent is ready to search flights
        
        Args:
            gemini_api_key: Your Google Gemini API key
        """
        # Call parent class constructor with agent name
        # This sets up everything from BaseAgent
        super().__init__("FlightAgent", gemini_api_key)
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main Execution Method - Search for Flights
        
        This is the main method that gets called when someone needs flights.
        It orchestrates the entire flight search process.
        
        Flow:
        1. Parse input (validate and clean user requirements)
        2. Search flights (call external API via MCP)
        3. Filter with AI (pick best options intelligently)
        4. Generate summary (explain recommendations)
        5. Return results
        
        Args:
            input_data: Dictionary with flight requirements:
            {
                'origin': 'SFO' or 'San Francisco',
                'destination': 'BCN' or 'Barcelona',
                'departure_date': '2025-12-15',
                'return_date': '2025-12-20' (optional),
                'passengers': 2,
                'budget': 2000 (optional),
                'preferences': {
                    'max_stops': 1,
                    'cabin': 'economy'
                }
            }
            
        Returns:
            Dictionary with results:
            {
                "success": True,
                "flights": [ ... list of flight options ... ],
                "summary": "AI-generated summary of options",
                "agent": "FlightAgent"
            }
            
            Or if error:
            {
                "success": False,
                "error": "error message",
                "agent": "FlightAgent"
            }
        """
        try:
            # STEP 1: Log that we're starting
            self.log("Starting flight search...")
            
            # STEP 2: Parse and validate the input
            # This converts messy user input into clean, structured data
            requirements = self._parse_requirements(input_data)
            self.log(f"Requirements: {requirements}")
            
            # STEP 3: Search for flights
            # TODO: Later we'll call the real MCP server here
            # For now, we use mock data to test the agent
            flight_data = self._search_flights_mcp(requirements)
            
            # STEP 4: Use AI to filter and rank the results
            # This picks the best flights based on user preferences
            filtered_flights = self._filter_with_ai(flight_data, requirements)
            
            # STEP 5: Generate a human-friendly summary
            # AI explains the options in natural language
            summary = self._generate_summary(filtered_flights, requirements)
            
            # STEP 6: Return the results
            return {
                "success": True,
                "flights": filtered_flights,
                "summary": summary,
                "agent": self.name
            }
            
        except Exception as e:
            # If anything goes wrong, log it and return formatted error
            self.log(f"Error in flight search: {str(e)}", "ERROR")
            return self.format_error(e)
    
    def _parse_requirements(self, input_data: Dict) -> Dict:
        """
        Parse and Validate User Input
        
        Why do we need this?
        - User input can be messy (lowercase, missing fields, etc.)
        - We need to validate required fields exist
        - Convert to standard format that our code expects
        - Set default values for optional fields
        
        What it does:
        1. Check required fields are present
        2. Convert city names to uppercase airport codes
        3. Extract optional preferences
        4. Set sensible defaults
        
        Args:
            input_data: Raw user input dictionary
            
        Returns:
            Clean, validated requirements dictionary
            
        Raises:
            ValueError: If required fields are missing
        """
        # Define what fields are absolutely required
        required_fields = ['origin', 'destination', 'departure_date']
        
        # Check each required field is present
        for field in required_fields:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Build clean requirements dictionary
        return {
            # Convert to uppercase (SFO, BCN, etc.)
            'origin': input_data['origin'].upper(),
            'destination': input_data['destination'].upper(),
            
            # Required date
            'departure_date': input_data['departure_date'],
            
            # Optional fields - use .get() with defaults
            'return_date': input_data.get('return_date'),  # None if not provided
            'passengers': input_data.get('passengers', 1),  # Default to 1 passenger
            'budget': input_data.get('budget'),  # None if not specified
            
            # Extract preferences or use defaults
            'max_stops': input_data.get('preferences', {}).get('max_stops', 2),
            'cabin': input_data.get('preferences', {}).get('cabin', 'economy')
        }
    
    def _search_flights_mcp(self, req: Dict) -> List[Dict]:
        """
        Search for Flights via MCP Server (REAL DATA)
        
        This calls our MCP Flight Server which connects to Amadeus API.
        Returns real flight data with actual prices.
        
        Flow:
        1. Prepare parameters for MCP tool
        2. Call MCP server (will implement client later)
        3. Parse response
        4. Return flights
        
        Args:
            req: Parsed requirements dictionary
            
        Returns:
            List of real flight dictionaries from Amadeus
        """
        self.log("Calling MCP Flight Server for real data...")
        
        # For now, import and use amadeus_client directly
        # Later we'll use proper MCP protocol
        import sys
        import os
        
        # Add MCP server path to import amadeus_client
        mcp_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', 'mcp-servers', 'flights'
        )
        sys.path.insert(0, mcp_path)
        
        from amadeus_client import AmadeusFlightClient
        from dotenv import load_dotenv
        
        # Load environment
        env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
        load_dotenv(env_path)
        
        # Get credentials
        api_key = os.getenv('AMADEUS_API_KEY')
        api_secret = os.getenv('AMADEUS_API_SECRET')
        
        # Create Amadeus client
        amadeus = AmadeusFlightClient(api_key, api_secret)
        
        # Search flights
        try:
            flights = amadeus.search_flights(
                origin=req['origin'],
                destination=req['destination'],
                departure_date=req['departure_date'],
                return_date=req.get('return_date'),
                adults=req.get('passengers', 1),
                max_results=10  # Get more results for AI to filter
            )
            
            self.log(f"MCP returned {len(flights)} flights")
            return flights
            
        except Exception as e:
            self.log(f"MCP call failed: {e}, falling back to mock data", "WARN")
            # Fall back to mock data if MCP fails
            return self._search_flights_mock(req)
    
    def _search_flights_mock(self, req: Dict) -> List[Dict]:
        """
        Search for Flights (Mock Data)
        
        TEMPORARY METHOD:
        This currently returns fake flight data for testing.
        Later, we'll replace this with a real call to our MCP Flight Server,
        which will call the Amadeus API to get real flight data.
        
        Why mock data?
        - Can test the agent without needing the MCP server yet
        - Faster development and testing
        - Can control the test data exactly
        
        Future: Will become _search_flights_mcp() and call real API
        
        Args:
            req: Parsed requirements dictionary
            
        Returns:
            List of flight dictionaries with mock data
        """
        self.log("Using mock flight data (will be replaced with MCP call)...")
        
        # Return 2 mock flights for testing
        # In real implementation, this would come from Amadeus API
        return [
            {
                "id": "FL001",
                "price": 1250,
                "currency": "USD",
                "outbound": {  # Departure flight
                    "airline": "United Airlines",
                    "flight": "UA87",
                    "from": req['origin'],
                    "to": req['destination'],
                    "departure": f"{req['departure_date']} 10:30",
                    "arrival": f"{req['departure_date']} 19:45",
                    "duration": "11h 15m",
                    "stops": 0  # Non-stop
                },
                "return": {  # Return flight
                    "airline": "United Airlines",
                    "flight": "UA88",
                    "from": req['destination'],
                    "to": req['origin'],
                    "departure": f"{req.get('return_date', '')} 12:00",
                    "arrival": f"{req.get('return_date', '')} 15:15",
                    "duration": "12h 15m",
                    "stops": 0
                } if req.get('return_date') else None  # Only if round trip
            },
            {
                "id": "FL002",
                "price": 980,  # Cheaper but with a stop
                "currency": "USD",
                "outbound": {
                    "airline": "Lufthansa",
                    "flight": "LH454",
                    "from": req['origin'],
                    "to": req['destination'],
                    "departure": f"{req['departure_date']} 14:00",
                    "arrival": f"{req['departure_date']} 09:30",
                    "duration": "13h 30m",
                    "stops": 1  # One stop
                },
                "return": {
                    "airline": "Lufthansa",
                    "flight": "LH455",
                    "from": req['destination'],
                    "to": req['origin'],
                    "departure": f"{req.get('return_date', '')} 10:00",
                    "arrival": f"{req.get('return_date', '')} 13:30",
                    "duration": "13h 30m",
                    "stops": 1
                } if req.get('return_date') else None
            }
        ]
    
    def _filter_with_ai(self, flights: List[Dict], req: Dict) -> List[Dict]:
        """
        Filter and Rank Flights Using AI
        
        Why use AI for filtering?
        - AI can understand complex trade-offs (price vs time vs comfort)
        - Can consider multiple factors simultaneously
        - Makes intelligent recommendations like a human travel agent
        
        What it does:
        1. Apply hard filters (budget, max stops)
        2. Use AI to rank remaining options
        3. Return top 5 flights
        
        Future Enhancement: 
        - Could use AI to understand preferences like "prefer morning flights"
        - Learn from user choices over time
        
        Args:
            flights: List of all available flights
            req: User requirements with preferences
            
        Returns:
            Top 5 filtered and ranked flights
        """
        self.log("Filtering flights with AI...")
        
        # FILTER 1: Budget constraint (hard filter)
        # Remove any flights over budget
        if req.get('budget'):
            flights = [f for f in flights if f['price'] <= req['budget']]
            self.log(f"After budget filter: {len(flights)} flights")
        
        # FILTER 2: Max stops constraint (hard filter)
        # Remove flights with too many stops
        if req.get('max_stops') is not None:
            flights = [f for f in flights 
                      if f['outbound']['stops'] <= req['max_stops']]
            self.log(f"After stops filter: {len(flights)} flights")
        
        # TODO: Use AI to intelligently rank flights
        # For now, just return the filtered list
        # Future: Send to Gemini to rank by value, convenience, etc.
        
        # Return top 5 options
        return flights[:5]
    
    def _generate_summary(self, flights: List[Dict], req: Dict) -> str:
        """
        Generate Human-Friendly Summary
        
        Why generate a summary?
        - Users don't want to read through raw flight data
        - AI can highlight what matters (best deal, fastest, etc.)
        - Natural language is easier to understand than tables
        
        What the AI does:
        - Analyzes all the flight options
        - Identifies key highlights (cheapest, fastest, best value)
        - Writes 2-3 sentences in friendly language
        
        Args:
            flights: Filtered list of flight options
            req: Original requirements for context
            
        Returns:
            Natural language summary string
        """
        self.log("Generating summary with AI...")
        
        # Edge case: No flights found
        if not flights:
            return "No flights found matching your criteria. Try adjusting your dates or budget."
        
        # Build a prompt for Gemini
        prompt = f"""You are a helpful travel agent. Create a brief, friendly summary 
        of these flight options for someone traveling from {req['origin']} to 
        {req['destination']} on {req['departure_date']}.
        
        Flight options:
        {json.dumps(flights, indent=2)}
        
        Write 2-3 sentences highlighting:
        - The best value option
        - The fastest/most convenient option
        - Price range
        
        Keep it concise and conversational."""
        
        try:
            # Ask Gemini to generate the summary
            summary = self.ask_ai(prompt)
            return summary
            
        except Exception as e:
            # If AI fails, generate a simple fallback summary
            self.log(f"AI summary failed, using fallback: {e}", "WARN")
            prices = [f['price'] for f in flights]
            return (f"Found {len(flights)} flight options from "
                   f"${min(prices)} to ${max(prices)}.")