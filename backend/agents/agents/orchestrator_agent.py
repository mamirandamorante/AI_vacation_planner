"""
Orchestrator Agent - TWO-PHASE HIL VERSION WITH INTELLIGENT CLARIFICATION
=========================================================================
Phase 1: User chooses flight and hotel (HIL)
Phase 2: System auto-selects restaurants/attractions/itinerary

STEP 3: Intelligent clarification system handles incomplete/ambiguous prompts
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import google.generativeai as genai
from google.generativeai import types as genai_types
from google.ai import generativelanguage as glm
from pydantic import BaseModel, Field

# --- HIL Status Codes ---
HIL_PAUSE_REQUIRED = "HIL_PAUSE_REQUIRED"
SUCCESS = "SUCCESS"
FINAL_CHOICE = "FINAL_CHOICE"
REFINE_SEARCH = "REFINE_SEARCH"

# =============================================================================
# BASE AGENT
# =============================================================================

class BaseAgent:
    """Placeholder for BaseAgent class with logging and utility methods."""
    def __init__(self, name, api_key):
        self.name = name
        self.api_key = api_key
    def log(self, message: str, level: str = "INFO"):
        print(f"[{self.name}][{level}] {message}")
    def format_error(self, e: Exception) -> Dict[str, Any]:
        return {"success": False, "error": f"Agent Error: {str(e)}"}

# =============================================================================
# ORCHESTRATOR TOOL SCHEMAS
# =============================================================================

class RequestClarification(BaseModel):
    """
    STEP 3 NEW TOOL: Request missing or ambiguous information from user.
    LLM autonomously decides when to call this and what questions to ask.
    """
    clarification_questions: List[str] = Field(
        ..., 
        description="List of clear, natural questions to ask the user. Generate conversational questions, not robotic ones."
    )
    reasoning: str = Field(
        ..., 
        description="Explain why you need this information and what you'll do with it."
    )
    missing_required_fields: List[str] = Field(
        default_factory=list,
        description="Which REQUIRED fields are missing or ambiguous: origin, destination, departure_date, return_date"
    )
    missing_optional_fields: List[str] = Field(
        default_factory=list,
        description="Which OPTIONAL preferences you want to ask about: dietary_restrictions, cuisine_preferences, hotel_amenities, budget"
    )

class FlightSearch(BaseModel):
    """Tool schema for triggering FlightAgent."""
    origin: str = Field(..., description="Origin airport code or city.")
    destination: str = Field(..., description="Destination airport code or city.")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format.")
    return_date: str = Field(..., description="Return date in YYYY-MM-DD format.")

class HotelSearch(BaseModel):
    """Tool schema for triggering HotelAgent."""
    city: str = Field(..., description="City for hotel search.")
    check_in_date: str = Field(..., description="Check-in date in YYYY-MM-DD format.")
    check_out_date: str = Field(..., description="Check-out date in YYYY-MM-DD format.")

class RestaurantSearchConstraints(BaseModel):
    """Filtering constraints for restaurant search."""
    min_rating: Optional[float] = Field(4.0, description="Minimum rating.")
    price_level: Optional[int] = Field(None, description="Price level 1-4.")
    cuisine_types: List[str] = Field(default_factory=list, description="Cuisines.")
    dietary_restrictions: List[str] = Field(default_factory=list, description="Dietary needs.")
    atmosphere: List[str] = Field(default_factory=list, description="Desired vibe.")
    open_now: Optional[bool] = Field(None, description="Only open restaurants.")

class RestaurantSearch(BaseModel):
    """Tool schema for triggering RestaurantAgent."""
    city: str = Field(..., description="City for restaurant search.")
    constraints: RestaurantSearchConstraints = Field(default_factory=RestaurantSearchConstraints)
    proximity_location: Optional[str] = Field(None, description="Hotel name for nearby results.")
    target_datetime: Optional[str] = Field(None, description="Target visit date/time.")
    max_results: int = Field(15, description="Maximum restaurants to search.")

class AttractionsSearchConstraints(BaseModel):
    """Filtering constraints for attraction search."""
    min_rating: Optional[float] = Field(4.0, description="Minimum rating.")
    attraction_types: List[str] = Field(default_factory=list, description="Attraction categories.")
    interests: List[str] = Field(default_factory=list, description="User interests.")
    max_entry_fee: Optional[float] = Field(None, description="Maximum entry fee.")
    is_indoor_outdoor: Optional[str] = Field(None, description="Filter for indoor/outdoor.")
    wheelchair_accessible: Optional[bool] = Field(None, description="Wheelchair accessibility.")

class AttractionsSearch(BaseModel):
    """Tool schema for triggering AttractionsAgent."""
    city: str = Field(..., description="City for attraction search.")
    constraints: AttractionsSearchConstraints = Field(default_factory=AttractionsSearchConstraints)
    proximity_location: Optional[str] = Field(None, description="Hotel for nearby results.")
    target_date: Optional[str] = Field(None, description="Target visit date.")
    max_results: int = Field(15, description="Maximum attractions to search.")

class GenerateItinerary(BaseModel):
    """Tool schema for triggering ItineraryAgent."""
    trip_summary: str = Field(..., description="Summary of finalized trip parameters.")

# =============================================================================
# TWO-PHASE ORCHESTRATOR AGENT
# =============================================================================

class OrchestratorAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str, flight_agent, hotel_agent, restaurant_agent, attractions_agent, itinerary_agent):
        """Initialize OrchestratorAgent with two-phase HIL and intelligent clarification."""
        super().__init__("OrchestratorAgent", gemini_api_key)
        
        # Store specialist agents
        self.flight_agent = flight_agent
        self.hotel_agent = hotel_agent
        self.restaurant_agent = restaurant_agent
        self.attractions_agent = attractions_agent
        self.itinerary_agent = itinerary_agent
        
        # Tool execution mapping - STEP 3: Added RequestClarification
        self.specialist_tools = {
            "RequestClarification": self._tool_request_clarification,  # STEP 3: NEW
            "FlightSearch": self._tool_flight_search,
            "HotelSearch": self._tool_hotel_search,
            "RestaurantSearch": self._tool_restaurant_search,
            "AttractionsSearch": self._tool_attractions_search,
            "GenerateItinerary": itinerary_agent.execute,
        }

        # Pydantic schema mapping - STEP 3: Added RequestClarification
        self.tool_schemas = {
            "RequestClarification": RequestClarification,  # STEP 3: NEW
            "FlightSearch": FlightSearch,
            "HotelSearch": HotelSearch,
            "RestaurantSearch": RestaurantSearch,
            "AttractionsSearch": AttractionsSearch,
            "GenerateItinerary": GenerateItinerary
        }

        # Storage for all results
        self.all_results = {}
        
        # Build system instruction and tools
        self.system_instruction = self._build_system_instruction()
        self.gemini_tools = self._create_gemini_tools()

        genai.configure(api_key=gemini_api_key)

        # Initialize Gemini model
        self.model = genai.GenerativeModel(
            'gemini-2.5-flash',
            tools=self.gemini_tools,
            system_instruction=self.system_instruction,
            generation_config={'temperature': 0.7}
        )
        self.log("✅ OrchestratorAgent initialized with TWO-PHASE HIL + CLARIFICATION")

    # =========================================================================
    # STEP 3: CLARIFICATION HANDLING
    # =========================================================================

    def _tool_request_clarification(self, params: RequestClarification) -> Dict[str, Any]:
        """
        Handle clarification request from LLM.
        This doesn't execute - it returns a special status for main.py to handle.
        """
        self.log(f"⏸️  LLM requests clarification: {len(params.clarification_questions)} questions")
        self.log(f"   Reasoning: {params.reasoning}")
        
        return {
            "status": "clarification_needed",
            "questions": params.clarification_questions,
            "reasoning": params.reasoning,
            "missing_required": params.missing_required_fields,
            "missing_optional": params.missing_optional_fields
        }

    # =========================================================================
    # PHASE 1: CRITICAL DECISIONS (HIL)
    # =========================================================================

    def _execute_phase1_agent(self, agent, initial_params: Dict[str, Any], agent_name: str, item_name: str) -> Dict[str, Any]:
        """
        Execute a Phase 1 agent (FlightAgent or HotelAgent) with HIL support.
        
        Returns immediately on pause for user input.
        """
        self.log(f"🎯 Phase 1: Starting {agent_name}...")
        
        # Execute agent
        result = agent.execute(initial_params, continuation_message=None)
        
        status = result.get('status_code')
        
        # HIL PAUSE
        if status == HIL_PAUSE_REQUIRED:
            self.log(f"⏸️  {agent_name} paused for user input")
            recommendations = result.get(f'recommended_{item_name}s', [])
            summary = result.get('recommendation_summary', f"Here are the top {item_name} options.")
            
            return {
                "status": "awaiting_user_input",
                "agent": agent_name,
                "item_type": item_name,
                "recommendations": recommendations,
                "summary": summary,
                "initial_params": initial_params,
                "phase": 1
            }
        
        # SUCCESS
        elif status == SUCCESS:
            self.log(f"✅ {agent_name} completed")
            return {"status": "success", "result": result}
        
        # ERROR
        else:
            self.log(f"❌ {agent_name} failed: {status}", "ERROR")
            return {"status": "error", "error": f"{agent_name} failed"}

    def _resume_phase1_agent(self, agent, session_state: Dict[str, Any], user_decision: Dict[str, Any], agent_name: str, item_name: str) -> Dict[str, Any]:
        """
        Resume a Phase 1 agent after user makes a choice.
        """
        self.log(f"▶️  Phase 1: Resuming {agent_name}...")
        
        initial_params = session_state.get('initial_params', {})
        
        # Build continuation message
        continuation_message = self._build_continuation_message(user_decision, initial_params, agent_name)
        
        # Resume agent
        result = agent.execute(initial_params, continuation_message=continuation_message)
        
        status = result.get('status_code')
        
        # Check if pausing again (e.g., after refinement)
        if status == HIL_PAUSE_REQUIRED:
            recommendations = result.get(f'recommended_{item_name}s', [])
            summary = result.get('recommendation_summary', '')
            
            return {
                "status": "awaiting_user_input",
                "agent": agent_name,
                "item_type": item_name,
                "recommendations": recommendations,
                "summary": summary,
                "initial_params": initial_params,
                "phase": 1
            }
        
        # SUCCESS - Agent finalized selection
        elif status == SUCCESS:
            self.log(f"✅ {agent_name} finalized selection")
            return {"status": "success", "result": result}
        
        else:
            return {"status": "error", "error": f"{agent_name} resume failed"}

    def _build_continuation_message(self, user_decision: Dict[str, Any], initial_params: Dict[str, Any], agent_name: str) -> Dict[str, Any]:
        """Build continuation message with context preservation."""
        if agent_name == "FlightAgent":
            context = f"CONTEXT: You are searching for flights from {initial_params.get('origin')} to {initial_params.get('destination')}, departing {initial_params.get('departure_date')}, returning {initial_params.get('return_date')}."
        elif agent_name == "HotelAgent":
            context = f"CONTEXT: You are searching for hotels in {initial_params.get('city')}, check-in {initial_params.get('check_in_date')}, check-out {initial_params.get('check_out_date')}."
        else:
            context = "CONTEXT: Continue with original search parameters."
        
        if user_decision.get('status') == REFINE_SEARCH:
            feedback = user_decision.get('feedback', '')
            content = f"{context}\n\nHuman feedback: {feedback}\n\nModify your search accordingly."
        elif user_decision.get('status') == FINAL_CHOICE:
            selection_key = [k for k in user_decision.keys() if k.endswith('_id')]
            selection_id = user_decision.get(selection_key[0]) if selection_key else 'unknown'
            
            if agent_name == "FlightAgent":
                content = f"{context}\n\nFINAL_CHOICE_TRIGGER: The human selected flight ID '{selection_id}'. Call FinalizeSelection now."
            elif agent_name == "HotelAgent":
                content = f"{context}\n\nFINAL_CHOICE_TRIGGER: The human selected hotel ID '{selection_id}'. Call FinalizeSelection now."
            else:
                content = f"{context}\n\nFINAL_CHOICE_TRIGGER: Human selected ID: {selection_id}."
        else:
            content = f"{context}\n\n{user_decision.get('feedback', 'Continue.')}"
        
        return {'content': content, 'original_params': initial_params}

    # =========================================================================
    # PHASE 2: AUTOMATED COMPLETION (NO HIL)
    # =========================================================================

    def _execute_phase2(self, trip_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Phase 2: Automatically select restaurants, attractions, and generate itinerary.
        
        FIXES from STEP 2:
        - Proper destination city extraction
        - Increased max_results for sufficient variety (20 instead of 10)
        - Better location handling
        """
        self.log("🚀 Phase 2: Auto-completing restaurants, attractions, and itinerary...")
        
        try:
            # Extract Phase 1 results
            final_flight = self.all_results.get('final_flight', {})
            final_hotel = self.all_results.get('final_hotel', {})
            
            # STEP 2 FIX: Extract proper destination city
            destination_city = None
            
            # Try hotel city first (most accurate)
            if final_hotel:
                hotel_address = final_hotel.get('address', {})
                if isinstance(hotel_address, dict):
                    destination_city = hotel_address.get('cityName') or hotel_address.get('city')
                elif isinstance(hotel_address, str):
                    destination_city = final_hotel.get('cityCode') or final_hotel.get('name', '').split(',')[0]
            
            # Fallback to flight destination (convert IATA to city name)
            if not destination_city and final_flight:
                dest_code = final_flight.get('outbound', {}).get('to', '')
                iata_to_city = {
                    'JFK': 'New York', 'LGA': 'New York', 'EWR': 'New York',
                    'LAX': 'Los Angeles', 'SFO': 'San Francisco',
                    'ORD': 'Chicago', 'MIA': 'Miami', 'DFW': 'Dallas',
                    'LHR': 'London', 'CDG': 'Paris', 'FCO': 'Rome',
                    'MAD': 'Madrid', 'BCN': 'Barcelona', 'TYO': 'Tokyo'
                }
                destination_city = iata_to_city.get(dest_code, trip_details.get('destination', 'unknown'))
            
            # Final fallback
            if not destination_city:
                destination_city = trip_details.get('destination', 'unknown')
            
            self.log(f"📍 Destination city for Phase 2: {destination_city}")
            
            # Get hotel location for proximity
            hotel_location = final_hotel.get('name', destination_city)
            self.log(f"📍 Hotel location for proximity: {hotel_location}")
            
            # Step 1: Auto-select restaurants
            self.log("🍽️  Phase 2: Auto-selecting restaurants...")
            restaurant_params = {
                'city': destination_city,
                'proximity_location': hotel_location,
                'max_results': 20,  # STEP 2 FIX: Was 10, now 20
                'departure_date': trip_details.get('departure_date'),
                'return_date': trip_details.get('return_date')   
            }
            
            self.log(f"🔍 Restaurant search params: city={destination_city}, proximity={hotel_location}, max={restaurant_params['max_results']}")
            
            restaurant_result = self.restaurant_agent.execute(restaurant_params)
            
            if restaurant_result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                restaurants = restaurant_result.get('recommended_restaurants', [])
                self.all_results['final_restaurant'] = {
                    'recommended_restaurants': restaurants,
                    'summary': restaurant_result.get('recommendation_summary', '')
                }
                self.log(f"✅ Restaurant auto-selected: {len(restaurants)} restaurants found")
            elif restaurant_result.get('status_code') == SUCCESS:
                self.all_results['final_restaurant'] = restaurant_result.get('final_restaurant', {})
                restaurants = [restaurant_result.get('final_restaurant', {})]
                self.log(f"✅ Restaurant auto-selected")
            else:
                self.log("⚠️  Restaurant selection incomplete, using partial results", "WARN")
                restaurants = restaurant_result.get('recommended_restaurants', [])
                self.all_results['final_restaurant'] = {'recommended_restaurants': restaurants}
            
            # Step 2: Auto-select attractions
            self.log("🎭 Phase 2: Auto-selecting attractions...")
            attraction_params = {
                'city': destination_city,
                'proximity_location': hotel_location,
                'max_results': 20,  # STEP 2 FIX: Was 10, now 20
                'departure_date': trip_details.get('departure_date'),
                'return_date': trip_details.get('return_date')
            }
            
            self.log(f"🔍 Attraction search params: city={destination_city}, proximity={hotel_location}, max={attraction_params['max_results']}")
            
            attraction_result = self.attractions_agent.execute(attraction_params)
            
            if attraction_result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                attractions = attraction_result.get('recommended_attractions', [])
                self.all_results['final_attraction'] = {
                    'recommended_attractions': attractions,
                    'summary': attraction_result.get('recommendation_summary', '')
                }
                self.log(f"✅ Attraction auto-selected: {len(attractions)} attractions found")
            elif attraction_result.get('status_code') == SUCCESS:
                self.all_results['final_attraction'] = attraction_result.get('final_attraction', {})
                attractions = [attraction_result.get('final_attraction', {})]
                self.log(f"✅ Attraction auto-selected")
            else:
                self.log("⚠️  Attraction selection incomplete, using partial results", "WARN")
                attractions = attraction_result.get('recommended_attractions', [])
                self.all_results['final_attraction'] = {'recommended_attractions': attractions}
            
            # Step 3: Generate itinerary
            self.log("📅 Phase 2: Generating itinerary...")
            
            itinerary_params = {
                'destination': destination_city,
                'departure_date': trip_details.get('departure_date'),
                'return_date': trip_details.get('return_date'),
                'final_flight': final_flight,
                'final_hotel': final_hotel,
                'restaurants': restaurants,
                'attractions': attractions,
                'trip_summary': trip_details.get('user_prompt', '')
            }
            
            self.log(f"📊 Itinerary generation: {len(restaurants)} restaurants, {len(attractions)} attractions")
            
            itinerary_result = self.itinerary_agent.execute(itinerary_params)
            
            if itinerary_result.get('success'):
                self.all_results['itinerary'] = itinerary_result
                self.log("✅ Phase 2 complete!")
                return {"status": "success", "data": itinerary_result}
            else:
                self.log("❌ Itinerary generation failed", "ERROR")
                return {"status": "error", "error": "Itinerary generation failed"}
                
        except Exception as e:
            self.log(f"❌ Phase 2 error: {str(e)}", "ERROR")
            import traceback
            traceback.print_exc()
            return {"status": "error", "error": str(e)}

    # =========================================================================
    # TOOL WRAPPER METHODS
    # =========================================================================

    def _tool_flight_search(self, params: FlightSearch) -> Dict[str, Any]:
        """Triggers FlightAgent (Phase 1)."""
        result = self._execute_phase1_agent(
            self.flight_agent,
            params.model_dump(),
            "FlightAgent",
            "flight"
        )
        
        if result.get('status') == 'awaiting_user_input':
            return result
        elif result.get('status') == 'success':
            self.all_results['final_flight'] = result['result'].get('final_flight')
            return {"success": True, "message": "Flight secured"}
        else:
            return {"success": False, "error": "Flight search failed"}

    def _tool_hotel_search(self, params: HotelSearch) -> Dict[str, Any]:
        """Triggers HotelAgent (Phase 1)."""
        result = self._execute_phase1_agent(
            self.hotel_agent,
            params.model_dump(),
            "HotelAgent",
            "hotel"
        )
        
        if result.get('status') == 'awaiting_user_input':
            return result
        elif result.get('status') == 'success':
            self.all_results['final_hotel'] = result['result'].get('final_hotel')
            return {"success": True, "message": "Hotel secured"}
        else:
            return {"success": False, "error": "Hotel search failed"}

    def _tool_restaurant_search(self, params: RestaurantSearch) -> Dict[str, Any]:
        """Phase 2 only - called automatically."""
        return {"success": True, "message": "Restaurant will be auto-selected in Phase 2"}

    def _tool_attractions_search(self, params: AttractionsSearch) -> Dict[str, Any]:
        """Phase 2 only - called automatically."""
        return {"success": True, "message": "Attractions will be auto-selected in Phase 2"}

    # =========================================================================
    # PUBLIC ENTRY POINTS
    # =========================================================================

    def execute(self, user_prompt: str, clarification_response: Optional[str] = None, max_turns: int = 10) -> Dict[str, Any]:
        """
        STEP 3: Main entry point with intelligent clarification support.
        
        Args:
            user_prompt: Initial user vacation request
            clarification_response: User's answers to clarification questions (if any)
            max_turns: Max LLM conversation turns
            
        Returns:
            - If clarification needed: {"status": "clarification_needed", "questions": [...]}
            - If ready for Phase 1: {"status": "awaiting_user_input", "agent": "FlightAgent", ...}
            - If error: {"success": False, "error": "..."}
        """
        
        # STEP 3: Combine prompt with clarification if provided
        if clarification_response:
            full_prompt = f"""ORIGINAL REQUEST: {user_prompt}

ADDITIONAL INFORMATION PROVIDED: {clarification_response}

Now proceed with planning using all the information above."""
            self.log("📥 Processing clarification response...")
        else:
            full_prompt = user_prompt
        
        self.log(f"Starting TWO-PHASE orchestration: {full_prompt[:100]}...")
        
        # Parse user prompt with LLM
        chat = self.model.start_chat()
        response = chat.send_message(full_prompt)
        
        # Extract function calls
        current_function_calls = []
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    current_function_calls.append(part.function_call)
        
        if not current_function_calls:
            return {"success": False, "error": "Could not parse trip request"}
        
        # Execute first tool
        func_call = current_function_calls[0]
        tool_name = func_call.name
        tool_args = self._convert_proto_to_dict(func_call.args)
        
        # STEP 3: Check if LLM is requesting clarification
        if tool_name == "RequestClarification":
            self.log("⏸️  LLM requests clarification from user")
            return self._tool_request_clarification(RequestClarification(**tool_args))
        
        # Otherwise proceed with Phase 1
        self.log(f"🎯 Phase 1: Starting with {tool_name}")
        
        # Store trip details for Phase 2
        self.trip_details = tool_args.copy()
        self.trip_details['user_prompt'] = user_prompt
        
        try:
            result = self._execute_orchestrator_tool(tool_name, tool_args)
            
            # Check if paused for HIL
            if result.get('status') == 'awaiting_user_input':
                return {
                    "status": "awaiting_user_input",
                    "session_id": None,
                    "agent": result.get('agent'),
                    "item_type": result.get('item_type'),
                    "recommendations": result.get('recommendations', []),
                    "summary": result.get('summary', ''),
                    "session_state": {
                        "result": result,
                        "trip_details": self.trip_details,
                        "current_phase": "FLIGHT"
                    }
                }
            
            return {"success": False, "error": "Unexpected result from FlightAgent"}
            
        except Exception as e:
            self.log(f"❌ Orchestration error: {str(e)}", "ERROR")
            return {"success": False, "error": str(e)}

    def resume(self, session_state: Dict[str, Any], user_decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resume orchestration after user makes a choice.
        """
        self.log("▶️  Resuming TWO-PHASE orchestration...")
        
        current_phase = session_state.get('current_phase', 'FLIGHT')
        hil_result = session_state.get('result', {})
        trip_details = session_state.get('trip_details', {})
        
        agent_name = hil_result.get('agent')
        item_name = hil_result.get('item_type')
        
        # Get agent
        agent = self.flight_agent if agent_name == "FlightAgent" else self.hotel_agent
        
        # Resume the agent
        result = self._resume_phase1_agent(agent, hil_result, user_decision, agent_name, item_name)
        
        # Check if pausing again (refinement)
        if result.get('status') == 'awaiting_user_input':
            return {
                "status": "awaiting_user_input",
                "agent": result.get('agent'),
                "item_type": result.get('item_type'),
                "recommendations": result.get('recommendations', []),
                "summary": result.get('summary', ''),
                "session_state": {
                    "result": result,
                    "trip_details": trip_details,
                    "current_phase": current_phase
                }
            }
        
        # Agent completed
        if result.get('status') == 'success':
            # Store result
            if agent_name == "FlightAgent":
                self.all_results['final_flight'] = result['result'].get('final_flight')
                self.log("✅ Flight secured! Moving to HotelAgent...")
                
                # Start HotelAgent
                hotel_params = {
                    'city': trip_details.get('destination'),
                    'check_in_date': trip_details.get('departure_date'),
                    'check_out_date': trip_details.get('return_date')
                }
                
                hotel_result = self._execute_phase1_agent(
                    self.hotel_agent,
                    hotel_params,
                    "HotelAgent",
                    "hotel"
                )
                
                if hotel_result.get('status') == 'awaiting_user_input':
                    return {
                        "status": "awaiting_user_input",
                        "agent": hotel_result.get('agent'),
                        "item_type": hotel_result.get('item_type'),
                        "recommendations": hotel_result.get('recommendations', []),
                        "summary": hotel_result.get('summary', ''),
                        "session_state": {
                            "result": hotel_result,
                            "trip_details": trip_details,
                            "current_phase": "HOTEL"
                        }
                    }
            
            elif agent_name == "HotelAgent":
                self.all_results['final_hotel'] = result['result'].get('final_hotel')
                self.log("✅ Hotel secured! Starting Phase 2...")
                
                # Execute Phase 2 (automatic)
                phase2_result = self._execute_phase2(trip_details)
                
                if phase2_result.get('status') == 'success':
                    formatted_itinerary = self.all_results.get('itinerary', {}).get('formatted_itinerary', '')
                    
                    self.log(f"📤 Sending formatted itinerary to frontend: {len(formatted_itinerary)} characters")
                    
                    if not formatted_itinerary:
                        self.log("⚠️  WARNING: Empty formatted itinerary!", "ERROR")
                        formatted_itinerary = "Error: Itinerary generation failed"
                    
                    return {
                        "status": "complete",
                        "success": True,
                        "data": formatted_itinerary,
                        "summary": "Complete vacation plan ready!",
                        "all_results": self.all_results
                    }
        
        return {"status": "error", "success": False, "error": "Resume failed"}

    def _execute_orchestrator_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute orchestrator tool with validation."""
        schema = self.tool_schemas.get(tool_name)
        func = self.specialist_tools.get(tool_name)
        if not schema or not func:
            raise ValueError(f"Unknown tool: {tool_name}")
        validated_args = schema(**tool_args)
        return func(validated_args)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _build_system_instruction(self) -> str:
        """STEP 3: System instruction with intelligent clarification guidance."""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        return f"""You are an intelligent vacation planning orchestrator.

CONTEXT:
- Current date: {current_date}
- All travel dates MUST be in the future

REQUIRED INFORMATION to start planning:
1. origin - Departure city/airport (where departing from)
2. destination - Arrival city/airport (where going to)
3. departure_date - Travel start date (YYYY-MM-DD format, MUST be future)
4. return_date - Travel end date (YYYY-MM-DD format, MUST be after departure)

OPTIONAL PREFERENCES (ask based on context - use judgment):
- If user mentions FOOD/RESTAURANTS → Ask about dietary restrictions, cuisine preferences
- If user mentions HOTELS/ACCOMMODATION → Ask about amenities (pool, gym, city center)
- If user mentions BUDGET → Confirm budget constraints
- If user mentions ACTIVITIES → Ask about interests (museums, outdoor, nightlife)

YOUR WORKFLOW:

1. Analyze the user's prompt carefully
2. Check if you have ALL REQUIRED fields with valid future dates
3. Consider if OPTIONAL preferences would significantly improve planning
4. If missing REQUIRED info OR year is ambiguous OR dates might be in past:
   → Call RequestClarification
   → Ask about REQUIRED fields first
   → Then ask about context-relevant OPTIONAL preferences
   → Generate clear, conversational questions (not robotic)
   → Keep total questions to 3-5 max

5. If you have complete, valid information:
   → Call FlightSearch to start Phase 1

CRITICAL RULES:
- NEVER assume year if ambiguous (ask "December 2025 or 2026?")
- NEVER use past dates - validate against current date: {current_date}
- ALWAYS ask rather than guess when information is vague
- Generate natural questions, avoid robotic phrasing
- If user already mentioned preferences, DON'T ask again

EXAMPLES:

User: "Trip to Madrid in December for 5 days"
→ Missing: origin, exact dates, year
→ Context: No food/hotel mentions
→ Call RequestClarification with:
   - "Where will you be departing from?"
   - "Which December - 2025 or 2026?"
   - "What are your exact travel dates? (e.g., December 10-15)"

User: "Trip to Madrid in December, love tapas and traditional food"
→ Missing: origin, exact dates, year
→ Context: User mentioned food
→ Call RequestClarification with:
   - "Where will you be departing from?"
   - "Which December - 2025 or 2026? What are your exact dates?"
   - "Since you love traditional food, any dietary restrictions? (e.g., vegetarian, vegan, gluten-free)"

User: "Santander to Madrid, Dec 10-16, 2025, vegan options, 4-star hotels with gym"
→ Has: All REQUIRED fields + preferences
→ Dates are valid (future)
→ Call FlightSearch immediately with: origin="Santander", destination="Madrid", departure_date="2025-12-10", return_date="2025-12-16"

Remember: You ONLY call FlightSearch initially. The system handles hotels, restaurants, attractions automatically."""

    def _convert_proto_to_dict(self, proto_map) -> Dict[str, Any]:
        """Convert protobuf map to dict."""
        return dict(proto_map)

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize property schema for Gemini."""
        sanitized = prop_schema.copy()
        if 'anyOf' in sanitized:
            for item in sanitized['anyOf']:
                if 'type' in item and item['type'] != 'null':
                    sanitized.update(item)
                    break
            del sanitized['anyOf']
        if 'default' in sanitized: del sanitized['default']
        if 'title' in sanitized: del sanitized['title']
        if '$defs' in sanitized: del sanitized['$defs']
        if 'type' in sanitized and isinstance(sanitized['type'], str):
            sanitized['type'] = sanitized['type'].upper()
        if sanitized.get('type') == 'ARRAY' and sanitized.get('items'):
            sanitized['items'] = self._sanitize_property_schema(sanitized['items'])
        if sanitized.get('type') == 'OBJECT' and sanitized.get('properties'):
            for key, val in sanitized['properties'].items():
                sanitized['properties'][key] = self._sanitize_property_schema(val)
        return sanitized

    def _pydantic_to_function_declaration(self, pydantic_model) -> Dict[str, Any]:
        """Convert Pydantic to function declaration."""
        schema = pydantic_model.model_json_schema()
        name = pydantic_model.__name__
        description = schema.get("description", f"Tool for {name}")
        definitions = schema.get("$defs", {})
        required_params = schema.get("required", [])

        sanitized_properties = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            if prop_schema.get('$ref'):
                ref_name = prop_schema['$ref'].split('/')[-1]
                nested_schema = definitions.get(ref_name, {})
                sanitized_nested_props = {
                    n_name: self._sanitize_property_schema(n_prop)
                    for n_name, n_prop in nested_schema.get('properties', {}).items()
                }
                param_schema = {
                    "type": "OBJECT",
                    "properties": sanitized_nested_props,
                    "required": nested_schema.get("required", [])
                }
            else:
                param_schema = self._sanitize_property_schema(prop_schema)
            sanitized_properties[prop_name] = param_schema
        
        return {
            "name": name,
            "description": description,
            "parameters": {"type": "OBJECT", "properties": sanitized_properties, "required": required_params}
        }

    def _create_gemini_tools(self) -> List:
        """STEP 3: Create Gemini tool declarations - includes RequestClarification."""
        tool_list = [RequestClarification, FlightSearch, HotelSearch, RestaurantSearch, AttractionsSearch, GenerateItinerary]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        return tools