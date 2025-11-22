from typing import Dict, Any, List, Optional
import json
import google.generativeai as genai
# This is the correct, modern import structure for a stable SDK
from google.generativeai import types as genai_types
from typing import Any
from pydantic import BaseModel, Field, ValidationError

# --- HIL Status Codes (Must match FlightAgent and HotelAgent) ---
HIL_PAUSE_REQUIRED = "HIL_PAUSE_REQUIRED"
SUCCESS = "SUCCESS"
FINAL_CHOICE = "FINAL_CHOICE"
REFINE_SEARCH = "REFINE_SEARCH"

# --- Placeholder/Base Classes (Required to resolve NameError) ---
class BaseAgent:
    """Placeholder for BaseAgent class with logging and utility methods."""
    def __init__(self, name, api_key):
        self.name = name
        self.api_key = api_key
    def log(self, message: str, level: str = "INFO"):
        print(f"[{self.name}][{level}] {message}")

# -----------------------------------------------------------------------------

# --- Orchestrator Tool Schemas (The Orchestrator LLM uses these) ---
# ... (Tool Schemas are unchanged) ...
class FlightSearch(BaseModel):
    origin: str = Field(..., description="Origin airport IATA code.")
    destination: str = Field(..., description="Destination airport IATA code.")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format.")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format.")

class HotelSearch(BaseModel):
    city_code: str = Field(..., description="City IATA code or name.")
    check_in_date: str = Field(..., description="Check-in date in YYYY-MM-DD format.")
    check_out_date: str = Field(..., description="Check-out date in YYYY-MM-DD format.")

class RestaurantSearch(BaseModel):
    city: str = Field(..., description="City for restaurant search.")

class AttractionsSearch(BaseModel):
    city: str = Field(..., description="City for attractions search.")

class GenerateItinerary(BaseModel):
    trip_summary: str = Field(..., description="A brief summary of the finalized trip parameters (dates, destinations).")

# =============================================================================
# ORCHESTRATOR AGENT
# =============================================================================

class OrchestratorAgent(BaseAgent):
    def __init__(self, gemini_api_key: str, flight_agent: Any, hotel_agent: Any, restaurant_agent: Any, attractions_agent: Any, itinerary_agent: Any):
        
        super().__init__("OrchestratorAgent", gemini_api_key)
        
        self.flight_agent = flight_agent
        self.hotel_agent = hotel_agent
        self.restaurant_agent = restaurant_agent
        self.attractions_agent = attractions_agent
        self.itinerary_agent = itinerary_agent
        
        self.specialist_tools = {
            "search_flights": self._tool_flight_search, 
            "search_hotels": self._tool_hotel_search,
            "search_restaurants": restaurant_agent.execute, 
            "search_attractions": attractions_agent.execute,
            "generate_itinerary": itinerary_agent.execute,
        }

        self.tool_schemas = {
            "search_flights": FlightSearch,
            "search_hotels": HotelSearch,
            "search_restaurants": RestaurantSearch,
            "search_attractions": AttractionsSearch,
            "generate_itinerary": GenerateItinerary
        }

        self.all_results = {}
        self.all_results['FlightAgent_HIL_TURN_COUNT'] = 0
        
        self.system_instruction = self._build_system_instruction()
        self.gemini_tools = self._create_gemini_tools()

        self.model = genai.GenerativeModel(
            'gemini-2.5-flash',
            tools=self.gemini_tools,
            system_instruction=self.system_instruction,
            generation_config={'temperature': 0.7}
        )
        self.log("✅ OrchestratorAgent initialized with HIL support")


    # =========================================================================
    # HIL EXECUTION WRAPPER (Unchanged)
    # =========================================================================

    def _execute_hil_agent_with_loop(self, agent: Any, initial_params: Dict[str, Any], agent_name: str, item_name: str) -> Dict[str, Any]:
        """
        Manages the Human-in-the-Loop (HIL) pause and resume cycle for a specialist agent.
        """
        continuation_message = None
        max_hil_turns = 3 
        turn = 0
        
        while turn < max_hil_turns:
            turn += 1
            self.log(f"🔗 HIL Loop Turn {turn} for {agent_name}...")
            
            # 1. Execute the agent (initial call or resumption)
            result = agent.execute(initial_params, continuation_message)
            
            # 2. Check the status
            if result.get('status_code') == SUCCESS:
                self.log(f"✅ {agent_name} successfully finalized the {item_name} selection.")
                return result
            
            elif result.get('status_code') == HIL_PAUSE_REQUIRED:
                self.log(f"⏸️ {agent_name} requires Human-in-the-Loop input. Pausing Orchestrator.")
                
                # 3. Present recommendations and get human feedback (SIMULATED)
                human_response = self._simulate_human_interaction(
                    agent_name, 
                    result.get(f'recommended_{item_name}s', []), 
                    item_name
                )
                
                # 4. Process human response and set continuation message
                if human_response['status'] == FINAL_CHOICE:
                    self.log(f"✔️ Human made final choice: {human_response[f'{item_name}_id']}")
                    
                    # Rerun the agent one final time with the selection to get final structured output
                    final_msg = {'status': FINAL_CHOICE, f'{item_name}_id': human_response[f'{item_name}_id']}
                    return agent.execute(initial_params, final_msg)
                
                elif human_response['status'] == REFINE_SEARCH:
                    self.log(f"🔄 Human requested refinement: {human_response['feedback']}")
                    continuation_message = {'status': REFINE_SEARCH, 'feedback': human_response['feedback']}
                    
                else:
                    self.log(f"❌ Unknown human response status: {human_response['status']}", "ERROR")
                    return {"success": False, "error": f"HIL failure: Unknown human response status {human_response['status']}"}
            
            else:
                self.log(f"❌ {agent_name} failed with status: {result.get('status_code')}", "ERROR")
                return result

        self.log(f"⚠️ HIL loop for {agent_name} reached max turns ({max_hil_turns}). Returning last result.", "WARN")
        return result

    def _simulate_human_interaction(self, agent_name: str, recommendations: List[Dict[str, Any]], item_name: str) -> Dict[str, Any]:
        """
        SIMULATED function to pause and receive user input.
        """
        
        self.log("\n" + "="*50)
        self.log(f"👤 HUMAN INPUT REQUIRED for {agent_name} ({item_name.upper()})")
        self.log("="*50)

        if not recommendations:
            self.log("❗ Agent returned no recommendations. Forcing refinement...")
            return {'status': REFINE_SEARCH, 'feedback': 'No options were found. Please broaden the search criteria.'}

        # --- SIMULATION LOGIC ---
        
        if agent_name == "FlightAgent":
            
            # This counter logic drives the simulation: Refine once, then select.
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
            
        else:
            selection_id = recommendations[0]['id'] if recommendations else "UNKNOWN_ID"
            return {'status': FINAL_CHOICE, f'{item_name}_id': selection_id}

    # =========================================================================
    # TOOL EXECUTION IMPLEMENTATIONS (Unchanged)
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

    # =========================================================================
    # ORCHESTRATOR LLM MAIN LOOP AND HELPERS (Unchanged)
    # =========================================================================
    
    def _build_system_instruction(self) -> str:
        return """You are the central Orchestrator Agent. Your task is to plan a complete vacation itinerary by calling specialist agents sequentially.

RULES:
1. **Analyze** the user request and determine the necessary information (flights, hotels, activities).
2. **Prioritize** securing the transport (flights) and accommodation (hotels) first, as these are mandatory.
3. **CALL** `search_flights` first, then `Google Hotels`, then `search_restaurants` and `search_attractions`.
4. **COLLECT** the final results from each tool call. The specialized search tools will handle the 'Human-in-the-Loop' process internally, so you just need to wait for their successful return.
5. **FINALIZE**: When all necessary information is collected (final flight, final hotel, attractions/dining info), call `generate_itinerary` once to synthesize the final plan."""

    # --- TOOL CONVERSION HELPERS (Unchanged logic) ---

    def _convert_proto_to_dict(self, proto_map: Any) -> Dict [str, Any]:
        """Converts a protobuf map/structure to a standard Python dictionary."""
        return {key: value for key, value in proto_map.items()}
        
    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        # ... (implementation omitted for brevity, logic remains the same)
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

    def _pydantic_to_function_declaration(self, pydantic_model: Any) -> Dict[str, Any]:
        # ... (implementation omitted for brevity, logic remains the same)
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

    def _create_gemini_tools(self) -> List[Any]:
        # ... (implementation omitted for brevity, logic remains the same)
        tool_list = [FlightSearch, HotelSearch, RestaurantSearch, AttractionsSearch, GenerateItinerary]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        self.log(f"✅ Created {len(tools)} explicit Tool objects for Orchestrator LLM.")
        return tools
    
    def _create_tool_response(self, function_call: Any, result: Dict[str, Any]) -> Any: 
    
        # Construct the function response using the correct v0.8.5 structure
        return genai_types.Part(
            function_response=genai_types.FunctionResponse(
                name=function_call.name,
                response=result
            )
        )
        
    def execute(self, user_prompt: str, max_turns: int = 15) -> Dict[str, Any]:
        
        self.log(f"Starting orchestration for: {user_prompt}")
        chat = self.model.start_chat()
        response = chat.send_message(user_prompt)

        for i in range(max_turns):
            
            # --- CRITICAL FIX: Explicitly extract function calls to avoid SDK ambiguity ---
            current_function_calls = []
            
            # Check if candidates exist and iterate over the parts of the first candidate
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        current_function_calls.append(part.function_call)

            if not current_function_calls:
                # Safely retrieve text for logging, preventing the crash
                final_text = getattr(response, 'text', 'No final text available.') 
                self.log(f"✅ LLM finished without tool call. Final text: {final_text}", "INFO")
                break 
            # ------------------------------------------------------------------------------------------
            
            tool_parts = []
            # Iterate over the explicitly extracted function calls
            for func_call in current_function_calls: 
                tool_name = func_call.name
                tool_args = self._convert_proto_to_dict(func_call.args)
                
                try:
                    self.log(f"🤖 Orchestrator LLM called tool: {tool_name} with args: {tool_args}")
                    tool_func = self.specialist_tools.get(tool_name)
                    
                    if not tool_func:
                        raise ValueError(f"Unknown tool: {tool_name}")
                        
                    schema = self.tool_schemas.get(tool_name)
                    validated_args = schema(**tool_args)
                    result = tool_func(validated_args)
                    
                    tool_parts.append(self._create_tool_response(func_call, result))
                    
                except Exception as e:
                    self.log(f"❌ Orchestrator tool execution failed for {tool_name}: {e}", "ERROR")
                    error_result = {"success": False, "error": f"Tool execution error: {str(e)}"}
                    tool_parts.append(self._create_tool_response(func_call, error_result))
            
            # FIX: Use the alias genai_types.Content
            tool_response_content = genai_types.Content(
                role="function",
                parts=tool_parts
            )
            
            response = chat.send_message(tool_response_content)
            
        return {
            "success": True, 
            "results": self.all_results, 
            "final_response_text": getattr(response, 'text', 'Orchestration complete, no final text response from LLM.')
        }