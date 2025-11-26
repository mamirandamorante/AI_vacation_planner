"""
Orchestrator Agent - TWO-PHASE HIL VERSION
==========================================
Phase 1: User chooses flight and hotel (HIL)
Phase 2: System auto-selects restaurants/attractions/itinerary

This is simpler, more reliable, and provides better UX.
"""

import json
from typing import Dict, Any, List, Optional
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
        """Initialize OrchestratorAgent with two-phase HIL."""
        super().__init__("OrchestratorAgent", gemini_api_key)
        
        # Store specialist agents
        self.flight_agent = flight_agent
        self.hotel_agent = hotel_agent
        self.restaurant_agent = restaurant_agent
        self.attractions_agent = attractions_agent
        self.itinerary_agent = itinerary_agent
        
        # Tool execution mapping
        self.specialist_tools = {
            "FlightSearch": self._tool_flight_search,
            "HotelSearch": self._tool_hotel_search,
            "RestaurantSearch": self._tool_restaurant_search,
            "AttractionsSearch": self._tool_attractions_search,
            "GenerateItinerary": itinerary_agent.execute,
        }

        # Pydantic schema mapping
        self.tool_schemas = {
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
        self.log("✅ OrchestratorAgent initialized with TWO-PHASE HIL")

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
            self.log(f"⏸️ {agent_name} paused for user input")
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
        self.log(f"▶️ Phase 1: Resuming {agent_name}...")
        
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
    # PHASE 2: AUTOMATED COMPLETION (NO HIL) - FIXED TO EXTRACT FORMATTED TEXT
    # =========================================================================

    def _execute_phase2(self, trip_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Phase 2: Automatically select restaurants, attractions, and generate itinerary.
        
        FIXED: Now properly extracts formatted_itinerary text for frontend display.
        """
        self.log("🚀 Phase 2: Auto-completing restaurants, attractions, and itinerary...")
        
        try:
            # Extract Phase 1 results
            final_flight = self.all_results.get('final_flight', {})
            final_hotel = self.all_results.get('final_hotel', {})
            
            destination_city = trip_details.get('destination', 'unknown')
            hotel_location = final_hotel.get('name', destination_city)
            
            # Step 1: Auto-select restaurants near hotel
            self.log("🍽️ Phase 2: Auto-selecting restaurants...")
            restaurant_params = {
                'city': destination_city,
                'proximity_location': hotel_location,
                'max_results': 10,
                'departure_date': trip_details.get('departure_date'),
                'return_date': trip_details.get('return_date')   
            }
            restaurant_result = self.restaurant_agent.execute(restaurant_params)
            
            # Extract recommendations (agent returns HIL_PAUSE but we ignore it)
            if restaurant_result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                self.all_results['final_restaurant'] = {
                    'recommended_restaurants': restaurant_result.get('recommended_restaurants', []),
                    'summary': restaurant_result.get('recommendation_summary', '')
                }
                self.log("✅ Restaurant auto-selected")
            elif restaurant_result.get('status_code') == SUCCESS:
                self.all_results['final_restaurant'] = restaurant_result.get('final_restaurant', {})
                self.log("✅ Restaurant auto-selected")
            
            # Step 2: Auto-select attractions near hotel
            self.log("🎭 Phase 2: Auto-selecting attractions...")
            attraction_params = {
                'city': destination_city,
                'proximity_location': hotel_location,
                'max_results': 10,
                'departure_date': trip_details.get('departure_date'),
                'return_date': trip_details.get('return_date')
            }
            attraction_result = self.attractions_agent.execute(attraction_params)
            
            # Extract recommendations (agent returns HIL_PAUSE but we ignore it)
            if attraction_result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                self.all_results['final_attraction'] = {
                    'recommended_attractions': attraction_result.get('recommended_attractions', []),
                    'summary': attraction_result.get('recommendation_summary', '')
                }
                self.log("✅ Attraction auto-selected")
            elif attraction_result.get('status_code') == SUCCESS:
                self.all_results['final_attraction'] = attraction_result.get('final_attraction', {})
                self.log("✅ Attraction auto-selected")
            
            # Step 3: Generate itinerary with real data
            self.log("📅 Phase 2: Generating itinerary...")
            
            # Extract collected data
            restaurants = self.all_results.get('final_restaurant', {}).get('recommended_restaurants', [])
            attractions = self.all_results.get('final_attraction', {}).get('recommended_attractions', [])
            
            self.log(f"📊 Passing to ItineraryAgent: {len(restaurants)} restaurants, {len(attractions)} attractions")
            
            itinerary_params = {
                'trip_summary': f"Trip to {destination_city} from {trip_details.get('departure_date')} to {trip_details.get('return_date')}",
                'departure_date': trip_details.get('departure_date'),
                'return_date': trip_details.get('return_date'),
                'destination': destination_city,
                'restaurants': restaurants,
                'attractions': attractions,
                'final_hotel': final_hotel,
                'final_flight': final_flight 
            }
            itinerary_result = self.itinerary_agent.execute(itinerary_params)
            
            # DEBUG: Log what we received
            self.log(f"🔍 DEBUG: Itinerary result keys: {list(itinerary_result.keys())}")
            self.log(f"🔍 DEBUG: Has formatted_itinerary: {'formatted_itinerary' in itinerary_result}")
            
            # CRITICAL FIX: Extract the formatted_itinerary text
            formatted_text = itinerary_result.get('formatted_itinerary', '')
            if not formatted_text:
                self.log("⚠️ WARNING: No formatted_itinerary found in result!", "WARN")
                formatted_text = "Itinerary generation incomplete"
            
            self.log(f"✅ Extracted formatted itinerary: {len(formatted_text)} characters")
            
            # Store both the itinerary data AND the formatted text
            self.all_results['itinerary'] = {
                'success': True,
                'itinerary': itinerary_result.get('itinerary', []),
                'formatted_itinerary': formatted_text,  # THIS IS THE KEY LINE!
                'summary': itinerary_result.get('recommendation_summary', '')
            }
            
            self.log("✅ Phase 2 complete!")
            return {"status": "success"}
            
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

    def execute(self, user_prompt: str, max_turns: int = 10) -> Dict[str, Any]:
        """
        Main entry point - starts Phase 1 (Flight selection).
        """
        self.log(f"Starting TWO-PHASE orchestration: {user_prompt}")
        
        # Parse user prompt with LLM to extract trip details
        chat = self.model.start_chat()
        response = chat.send_message(user_prompt)
        
        # Extract function calls
        current_function_calls = []
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    current_function_calls.append(part.function_call)
        
        if not current_function_calls:
            return {"success": False, "error": "Could not parse trip request"}
        
        # Execute first tool (should be FlightSearch)
        func_call = current_function_calls[0]
        tool_name = func_call.name
        tool_args = self._convert_proto_to_dict(func_call.args)
        
        self.log(f"🎯 Phase 1: Starting with {tool_name}")
        
        # Store trip details for Phase 2
        self.trip_details = tool_args.copy()
        
        try:
            result = self._execute_orchestrator_tool(tool_name, tool_args)
            
            # Check if paused for HIL
            if result.get('status') == 'awaiting_user_input':
                return {
                    "status": "awaiting_user_input",
                    "session_id": None,  # Will be created by main.py
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
        
        TWO-PHASE LOGIC:
        1. If resuming FlightAgent → Complete flight, then start HotelAgent
        2. If resuming HotelAgent → Complete hotel, then execute Phase 2
        
        FIXED: Now properly passes formatted_itinerary to frontend as 'data'
        """
        self.log("▶️ Resuming TWO-PHASE orchestration...")
        
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
                    # CRITICAL FIX: Extract formatted itinerary for frontend
                    formatted_itinerary = self.all_results.get('itinerary', {}).get('formatted_itinerary', '')
                    
                    self.log(f"📤 Sending formatted itinerary to frontend: {len(formatted_itinerary)} characters")
                    
                    if not formatted_itinerary:
                        self.log("⚠️ WARNING: Empty formatted itinerary!", "ERROR")
                        formatted_itinerary = "Error: Itinerary generation failed"
                    
                    return {
                        "status": "complete",
                        "success": True,
                        "data": formatted_itinerary,  # THIS IS WHAT THE FRONTEND NEEDS!
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
        """System instruction for two-phase orchestration."""
        return """You are the Orchestrator Agent for a vacation planning system.

YOUR JOB:
1. Parse the user's vacation request
2. Extract: origin, destination, departure_date, return_date, passengers, budget
3. Call FlightSearch with these parameters

CRITICAL:
- You ONLY call FlightSearch initially
- The system handles HotelSearch, RestaurantSearch, AttractionsSearch, and GenerateItinerary automatically
- Extract all trip details accurately from the user's prompt"""

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
        """Create Gemini tool declarations."""
        tool_list = [FlightSearch, HotelSearch, RestaurantSearch, AttractionsSearch, GenerateItinerary]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        return tools
