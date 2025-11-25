"""
FlightAgent - Production Version with Real Amadeus API Integration
===================================================================
FIXED: Conversation history serialization for SDK compatibility
"""

import json
import os
import sys
from typing import Dict, Any, List, Optional, Union, Tuple
from dotenv import load_dotenv

# Google Gemini imports
import google.generativeai as genai
from google.generativeai import types as genai_types 
from google.ai import generativelanguage as glm
from pydantic import BaseModel, Field, ValidationError

# ============================================================================
# AMADEUS CLIENT IMPORT (CRITICAL FOR REAL API)
# ============================================================================

# Add MCP servers path to import Amadeus client
mcp_path = os.path.join(os.path.dirname(__file__), '..', '..', 'mcp-servers', 'flights')
if mcp_path not in sys.path:
    sys.path.insert(0, mcp_path)

from amadeus_client import AmadeusFlightClient

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path)

# ============================================================================
# BASE AGENT
# ============================================================================

class BaseAgent:
    """Placeholder for BaseAgent class with logging and utility methods."""
    def __init__(self, name, api_key):
        self.name = name
        self.api_key = api_key
    def log(self, message: str, level: str = "INFO"):
        print(f"[{self.name}][{level}] {message}")
    def format_error(self, e: Exception) -> Dict[str, Any]:
        return {"success": False, "error": f"Agent Error: {str(e)}"}

# ============================================================================
# TOOL SCHEMAS (UNCHANGED - Pydantic models for tool validation)
# ============================================================================

class SearchFlights(BaseModel):
    """Tool for searching flight options."""
    origin: str = Field(..., description="Origin airport IATA code (e.g., 'SFO').")
    destination: str = Field(..., description="Destination airport IATA code (e.g., 'CDG').")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format.")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format (optional).")
    passengers: int = Field(1, description="Number of passengers (default: 1).")
    cabin: str = Field("economy", description="Cabin class: economy, premium_economy, business, or first.")
    max_results: int = Field(20, description="Maximum number of flight results to return (default: 20).")

class AnalyzeAndFilter(BaseModel):
    """Tool for analyzing and filtering flight search results.
    
    Call this tool to analyze flights and apply budget constraints.
    The analysis_criteria field specifies what to optimize for.
    """
    analysis_criteria: str = Field("lowest_price", description="Analysis type: 'lowest_price', 'fastest', 'best_value', or 'most_convenient'.")
    max_price: Optional[int] = Field(None, description="Maximum total price allowed in USD (optional budget constraint).")

class ReflectAndModifySearch(BaseModel):
    """Tool for strategic reflection and search modification."""
    reasoning: str = Field(..., description="Detailed explanation of why previous search failed or how to adjust based on feedback.")
    new_search_parameters: SearchFlights = Field(..., description="Complete new parameters for the next SearchFlights call.")

class ProvideRecommendation(BaseModel):
    """Tool for providing final flight recommendations and signaling HIL pause."""
    top_flight_ids: List[str] = Field(default=[], description="List of 3-5 best flight IDs ranked by the LLM. Empty list if no flights found.")
    reasoning: str = Field(..., description="Detailed reasoning for why these flights were selected, or explanation of why no flights were found.")
    summary: str = Field(..., description="Brief summary comparing options and asking user to choose or provide refinement feedback. If no flights found, explain the issue.")
    user_input_required: bool = Field(True, description="MUST be True. Signals Orchestrator to pause for human input.")

class FinalizeSelection(BaseModel):
    """Tool for finalizing the human's flight choice.
    
    Call this tool when the human has made a final selection.
    """
    selected_flight_id: str = Field(..., description="The ID of the flight the human selected.")
    confirmation_message: str = Field(..., description="Brief confirmation message to the human about their selection.")

# ============================================================================
# ENHANCED PURE AGENTIC FLIGHT AGENT WITH REAL AMADEUS API
# ============================================================================

class FlightAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str):
        super().__init__("FlightAgent", gemini_api_key)
        
        # ✅ INITIALIZE AMADEUS CLIENT FOR REAL API CALLS
        amadeus_api_key = os.getenv('AMADEUS_API_KEY')
        amadeus_api_secret = os.getenv('AMADEUS_API_SECRET')
        
        if not amadeus_api_key or not amadeus_api_secret:
            raise ValueError("AMADEUS_API_KEY and AMADEUS_API_SECRET must be set in environment variables!")
        
        self.amadeus_client = AmadeusFlightClient(amadeus_api_key, amadeus_api_secret)
        self.log("✅ Amadeus Flight Client initialized successfully")
        
        # Initialize agent state
        self.flight_search_results = []
        self.analysis_results = {}
        
        # Tool function mapping
        self.tool_functions = {
            "SearchFlights": self._tool_search_flights,
            "AnalyzeAndFilter": self._tool_analyze_and_filter,
            "ReflectAndModifySearch": self._tool_reflect_and_modify_search,
            "ProvideRecommendation": self._tool_provide_recommendation,
            "FinalizeSelection": self._tool_finalize_selection
        }
        
        # Tool schema mapping
        self.tool_schemas = {
            "SearchFlights": SearchFlights,
            "AnalyzeAndFilter": AnalyzeAndFilter,
            "ReflectAndModifySearch": ReflectAndModifySearch,
            "ProvideRecommendation": ProvideRecommendation,
            "FinalizeSelection": FinalizeSelection
        }
        
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
        self.log("✅ Enhanced Pure Agentic FlightAgent initialized with REAL Amadeus API")

    # ========================================================================
    # PUBLIC ENTRY POINT (HIL Flow Controller)
    # ========================================================================

    def execute(self, params: Dict[str, Any], continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 5) -> Dict[str, Any]:
        """
        Triggers the autonomous process. Handles initial search or continuation 
        (resumption) based on user feedback.
        
        FIXED: Proper conversation history serialization for SDK compatibility
        
        Args:
            params: Initial search parameters
            continuation_message: Optional message from orchestrator for HIL resumption
            max_turns: Maximum iterations before forcing completion
            
        Returns:
            Dict with status_code: "HIL_PAUSE_REQUIRED" or "SUCCESS"
        """
        try:
            self.log(f"🚀 Starting FlightAgent execution (max_turns={max_turns})...")
            
            # Initialize conversation history as list of properly formatted messages
            conversation_history = []
            
            # CRITICAL: Store original search parameters to prevent hallucination during refinement
            if not continuation_message:
                # First execution - store the original params
                self._original_params = {
                    'origin': params.get('origin'),
                    'destination': params.get('destination'),
                    'departure_date': params.get('departure_date'),
                    'return_date': params.get('return_date'),
                    'passengers': params.get('passengers', 1)
                }
            
            # Add initial user message or continuation message
            if continuation_message:
                self.log("📥 Resuming with human feedback...")
                # Include context reminder with original params
                context = f"CONTEXT REMINDER: You are searching for flights from {self._original_params['origin']} to {self._original_params['destination']}, departing {self._original_params['departure_date']}"
                if self._original_params.get('return_date'):
                    context += f", returning {self._original_params['return_date']}"
                context += f", for {self._original_params['passengers']} passenger(s). You MUST maintain these origin, destination, and date parameters.\n\n"
                user_text = context + continuation_message.get('content', '')
            else:
                # Build EXPLICIT initial user message that triggers SearchFlights call
                origin = self._original_params['origin']
                destination = self._original_params['destination']
                departure_date = self._original_params['departure_date']
                return_date = self._original_params.get('return_date')
                passengers = self._original_params['passengers']
                
                user_text = f"""Search for flights with these parameters:
- Origin: {origin}
- Destination: {destination}
- Departure: {departure_date}"""
                if return_date:
                    user_text += f"\n- Return: {return_date}"
                user_text += f"\n- Passengers: {passengers}\n\nCall the SearchFlights tool now with these exact parameters."
            
            # Add initial user message
            conversation_history.append({
                'role': 'user',
                'parts': [{'text': user_text}]
            })
            
            # Main agentic loop
            for turn in range(max_turns):
                self.log(f"🔄 Turn {turn + 1}/{max_turns}")
                
                # Get LLM response with function calling
                response = self.model.generate_content(conversation_history)
                
                # FIXED: Extract parts properly from response
                response_parts = response.candidates[0].content.parts
                
                # Add model response to conversation history
                conversation_history.append({
                    'role': 'model',
                    'parts': [self._serialize_part(part) for part in response_parts]
                })
                
                # Check if LLM wants to call a tool
                # CRITICAL: Handle empty response_parts to prevent IndexError
                if response_parts and len(response_parts) > 0 and response_parts[0].function_call:
                    function_call = response_parts[0].function_call
                    tool_name = function_call.name
                    tool_args = self._convert_proto_to_dict(function_call.args)
                    
                    self.log(f"🛠️  LLM called tool: {tool_name}")
                    
                    # Execute tool
                    result = self._execute_tool(tool_name, tool_args)
                    
                    # FIXED: Add function response to conversation with proper serialization
                    conversation_history.append({
                        'role': 'function',
                        'parts': [{
                            'function_response': {
                                'name': tool_name,
                                'response': {'result': result}
                            }
                        }]
                    })
                    
                    # Check if we need to pause for HIL
                    if tool_name == "ProvideRecommendation":
                        self.log("⏸️  HIL PAUSE - Recommendations ready for human")
                        return self._format_recommendation_for_pause()
                    
                    # Check if agent finalized the selection
                    elif tool_name == "FinalizeSelection":
                        self.log("✅ Selection finalized - Returning SUCCESS")
                        return result  # Return the result directly with SUCCESS status
                
                else:
                    # LLM provided text response (shouldn't happen in proper flow)
                    self.log("⚠️  LLM gave text response instead of tool call", "WARN")
                    break
            
            # If we reach here, max turns exceeded
            self.log("⚠️  Max turns reached without completion", "WARN")
            return self._force_completion()
            
        except Exception as e:
            self.log(f"❌ Error in execute: {str(e)}", "ERROR")
            import traceback
            traceback.print_exc()
            return self.format_error(e)

    # ========================================================================
    # TOOL IMPLEMENTATION METHODS
    # ========================================================================

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool requested by the LLM with Pydantic validation."""
        schema = self.tool_schemas.get(tool_name)
        func = self.tool_functions.get(tool_name)

        if not schema or not func:
            raise ValueError(f"Unknown tool or function mapping: {tool_name}")
        
        validated_args = schema(**tool_args)
            
        return func(validated_args)
    
    def _tool_search_flights(self, params: SearchFlights) -> Dict[str, Any]:
        """Tool Implementation: Search for flights using REAL Amadeus API."""
        self.log(f"🔍 Searching REAL flights via Amadeus: {params.origin} → {params.destination}")
        
        # Call REAL Amadeus API
        flights = self._search_flights_real_api(params)
        
        # Store results (avoiding duplicates)
        current_ids = {f['id'] for f in self.flight_search_results}
        new_flights = [f for f in flights if f['id'] not in current_ids]
        self.flight_search_results.extend(new_flights)

        return {
            "success": True,
            "flights_found_this_call": len(flights),
            "total_flights_stored": len(self.flight_search_results),
            "message": f"✅ Real flight data from Amadeus API stored. Found {len(flights)} flights.",
            "sample_flights": new_flights[:3] if new_flights else flights[:3]
        }
    
    def _tool_analyze_and_filter(self, params: AnalyzeAndFilter) -> Dict[str, Any]:
        """Tool Implementation: Analyze and filter flights."""
        
        self.log(f"📊 Analyzing {len(self.flight_search_results)} stored flights...")
        filtered_flights = self.flight_search_results.copy()
        
        # Apply price filtering if max_price is provided
        if params.max_price:
            original_count = len(filtered_flights)
            filtered_flights = [f for f in filtered_flights if f['price'] <= params.max_price]
            self.log(f"💰 Filtered by max price ${params.max_price}: {original_count} → {len(filtered_flights)} flights")

        # Apply sorting based on analysis criteria
        if params.analysis_criteria == "lowest_price":
            filtered_flights.sort(key=lambda f: f['price'])
        elif params.analysis_criteria == "fastest":
            filtered_flights.sort(key=lambda f: self._parse_duration_minutes(f['outbound'].get('duration', '999h')))
        else:  # best_value or most_convenient
            filtered_flights.sort(key=lambda f: (f['price'], self._parse_duration_minutes(f['outbound'].get('duration', '0h'))))

        self.analysis_results['last_filtered_hotels'] = filtered_flights
        
        return {
            "success": True,
            "filtered_count": len(filtered_flights),
            "message": f"Analysis complete. {len(filtered_flights)} flights match criteria and are ranked by {params.analysis_criteria}.",
            "top_3_summary": [{"id": f['id'], "price": f['price'], "summary": f"{f['outbound'].get('stops', 0)} stops, {f['outbound'].get('duration', 'N/A')}"} for f in filtered_flights[:3]]
        }
    
    def _tool_reflect_and_modify_search(self, params: ReflectAndModifySearch) -> Dict[str, Any]:
        """Tool Implementation: Record reflection and prepare for new search."""
        self.log("🧠 Agent Reflection:")
        self.log(f"   Reasoning: {params.reasoning}")
        
        return {
            "success": True,
            "message": f"Reflection recorded. New strategy: {params.reasoning}. Please call 'SearchFlights' with the new parameters to proceed."
        }

    def _tool_provide_recommendation(self, params: ProvideRecommendation) -> Dict[str, Any]:
        """Tool Implementation: Store recommendation and signal HIL pause."""
        self.log(f"⭐ Recommendation provided for {len(params.top_flight_ids)} flights.")
        self.analysis_results['last_recommendation'] = params.model_dump()
        
        return {
            "success": True,
            "message": "Recommendation prepared. Waiting for Orchestrator to pause for human input."
        }
    
    def _tool_finalize_selection(self, params: FinalizeSelection) -> Dict[str, Any]:
        """Tool Implementation: Finalize the human's flight selection and return SUCCESS status."""
        self.log(f"✅ Finalizing selection: Flight ID {params.selected_flight_id}")
        
        # Find the selected flight
        selected_flight = None
        for flight in self.flight_search_results:
            if flight['id'] == params.selected_flight_id:
                selected_flight = flight
                break
        
        if not selected_flight:
            self.log(f"⚠️ Selected flight ID {params.selected_flight_id} not found in search results", "WARN")
            # Use first flight as fallback
            selected_flight = self.flight_search_results[0] if self.flight_search_results else {}
        
        return {
            "success": True,
            "status_code": "SUCCESS",
            "final_flight": selected_flight,
            "confirmation": params.confirmation_message
        }
    
    # ========================================================================
    # REAL AMADEUS API INTEGRATION
    # ========================================================================
    
    def _search_flights_real_api(self, params: SearchFlights) -> List[Dict]:
        """
        Search for flights using REAL Amadeus API.
        
        Args:
            params: Validated SearchFlights parameters
            
        Returns:
            List of real flight dictionaries from Amadeus API
        """
        try:
            self.log("📡 Calling Amadeus API for real flight data...")
            
            # Call Amadeus client with search parameters
            flights = self.amadeus_client.search_flights(
                origin=params.origin,
                destination=params.destination,
                departure_date=params.departure_date,
                return_date=params.return_date,
                adults=params.passengers,
                max_results=params.max_results
            )
            
            self.log(f"✅ Amadeus returned {len(flights)} real flights")
            return flights
            
        except Exception as e:
            self.log(f"❌ Amadeus API call failed: {str(e)}", "ERROR")
            raise Exception(f"Failed to fetch flights from Amadeus API: {str(e)}")
    
    # ========================================================================
    # HIL AND FINAL RESPONSE FORMATTING
    # ========================================================================
    
    def _format_recommendation_for_pause(self) -> Dict[str, Any]:
        """Formats the output when the agent needs human input (HIL PAUSE)."""
        rec = self.analysis_results['last_recommendation']
        flight_map = {f['id']: f for f in self.flight_search_results}
        recommended_flights = [flight_map[fid] for fid in rec['top_flight_ids'] if fid in flight_map]
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": "HIL_PAUSE_REQUIRED",
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
    
    # ========================================================================
    # UTILITY METHODS (FIXED FOR SDK COMPATIBILITY)
    # ========================================================================
    
    def _serialize_part(self, part) -> Dict[str, Any]:
        """
        FIXED: Serialize a part object to a dictionary for conversation history.
        
        This ensures SDK compatibility by converting protobuf objects to dicts.
        """
        if hasattr(part, 'text') and part.text:
            return {'text': part.text}
        elif hasattr(part, 'function_call') and part.function_call:
            return {
                'function_call': {
                    'name': part.function_call.name,
                    'args': dict(part.function_call.args)
                }
            }
        else:
            # Fallback for other types
            return {'text': str(part)}
        
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

    def _convert_proto_to_dict(self, proto_map) -> Dict[str, Any]:
        """Convert protobuf map to Python dict."""
        return dict(proto_map)

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize a property schema for Gemini compatibility."""
        sanitized = {}
        type_map = {
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT"
        }
        
        json_type = prop_schema.get("type", "string")
        sanitized["type"] = type_map.get(json_type, "STRING")
        
        if "description" in prop_schema:
            sanitized["description"] = prop_schema["description"]
        if "enum" in prop_schema:
            sanitized["enum"] = prop_schema["enum"]
        if json_type == "array" and "items" in prop_schema:
            sanitized["items"] = self._sanitize_property_schema(prop_schema["items"])
            
        return sanitized

    def _pydantic_to_function_declaration(self, pydantic_model: BaseModel) -> Dict[str, Any]:
        """Convert Pydantic model to Gemini function declaration."""
        schema = pydantic_model.model_json_schema()
        name = schema.get("title", pydantic_model.__name__)
        description = schema.get("description", f"Tool: {name}")
        properties = schema.get("properties", {})
        required_params = schema.get("required", [])
        definitions = schema.get("$defs", {})
        
        sanitized_properties = {}
        for prop_name, prop_schema in properties.items():
            if "$ref" in prop_schema:
                ref_name = prop_schema["$ref"].split("/")[-1]
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
        """Create Gemini-compatible tool declarations."""
        tool_list = [SearchFlights, AnalyzeAndFilter, ReflectAndModifySearch, ProvideRecommendation, FinalizeSelection]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        return tools

    def _build_system_instruction(self) -> str:
        """Build the system instruction for the agent."""
        return """You are a highly autonomous Flight Search Agent. Your goal is to find the best flights and pause the workflow for human confirmation.

YOUR WORKFLOW (HIL):
1. **Search**: Call `SearchFlights` with appropriate parameters.
2. **Analyze**: Use `AnalyzeAndFilter` to apply constraints and identify 3-5 top options.
3. **HIL PAUSE**: Call `ProvideRecommendation`. This tool MUST set `user_input_required=True` to signal the orchestrator to pause and ask the human for a choice.
4. **RESUME**: If the orchestrator provides human feedback (e.g., "Too expensive"), call `ReflectAndModifySearch` to articulate your new strategy before rerunning the search.
5. **FINAL SELECTION**: When you see the phrase "FINAL_CHOICE_TRIGGER" in the user message, immediately call `FinalizeSelection` tool with the flight ID mentioned in the message. DO NOT respond with text.

CRITICAL RULES:
- ALWAYS call a tool on every turn - NEVER give text-only responses
- Maintain persistent memory of ALL search results across iterations.
- Never choose a flight yourself; always use `ProvideRecommendation` to get human confirmation/refinement.
- The phrase "FINAL_CHOICE_TRIGGER" means you must call FinalizeSelection immediately.
- **PARAMETER PRESERVATION**: When the message starts with "CONTEXT:", use ONLY those exact origin, destination, departure_date, and return_date values. NEVER change these parameters."""