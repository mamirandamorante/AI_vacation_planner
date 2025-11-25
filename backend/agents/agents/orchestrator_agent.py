"""
Orchestrator Agent - Enhanced for Production-Grade Specialist Agents
====================================================================
Coordinates all specialist agents with HIL (Human-in-the-Loop) support.
FIXED: Continuation messages now preserve original search context.
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
# BASE AGENT (Required for context)
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
# ORCHESTRATOR TOOL SCHEMAS (Enhanced for Production)
# =============================================================================

class FlightSearch(BaseModel):
    """Tool schema for triggering FlightAgent."""
    origin: str = Field(..., description="Origin airport code or city (e.g., 'SFO', 'San Francisco').")
    destination: str = Field(..., description="Destination airport code or city (e.g., 'CDG', 'Paris').")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format.")
    return_date: str = Field(..., description="Return date in YYYY-MM-DD format.")

class HotelSearch(BaseModel):
    """Tool schema for triggering HotelAgent."""
    city: str = Field(..., description="City for hotel search (e.g., 'Paris').")
    check_in_date: str = Field(..., description="Check-in date in YYYY-MM-DD format.")
    check_out_date: str = Field(..., description="Check-out date in YYYY-MM-DD format.")

class RestaurantSearchConstraints(BaseModel):
    """Production-grade filtering constraints for restaurant search."""
    min_rating: Optional[float] = Field(4.0, description="Minimum rating (e.g., 4.5).")
    price_level: Optional[int] = Field(None, description="Price level 1-4 (1=Cheap, 4=Very Expensive).")
    cuisine_types: List[str] = Field(default_factory=list, description="Cuisines (e.g., ['italian', 'japanese']).")
    dietary_restrictions: List[str] = Field(default_factory=list, description="Dietary needs (e.g., ['vegetarian', 'vegan']).")
    atmosphere: List[str] = Field(default_factory=list, description="Desired vibe (e.g., ['romantic', 'family_friendly']).")
    open_now: Optional[bool] = Field(None, description="Only return currently open restaurants.")

class RestaurantSearch(BaseModel):
    """Enhanced tool schema for triggering RestaurantAgent."""
    city: str = Field(..., description="City for restaurant search (e.g., 'Paris').")
    constraints: RestaurantSearchConstraints = Field(default_factory=RestaurantSearchConstraints, description="Filtering constraints for restaurant search.")
    proximity_location: Optional[str] = Field(None, description="Landmark or hotel name to prioritize nearby results.")
    target_datetime: Optional[str] = Field(None, description="Target visit date/time (ISO 8601 or YYYY-MM-DD HH:MM).")
    max_results: int = Field(15, description="Maximum restaurants to search (default: 15).")

class AttractionsSearchConstraints(BaseModel):
    """Production-grade filtering constraints for attraction search."""
    min_rating: Optional[float] = Field(4.0, description="Minimum rating (e.g., 4.5).")
    attraction_types: List[str] = Field(default_factory=list, description="Attraction categories (e.g., ['museum', 'park']).")
    interests: List[str] = Field(default_factory=list, description="User interests (e.g., ['art', 'history']).")
    max_entry_fee: Optional[float] = Field(None, description="Maximum entry fee (e.g., 50.0).")
    is_indoor_outdoor: Optional[str] = Field(None, description="Filter for 'indoor' or 'outdoor'.")
    wheelchair_accessible: Optional[bool] = Field(None, description="Filter for wheelchair accessibility.")

class AttractionsSearch(BaseModel):
    """Enhanced tool schema for triggering AttractionsAgent."""
    city: str = Field(..., description="City for attraction search (e.g., 'Tokyo').")
    constraints: AttractionsSearchConstraints = Field(default_factory=AttractionsSearchConstraints, description="Filtering constraints for attraction search.")
    proximity_location: Optional[str] = Field(None, description="Landmark or hotel to prioritize nearby results.")
    target_date: Optional[str] = Field(None, description="Target visit date (YYYY-MM-DD) to check opening hours.")
    max_results: int = Field(15, description="Maximum attractions to search (default: 15).")

class GenerateItinerary(BaseModel):
    """Tool schema for triggering ItineraryAgent."""
    trip_summary: str = Field(..., description="Brief summary of finalized trip parameters.")

# =============================================================================
# ORCHESTRATOR AGENT (Enhanced HIL Coordination)
# =============================================================================

class OrchestratorAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str, flight_agent, hotel_agent, restaurant_agent, attractions_agent, itinerary_agent):
        """
        Initialize OrchestratorAgent with all specialist agents.
        
        Args:
            gemini_api_key: Google Gemini API key
            flight_agent: FlightAgent instance
            hotel_agent: HotelAgent instance
            restaurant_agent: RestaurantAgent instance (production-grade)
            attractions_agent: AttractionsAgent instance (production-grade)
            itinerary_agent: ItineraryAgent instance
        """
        super().__init__("OrchestratorAgent", gemini_api_key)
        
        # Store specialist agents
        self.flight_agent = flight_agent
        self.hotel_agent = hotel_agent
        self.restaurant_agent = restaurant_agent
        self.attractions_agent = attractions_agent
        self.itinerary_agent = itinerary_agent
        
        # Tool execution mapping - Now using HIL wrappers for all agents
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
        self.all_results['FlightAgent_HIL_TURN_COUNT'] = 0
        self.all_results['HotelAgent_HIL_TURN_COUNT'] = 0
        self.all_results['RestaurantAgent_HIL_TURN_COUNT'] = 0
        self.all_results['AttractionsAgent_HIL_TURN_COUNT'] = 0
        
        # Build system instruction and tools
        self.system_instruction = self._build_system_instruction()
        self.gemini_tools = self._create_gemini_tools()

        # Initialize Gemini model
        self.model = genai.GenerativeModel(
            'gemini-2.5-flash',
            tools=self.gemini_tools,
            system_instruction=self.system_instruction,
            generation_config={'temperature': 0.7}
        )
        self.log("✅ OrchestratorAgent initialized with HIL support for all 4 specialist agents")

    # =========================================================================
    # HIL EXECUTION WRAPPER (Manages pause/resume for any agent)
    # =========================================================================

    def _execute_hil_agent_with_loop(self, agent, initial_params: Dict[str, Any], agent_name: str, item_name: str) -> Dict[str, Any]:
        """
        Manages the Human-in-the-Loop (HIL) pause and resume cycle for a specialist agent.
        
        FIXED: Continuation messages now include original search context to prevent LLM hallucination.
        
        Args:
            agent: The specialist agent instance (FlightAgent, HotelAgent, etc.)
            initial_params: Initial search parameters
            agent_name: Name of agent for logging (e.g., "FlightAgent")
            item_name: Item type for human interaction (e.g., "flight", "hotel")
            
        Returns:
            Final result dict with status_code (SUCCESS or error)
        """
        turn_count = 0
        max_hil_turns = 5
        continuation_message = None
        
        while turn_count < max_hil_turns:
            turn_count += 1
            self.log(f"🔗 HIL Loop Turn {turn_count} for {agent_name}...")
            
            # Call the agent (initial or continuation)
            if turn_count == 1:
                result = agent.execute(initial_params, continuation_message=None)
            else:
                result = agent.execute(initial_params, continuation_message=continuation_message)
            
            status = result.get('status_code')
            
            # HIL PAUSE: Agent needs human input
            if status == HIL_PAUSE_REQUIRED:
                self.log(f"⏸️ {agent_name} requires Human-in-the-Loop input. Pausing Orchestrator.")
                
                # Extract recommendations
                recommendations = result.get(f'recommended_{item_name}s', [])
                
                # SIMULATE human interaction (in production, this would be real UI)
                human_decision = self._simulate_human_interaction(agent_name, recommendations, item_name)
                
                # CRITICAL FIX: Preserve original search context in continuation message
                continuation_message = self._build_continuation_message(
                    human_decision, 
                    initial_params, 
                    agent_name
                )
                
                # Check if human made final choice
                if human_decision.get('status') == FINAL_CHOICE:
                    self.log(f"✅ Human finalized {item_name} selection. Resuming {agent_name}...")
                    final_result = agent.execute(initial_params, continuation_message=continuation_message)
                    return final_result
                
                # Human wants refinement
                elif human_decision.get('status') == REFINE_SEARCH:
                    self.log(f"🔄 Human requested refinement: {human_decision.get('feedback')}")
                    continue
                
            # SUCCESS: Agent completed successfully
            elif status == SUCCESS:
                self.log(f"✅ {agent_name} successfully finalized the {item_name} selection.")
                return result
            
            # ERROR or other status
            else:
                self.log(f"❌ {agent_name} returned unexpected status: {status}", "ERROR")
                return result
        
        # Max turns reached
        self.log(f"⚠️ {agent_name} reached maximum HIL turns ({max_hil_turns}). Forcing completion.", "WARN")
        return {"success": False, "status_code": "HIL_MAX_TURNS_EXCEEDED", "summary": f"{agent_name} exceeded HIL turn limit."}

    def _build_continuation_message(self, human_decision: Dict[str, Any], initial_params: Dict[str, Any], agent_name: str) -> Dict[str, Any]:
        """
        CRITICAL FIX: Build continuation message that includes BOTH human feedback AND original search context.
        
        This prevents the LLM from hallucinating new search parameters.
        
        Args:
            human_decision: Human's decision (refinement feedback or final choice)
            initial_params: Original search parameters to preserve
            agent_name: Name of the agent
            
        Returns:
            Enhanced continuation message with context preservation
        """
        # Build context reminder based on agent type - ALWAYS include for all message types
        if agent_name == "FlightAgent":
            context = f"CONTEXT: You are searching for flights from {initial_params.get('origin')} to {initial_params.get('destination')}, departing {initial_params.get('departure_date')}, returning {initial_params.get('return_date')}."
        elif agent_name == "HotelAgent":
            context = f"CONTEXT: You are searching for hotels in {initial_params.get('city')}, check-in {initial_params.get('check_in_date')}, check-out {initial_params.get('check_out_date')}, for {initial_params.get('adults', 2)} adults."
        elif agent_name == "RestaurantAgent":
            context = f"CONTEXT: You are searching for restaurants in {initial_params.get('city')}."
        elif agent_name == "AttractionsAgent":
            context = f"CONTEXT: You are searching for attractions in {initial_params.get('city')}."
        else:
            context = "CONTEXT: Continue with the original search parameters."
        
        # Combine context with human feedback
        if human_decision.get('status') == REFINE_SEARCH:
            feedback = human_decision.get('feedback', '')
            content = f"{context}\n\nHuman feedback: {feedback}\n\nModify your search strategy accordingly while maintaining the original search location and dates."
        elif human_decision.get('status') == FINAL_CHOICE:
            selection_key = [k for k in human_decision.keys() if k.endswith('_id')]
            selection_id = human_decision.get(selection_key[0]) if selection_key else 'unknown'
            
            # Use EXACT trigger phrase from system instruction
            if agent_name == "FlightAgent":
                content = f"{context}\n\nFINAL_CHOICE_TRIGGER: The human selected flight ID '{selection_id}'. Call FinalizeSelection now with selected_flight_id='{selection_id}' and a confirmation message."
            elif agent_name == "HotelAgent":
                content = f"{context}\n\nFINAL_CHOICE_TRIGGER: The human selected hotel ID '{selection_id}'. Call FinalizeSelection now with selected_hotel_id='{selection_id}' and a confirmation message."
            else:
                content = f"{context}\n\nFINAL_CHOICE_TRIGGER: Human selected ID: {selection_id}. Finalize this selection."
        else:
            content = f"{context}\n\n{human_decision.get('feedback', 'Continue.')}"
        
        return {
            **human_decision,  # Preserve original decision structure
            'content': content,  # Add context-aware content
            'original_params': initial_params  # Include original params for reference
        }

    def _simulate_human_interaction(self, agent_name: str, recommendations: List[Dict[str, Any]], item_name: str) -> Dict[str, Any]:
        """
        SIMULATED function to pause and receive user input.
        In production, this would connect to a real UI/API for human decisions.
        
        Args:
            agent_name: Name of the agent requesting input
            recommendations: List of recommended items from agent
            item_name: Type of item (flight, hotel, restaurant, attraction)
            
        Returns:
            Human decision dict with status (FINAL_CHOICE or REFINE_SEARCH)
        """
        self.log("\n" + "="*50)
        self.log(f"👤 HUMAN INPUT REQUIRED for {agent_name} ({item_name.upper()})")
        self.log("="*50)

        if not recommendations:
            self.log("❗ Agent returned no recommendations. Forcing refinement...")
            return {'status': REFINE_SEARCH, 'feedback': 'No options were found. Please broaden the search criteria.'}

        # --- SIMULATION LOGIC (Turn-based refinement for FlightAgent only) ---
        
        if agent_name == "FlightAgent":
            if self.all_results['FlightAgent_HIL_TURN_COUNT'] == 0:
                self.all_results['FlightAgent_HIL_TURN_COUNT'] = 1
                feedback = "The flight is too expensive, re-search with a maximum budget of $1500 per person."
                self.log(f"Simulating Human Action (Turn 1): Refinement: {feedback}")
                return {'status': REFINE_SEARCH, 'feedback': feedback}
            else:
                selection_id = recommendations[0]['id'] if recommendations else "FL003"
                self.log(f"Simulating Human Action (Turn 2): Final Selection: {selection_id}")
                return {'status': FINAL_CHOICE, 'flight_id': selection_id}

        elif agent_name == "HotelAgent":
            selection_id = recommendations[0]['id'] if recommendations else "HT001"
            self.log(f"Simulating Human Action: Final Selection: {selection_id}")
            return {'status': FINAL_CHOICE, 'hotel_id': selection_id}
        
        elif agent_name == "RestaurantAgent":
            selection_id = recommendations[0]['id'] if recommendations else "REST001"
            self.log(f"Simulating Human Action: Final Selection: {selection_id}")
            return {'status': FINAL_CHOICE, 'restaurant_id': selection_id}
        
        elif agent_name == "AttractionsAgent":
            selection_id = recommendations[0]['id'] if recommendations else "ATTR001"
            self.log(f"Simulating Human Action: Final Selection: {selection_id}")
            return {'status': FINAL_CHOICE, 'attraction_id': selection_id}
            
        else:
            # Fallback for unknown agents
            selection_id = recommendations[0]['id'] if recommendations else "UNKNOWN_ID"
            return {'status': FINAL_CHOICE, f'{item_name}_id': selection_id}

    # =========================================================================
    # TOOL WRAPPER METHODS (HIL Integration Points)
    # =========================================================================

    def _tool_flight_search(self, params: FlightSearch) -> Dict[str, Any]:
        """Triggers the FlightAgent and handles the HIL pause/resume loop."""
        self.log("🚀 Starting FlightAgent execution (HIL enabled)...")
        
        result = self._execute_hil_agent_with_loop(
            self.flight_agent, 
            params.model_dump(), 
            "FlightAgent", 
            "flight"
        )
        
        if result.get('status_code') == SUCCESS:
            self.all_results['final_flight'] = result.get('final_flight')
            return {"success": True, "message": "Final flight secured and stored."}
        else:
            return {"success": False, "error": f"Flight search failed or was inconclusive: {result.get('summary')}"}

    def _tool_hotel_search(self, params: HotelSearch) -> Dict[str, Any]:
        """Triggers the HotelAgent and handles the HIL pause/resume loop."""
        self.log("🏨 Starting HotelAgent execution (HIL enabled)...")
        
        result = self._execute_hil_agent_with_loop(
            self.hotel_agent, 
            params.model_dump(), 
            "HotelAgent", 
            "hotel"
        )
        
        if result.get('status_code') == SUCCESS:
            self.all_results['final_hotel'] = result.get('final_hotel')
            return {"success": True, "message": "Final hotel secured and stored."}
        else:
            return {"success": False, "error": f"Hotel search failed or was inconclusive: {result.get('summary')}"}

    def _tool_restaurant_search(self, params: RestaurantSearch) -> Dict[str, Any]:
        """Triggers the RestaurantAgent and handles the HIL pause/resume loop."""
        self.log("🍽️ Starting RestaurantAgent execution (HIL enabled)...")
        
        result = self._execute_hil_agent_with_loop(
            self.restaurant_agent, 
            params.model_dump(), 
            "RestaurantAgent", 
            "restaurant"
        )
        
        if result.get('status_code') == SUCCESS:
            self.all_results['final_restaurant'] = result.get('final_restaurant')
            return {"success": True, "message": "Final restaurant secured and stored."}
        else:
            return {"success": False, "error": f"Restaurant search failed or was inconclusive: {result.get('summary')}"}

    def _tool_attractions_search(self, params: AttractionsSearch) -> Dict[str, Any]:
        """Triggers the AttractionsAgent and handles the HIL pause/resume loop."""
        self.log("🎭 Starting AttractionsAgent execution (HIL enabled)...")
        
        result = self._execute_hil_agent_with_loop(
            self.attractions_agent, 
            params.model_dump(), 
            "AttractionsAgent", 
            "attraction"
        )
        
        if result.get('status_code') == SUCCESS:
            self.all_results['final_attraction'] = result.get('final_attraction')
            return {"success": True, "message": "Final attraction secured and stored."}
        else:
            return {"success": False, "error": f"Attractions search failed or was inconclusive: {result.get('summary')}"}

    # =========================================================================
    # PUBLIC ENTRY POINT (Main Orchestration Loop)
    # =========================================================================

    def execute(self, user_prompt: str, max_turns: int = 15) -> Dict[str, Any]:
        """
        Main orchestration entry point. Coordinates all specialist agents.
        
        Args:
            user_prompt: User's vacation planning request
            max_turns: Maximum LLM orchestration turns (default: 15)
            
        Returns:
            Complete vacation plan with all selections
        """
        self.log(f"Starting orchestration for: {user_prompt}")
        
        # Start chat with orchestrator LLM
        chat = self.model.start_chat()
        response = chat.send_message(user_prompt)
        
        # Main orchestration loop
        for turn in range(max_turns):
            # Extract function calls from response
            current_function_calls = []
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        current_function_calls.append(part.function_call)
            
            # If no tool calls, orchestrator is done or stuck
            if not current_function_calls:
                final_text = getattr(response, 'text', 'Orchestration complete.')
                self.log(f"✅ Orchestrator completed. Final message: {final_text}")
                return {
                    "success": True,
                    "summary": final_text,
                    "all_results": self.all_results
                }
            
            # Execute each tool call
            tool_results = []
            for func_call in current_function_calls:
                tool_name = func_call.name
                tool_args = self._convert_proto_to_dict(func_call.args)
                
                self.log(f"🤖 Orchestrator LLM called tool: {tool_name} with args: {tool_args}")
                
                try:
                    # Execute the tool
                    result = self._execute_orchestrator_tool(tool_name, tool_args)
                    tool_results.append(self._create_tool_response(func_call, result))
                    
                except Exception as e:
                    self.log(f"❌ Orchestrator tool execution failed for {tool_name}: {e}", "ERROR")
                    error_result = {"success": False, "error": str(e)}
                    tool_results.append(self._create_tool_response(func_call, error_result))
            
            # Send tool results back to orchestrator LLM
            tool_response_content = glm.Content(
                role="function",
                parts=tool_results
            )
            response = chat.send_message(tool_response_content)
        
        # Max turns reached
        self.log(f"⚠️ Orchestrator reached max turns ({max_turns})", "WARN")
        return {
            "success": False,
            "error": "Orchestrator exceeded maximum turns",
            "all_results": self.all_results
        }

    def _execute_orchestrator_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an orchestrator tool with Pydantic validation."""
        schema = self.tool_schemas.get(tool_name)
        func = self.specialist_tools.get(tool_name)

        if not schema or not func:
            raise ValueError(f"Unknown tool or function: {tool_name}")
        
        # Validate arguments with Pydantic
        validated_args = schema(**tool_args)
        
        # Execute the tool
        return func(validated_args)

    # =========================================================================
    # SYSTEM INSTRUCTION & TOOL CONVERSION
    # =========================================================================
    
    def _build_system_instruction(self) -> str:
        """Build the system instruction that guides the orchestrator LLM."""
        return """You are the central Orchestrator Agent for a vacation planning system. Your task is to coordinate specialist agents to create a complete itinerary.

YOUR WORKFLOW:
1. **Analyze** the user request to extract: origin, destination, dates, preferences (dietary, accessibility, atmosphere, etc.)
2. **Call agents sequentially**: FlightSearch → HotelSearch → RestaurantSearch → AttractionsSearch → GenerateItinerary
3. **Pass context between agents**: Use hotel location for RestaurantSearch/AttractionsSearch proximity
4. **Handle ALL specialist tools**: Each specialized search tool manages its own Human-in-the-Loop process - just wait for successful return
5. **Finalize**: When all selections are complete (final_flight, final_hotel, final_restaurant, final_attraction), call GenerateItinerary

ENHANCED FEATURES:
- **RestaurantSearch** supports: dietary restrictions, atmosphere preferences, price levels, proximity to hotel, open_now filtering
- **AttractionsSearch** supports: accessibility requirements, indoor/outdoor preferences, max entry fees, attraction types, proximity to hotel
- **Use proximity_location**: Pass the hotel name/address to RestaurantSearch and AttractionsSearch for better recommendations
- **Use temporal data**: Pass check-in/out dates and times to ensure restaurants/attractions are open

CRITICAL RULES:
- ALWAYS extract user preferences and pass them as constraints
- Use the hotel location as proximity_location for dining/attractions
- All specialist agents handle their own HIL - you just coordinate the sequence
- Call GenerateItinerary ONLY after all 4 selections are finalized"""

    def _convert_proto_to_dict(self, proto_map) -> Dict[str, Any]:
        """Convert protobuf map to Python dict."""
        return dict(proto_map)

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize a property schema for Gemini compatibility."""
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
        """Convert Pydantic model to FunctionDeclaration dict."""
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
        """Convert Pydantic schemas into explicit Tool instances."""
        tool_list = [FlightSearch, HotelSearch, RestaurantSearch, AttractionsSearch, GenerateItinerary]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        self.log("✅ Created 5 explicit Tool objects for Orchestrator LLM.")
        return tools

    def _create_tool_response(self, function_call, result: Dict[str, Any]):
        """Create properly formatted function response for SDK 0.8.5."""
        return glm.Part(
            function_response=glm.FunctionResponse(
                name=function_call.name,
                response={'result': result}
            )
        )