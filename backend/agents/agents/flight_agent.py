import json
from typing import Dict, Any, List, Optional, Union, Tuple
# Consolidated and Corrected Imports
import google.generativeai as genai
from google.generativeai import types as genai_types 
from google.ai import generativelanguage as glm
from pydantic import BaseModel, Field, ValidationError

# Assuming BaseAgent is defined elsewhere
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
# TOOL SCHEMAS
# =============================================================================

class SearchFlights(BaseModel):
    """Tool for searching flight options."""
    origin: str = Field(..., description="Origin airport IATA code (e.g., 'SFO').")
    destination: str = Field(..., description="Destination airport IATA code (e.g., 'CDG').")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format.")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format (optional).")
    passengers: int = Field(1, description="Number of passengers (default: 1).")
    cabin: str = Field("economy", description="Cabin class: economy, premium_economy, business, or first.")
    max_results: int = Field(20, description="Maximum number of flight results to return (default: 20).")


class FilterConstraints(BaseModel):
    """Structured filtering constraints for complex logic."""
    max_price: Optional[int] = Field(None, description="Maximum total price allowed in USD.")
    max_stops: Optional[int] = Field(None, description="Maximum number of stops allowed PER FLIGHT LEG (0 for nonstop).")
    preferred_airlines: List[str] = Field(default_factory=list, description="Preferred airlines IATA codes (e.g., ['UA', 'BA', 'LH']).")
    max_duration_hours: Optional[int] = Field(None, description="Maximum total trip duration in hours PER FLIGHT LEG.")


class AnalyzeAndFilter(BaseModel):
    """Tool for analyzing and filtering flight search results against complex user criteria."""
    analysis_criteria: str = Field(..., description="Primary analysis type: 'lowest_price', 'fastest', 'best_value', 'most_convenient'.")
    ranking_priorities: List[str] = Field(default_factory=lambda: ["price", "duration"], description="Ordered list of ranking priorities (e.g., ['price', 'duration', 'stops']).")
    constraints: FilterConstraints = Field(default_factory=FilterConstraints, description="Structured filtering constraints derived from user requirements.")


class ReflectAndModifySearch(BaseModel):
    """Tool for strategic reflection and search modification."""
    reasoning: str = Field(..., description="Detailed explanation of why previous search failed, how to adjust based on human feedback, and what the new strategy is.")
    new_search_parameters: SearchFlights = Field(..., description="Complete new parameters for the next search_flights call.")


class ProvideRecommendation(BaseModel):
    """Tool for providing final flight recommendations and explicitly signaling the need for user feedback."""
    top_flight_ids: List[str] = Field(..., description="List of the 3-5 best flight IDs ranked by the LLM (e.g., ['FL001', 'FL002', 'FL003']).")
    reasoning: str = Field(..., description="Detailed reasoning for why these flights were selected.")
    summary: str = Field(..., description="Brief summary comparing options and explicitly asking the user to choose one or provide refinement feedback.")
    # CRITICAL HIL FLAG
    user_input_required: bool = Field(True, description="MUST be True. Signals the Orchestrator to pause and ask the human to choose a flight or provide refinement feedback.")


# =============================================================================
# ENHANCED PURE AGENTIC FLIGHT AGENT
# =============================================================================

class FlightAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str, amadeus_client: Any = None):
        
        super().__init__("FlightAgent", gemini_api_key)
        self.amadeus_client = amadeus_client
        
        if not amadeus_client:
            self.log("⚠️ No Amadeus client provided - will use MOCK data", "WARN")
            
        self.flight_search_results = []
        self.analysis_results = {}
        
        # Tool execution mapping
        self.tool_functions = {
            "SearchFlights": self._tool_search_flights,
            "AnalyzeAndFilter": self._tool_analyze_and_filter,
            "ReflectAndModifySearch": self._tool_reflect_and_modify_search,
            "ProvideRecommendation": self._tool_provide_recommendation
        }
        
        # Pydantic schema mapping
        self.tool_schemas = {
            "SearchFlights": SearchFlights,
            "AnalyzeAndFilter": AnalyzeAndFilter,
            "ReflectAndModifySearch": ReflectAndModifySearch,
            "ProvideRecommendation": ProvideRecommendation
        }
        
        self.system_instruction = self._build_system_instruction()
        self.gemini_tools = self._create_gemini_tools()

        self.model = genai.GenerativeModel(
            'gemini-2.5-flash',
            tools=self.gemini_tools, 
            system_instruction=self.system_instruction,
            generation_config={'temperature': 0.7}
        )
        self.log("✅ Enhanced Pure Agentic FlightAgent initialized")


    # =========================================================================
    # PUBLIC ENTRY POINT (HIL Flow Controller)
    # =========================================================================

    def execute(self, params: Dict[str, Any], continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 5) -> Dict[str, Any]:
        """
        Public entry point for the OrchestratorAgent. 
        Triggers the autonomous process and handles HIL resumption.
        """
        
        chat = self.model.start_chat()
        
        if continuation_message:
            # HIL RESUMPTION: Orchestrator passes back structured human feedback
            prompt = f"The user has reviewed the last recommendations and provided this feedback: {json.dumps(continuation_message)}. Based on this, reflect and immediately use your tools (ReflectAndModifySearch or AnalyzeAndFilter) to refine the results or confirm the final choice."
            self.log(f"🔄 Resuming search based on human feedback: {continuation_message.get('feedback', 'New constraints/choice')}")
            
            # Check for final choice
            if continuation_message.get('status') == 'FINAL_CHOICE':
                 self.log(f"✅ User selected flight ID: {continuation_message.get('flight_id')}")
                 return self._format_final_response(selected_id=continuation_message.get('flight_id'))
        
        else:
            # INITIAL CALL: Start the search process
            prompt = f"Find and recommend flights with a complete strategy (search, analyze, recommend) based on the following initial parameters: {json.dumps(params)}"
            self.log(f"▶️ Starting initial flight search for: {params.get('origin')} to {params.get('destination')}")

        # First message (or resumption message)
        response = chat.send_message(prompt)

        for i in range(max_turns):
            # Extract function calls properly for SDK 0.8.5
            current_function_calls = []
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        current_function_calls.append(part.function_call)
            
            if not current_function_calls:
                self.log(f"❗ Turn {i+1}: LLM stopped without calling a tool. Text: {getattr(response, 'text', 'No text')}", "WARN")
                break

            tool_results = []  # Initialize tool_results at the start of each iteration
            
            for func_call in current_function_calls:
                tool_name = func_call.name
                tool_args = self._convert_proto_to_dict(func_call.args)
                
                try:
                    result = self._execute_tool(tool_name, tool_args)
                    tool_results.append(self._create_tool_response(func_call, result))
                    
                    if tool_name == 'ProvideRecommendation':
                        self.log("⏸️ FlightAgent is ready for Human-in-the-Loop input.")
                        return self._format_recommendation_for_pause()
                        
                except Exception as e:
                    self.log(f"❌ Tool execution failed for {tool_name}: {e}", "ERROR")
                    error_result = {"success": False, "error": f"Tool error: {str(e)}"}
                    tool_results.append(self._create_tool_response(func_call, error_result))
            
            # Send tool results back wrapped in glm.Content for SDK 0.8.5
            tool_response_content = glm.Content(
                role="function",
                parts=tool_results
            )
            response = chat.send_message(tool_response_content)
            
        # If the loop finishes without a recommendation or choice
        return self._force_completion()


    # =========================================================================
    # TOOL CONVERSION & HELPER FIXES (For robust tool calling)
    # =========================================================================

    def _convert_proto_to_dict(self, proto_map: Any) -> Dict[str, Any]:
        """Converts a protobuf map/structure to a standard Python dictionary."""
        return dict(proto_map)
        
    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitizes a single property schema for Gemini compatibility."""
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
        """Converts Pydantic model to a sanitized FunctionDeclaration dictionary."""
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
        """Converts Pydantic schemas into explicit Tool instances."""
        tool_list = [SearchFlights, AnalyzeAndFilter, ReflectAndModifySearch, ProvideRecommendation]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        return tools


    def _build_system_instruction(self) -> str:
        return """You are a highly autonomous, professional Flight Search Agent. Your goal is to find the best flights and pause the workflow for human confirmation.

YOUR WORKFLOW (HIL):
1. **Search**: Call `SearchFlights` with initial parameters.
2. **Analyze**: Use `AnalyzeAndFilter` to apply constraints and ranking priorities to collected results.
3. **HIL PAUSE**: Call `ProvideRecommendation`. This tool MUST set `user_input_required=True` to signal the orchestrator to pause and ask the human for a choice.
4. **RESUME**: If the orchestrator provides human feedback (e.g., "Too many stops, search for nonstop"), **you MUST call `ReflectAndModifySearch`** to articulate your new strategy and adjusted search/filter parameters before rerunning the search.
5. **FINAL CHOICE**: If the orchestrator provides a `FINAL_CHOICE` message, confirm the choice and terminate the loop by returning the final result structure.

CRITICAL RULES:
- Maintain persistent memory of ALL search results across iterations.
- Never choose a flight yourself; always use `ProvideRecommendation` to get human confirmation/refinement."""

    # =========================================================================
    # TOOL IMPLEMENTATION METHODS (No HIL changes, just ensure compatibility)
    # =========================================================================

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool requested by the LLM with Pydantic validation."""
        schema = self.tool_schemas.get(tool_name)
        func = self.tool_functions.get(tool_name)

        if not schema or not func:
            raise ValueError(f"Unknown tool or function mapping: {tool_name}")
        
        validated_args = schema(**tool_args)
            
        return func(validated_args)
    
    def _tool_search_flights(self, params: SearchFlights) -> Dict[str, Any]:
        """Tool Implementation: Search for flights with mock/real API logic."""
        self.log(f"🔍 Searching flights: {params.origin} → {params.destination}")
        flights = self._generate_mock_flights(params)
        
        current_ids = {f['id'] for f in self.flight_search_results}
        new_flights = [f for f in flights if f['id'] not in current_ids]
        self.flight_search_results.extend(new_flights)

        return {
            "success": True,
            "flights_found_this_call": len(flights),
            "total_flights_stored": len(self.flight_search_results),
            "message": "Mock flight data stored.",
            "sample_flights": new_flights[:3] if new_flights else flights[:3]
        }
    
    def _tool_analyze_and_filter(self, params: AnalyzeAndFilter) -> Dict[str, Any]:
        """Tool Implementation: Analyze and filter flights."""
        
        self.log(f"📊 Analyzing {len(self.flight_search_results)} stored flights...")
        filtered_flights = self.flight_search_results.copy()
        
        # Apply mock filtering logic here (e.g., max_price, max_stops)
        if params.constraints.max_price:
             filtered_flights = [f for f in filtered_flights if f['price'] <= params.constraints.max_price]

        # Apply sorting logic
        if params.ranking_priorities:
            filtered_flights.sort(key=lambda f: (f['price'], self._parse_duration_minutes(f['outbound'].get('duration', '0h 0m'))))

        self.analysis_results['last_filtered_flights'] = filtered_flights
        
        return {
            "success": True,
            "filtered_count": len(filtered_flights),
            "message": f"Analysis complete. {len(filtered_flights)} flights match criteria and are now ranked by: {', '.join(params.ranking_priorities)}.",
            "top_3_summary": [{"id": f['id'], "price": f['price'], "summary": f"{f['outbound'].get('stops', 0)} stops, {f['outbound'].get('duration', 'N/A')}"} for f in filtered_flights[:3]]
        }
    
    def _tool_reflect_and_modify_search(self, params: ReflectAndModifySearch) -> Dict[str, Any]:
        """Tool Implementation: Record reflection and prepare for new search."""
        self.log("🧠 Agent Reflection:")
        self.log(f"   Reasoning: {params.reasoning}")
        
        return {
            "success": True,
            "message": f"Reflection recorded. New strategy: {params.reasoning}. Please call 'SearchFlights' with the new parameters to proceed."
        }

    def _tool_provide_recommendation(self, params: ProvideRecommendation) -> Dict[str, Any]:
        """Tool Implementation: Store recommendation and signal HIL pause."""
        self.log(f"⭐ Recommendation provided for {len(params.top_flight_ids)} flights.")
        self.analysis_results['last_recommendation'] = params.model_dump()
        
        # The actual HIL signal is handled by the execute loop via _format_recommendation_for_pause
        return {
            "success": True,
            "message": "Recommendation prepared. Waiting for Orchestrator to pause for human input."
        }
    
    # =========================================================================
    # HIL and FINAL RESPONSE FORMATTING
    # =========================================================================
    
    def _format_recommendation_for_pause(self) -> Dict[str, Any]:
        """Formats the output when the agent needs human input (HIL PAUSE)."""
        rec = self.analysis_results['last_recommendation']
        flight_map = {f['id']: f for f in self.flight_search_results}
        recommended_flights = [flight_map[fid] for fid in rec['top_flight_ids'] if fid in flight_map]
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": "HIL_PAUSE_REQUIRED", # Explicit status for Orchestrator
            "recommendation_summary": rec['summary'],
            "recommended_flights": recommended_flights
        }

    def _format_final_response(self, selected_id: Optional[str] = None) -> Dict[str, Any]:
        """Formats the final structured output after human selection (HIL TERMINATION)."""
        
        if selected_id:
            final_flight = next((f for f in self.flight_search_results if f['id'] == selected_id), None)
            summary = f"User selected the flight ID: {selected_id}. Final flight secured."
        else:
            final_flight = None
            summary = "Agent completed its task but no final selection was provided."

        return {
            "success": True,
            "agent": self.name,
            "status_code": "SUCCESS",
            "recommendation_summary": summary,
            "final_flight": final_flight
        }

    def _force_completion(self) -> Dict[str, Any]:
        """Fallback to force a completion if max iterations reached."""
        top_flights = self.analysis_results.get('last_filtered_flights', [])
        
        if not top_flights:
            status = "STATUS_NO_RESULTS_FOUND"
            summary = "Search failed to return any flights."
        else:
            status = "STATUS_INCOMPLETE_LOOP"
            summary = "Agent reached iteration limit before human pause or final recommendation. Returning best available analysis."

        return {
            "success": False,
            "agent": self.name,
            "status_code": status,
            "summary": summary,
            "recommended_flights": top_flights[:3]
        }
        
    def _create_tool_response(self, function_call: Any, result: Dict[str, Any]) -> Any:
        """
        Creates a properly formatted function response for SDK 0.8.5.
        Uses the raw protobuf glm.Part structure.
        """
        return glm.Part(
            function_response=glm.FunctionResponse(
                name=function_call.name,
                response={'result': result}
            )
        )
        
    def _parse_duration_minutes(self, duration_str: str) -> int:
        """Converts 'Xh Ym' string duration to total minutes (used for sorting)."""
        try:
            total_minutes = 0
            parts = duration_str.lower().replace(',', '').split()
            for part in parts:
                if 'h' in part:
                    total_minutes += int(part.replace('h', '')) * 60
                elif 'm' in part:
                    total_minutes += int(part.replace('m', ''))
            return total_minutes
        except:
            return 999999 

    def _generate_mock_flights(self, params: SearchFlights) -> List[Dict]:
        """Generates mock data for development."""
        # Simple mock generation for round trip or one way
        is_round_trip = params.return_date is not None

        flights = [
            {
                "id": "FL001", "price": 1250, "currency": "USD",
                "outbound": {"airline": "United Airlines", "airline_code": "UA", "stops": 0, "duration": "11h 15m"},
                "return": {"airline": "United Airlines", "airline_code": "UA", "stops": 0, "duration": "12h 0m"} if is_round_trip else None
            },
            {
                "id": "FL002", "price": 980, "currency": "USD",
                "outbound": {"airline": "Lufthansa", "airline_code": "LH", "stops": 1, "duration": "13h 30m"},
                "return": {"airline": "Lufthansa", "airline_code": "LH", "stops": 1, "duration": "14h 0m"} if is_round_trip else None
            },
            {
                "id": "FL003", "price": 2800, "currency": "USD",
                "outbound": {"airline": "Air France", "airline_code": "AF", "stops": 0, "duration": "10h 5m"},
                "return": {"airline": "Air France", "airline_code": "AF", "stops": 0, "duration": "10h 15m"} if is_round_trip else None
            }
        ]
        return flights