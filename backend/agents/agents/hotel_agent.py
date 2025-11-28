"""
HotelAgent - Production Version with Real Amadeus API Integration
==================================================================
UPDATED: Added autonomous error correction for city code conversion
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

# Add MCP servers path to import Amadeus hotel client
mcp_path = os.path.join(os.path.dirname(__file__), '..', '..', 'mcp-servers', 'hotels')
if mcp_path not in sys.path:
    sys.path.insert(0, mcp_path)

from amadeus_hotel_client import AmadeusHotelClient

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

class SearchHotels(BaseModel):
    """Tool for searching hotel options."""
    city_code: str = Field(..., description="City code or name for hotel search (e.g., 'NYC', 'PAR').")
    check_in_date: str = Field(..., description="Check-in date in YYYY-MM-DD format.")
    check_out_date: str = Field(..., description="Check-out date in YYYY-MM-DD format.")
    adults: int = Field(2, description="Number of adults (default: 2).")
    max_results: int = Field(20, description="Maximum number of hotel results to return (default: 20).")

class AnalyzeAndFilter(BaseModel):
    """Tool for analyzing and ranking hotel search results.
    
    Simply call this tool without any parameters to analyze and rank hotels.
    """
    pass  # No parameters needed - agent will use default ranking

class ReflectAndModifySearch(BaseModel):
    """Tool for strategic reflection and search modification."""
    reasoning: str = Field(..., description="Detailed explanation of why previous search failed or how to adjust based on feedback.")
    new_search_parameters: SearchHotels = Field(..., description="Complete new parameters for the next SearchHotels call.")

class ProvideRecommendation(BaseModel):
    """Tool for providing final hotel recommendations and signaling HIL pause."""
    top_hotel_ids: List[str] = Field(default=[], description="List of the 3-5 best hotel IDs ranked by the LLM. Empty list if no hotels found.")
    reasoning: str = Field(..., description="Detailed reasoning for why these hotels were selected, or explanation of why no hotels were found.")
    summary: str = Field(..., description="Brief summary comparing options and explicitly asking the user to choose one or provide refinement feedback. If no hotels found, explain the issue.")
    user_input_required: bool = Field(True, description="MUST be True. Signals the Orchestrator to pause and ask the human to choose a hotel or provide refinement feedback.")

class FinalizeSelection(BaseModel):
    """Tool for finalizing the human's hotel choice.
    
    Call this tool when the human has made a final selection.
    """
    selected_hotel_id: str = Field(..., description="The ID of the hotel the human selected.")
    confirmation_message: str = Field(..., description="Brief confirmation message to the human about their selection.")

# ============================================================================
# ENHANCED PURE AGENTIC HOTEL AGENT WITH REAL AMADEUS API
# ============================================================================

class HotelAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str, travel_api_client: Any = None):
        super().__init__("HotelAgent", gemini_api_key)
        
        # ✅ INITIALIZE AMADEUS CLIENT FOR REAL API CALLS
        amadeus_api_key = os.getenv('AMADEUS_API_KEY')
        amadeus_api_secret = os.getenv('AMADEUS_API_SECRET')
        
        if not amadeus_api_key or not amadeus_api_secret:
            raise ValueError("AMADEUS_API_KEY and AMADEUS_API_SECRET must be set in environment variables!")
        
        self.amadeus_client = AmadeusHotelClient(amadeus_api_key, amadeus_api_secret)
        self.log("✅ Amadeus Hotel Client initialized successfully")
        
        # Initialize agent state
        self.hotel_search_results = []
        self.analysis_results = {}
        
        # Tool function mapping
        self.tool_functions = {
            "SearchHotels": self._tool_search_hotels,
            "AnalyzeAndFilter": self._tool_analyze_and_filter,
            "ReflectAndModifySearch": self._tool_reflect_and_modify_search,
            "ProvideRecommendation": self._tool_provide_recommendation,
            "FinalizeSelection": self._tool_finalize_selection
        }
        
        # Tool schema mapping
        self.tool_schemas = {
            "SearchHotels": SearchHotels,
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
        self.log("✅ Enhanced Pure Agentic HotelAgent initialized with REAL Amadeus API")

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
            self.log(f"🚀 Starting HotelAgent execution (max_turns={max_turns})...")
            
            # Initialize conversation history as list of properly formatted messages
            conversation_history = []
            if not continuation_message:  # Only on NEW searches, not HIL continuation
                self.hotel_search_results_search_results = [] 
                self.analysis_results = {}
                self.log("🔄 Cleared previous search results")
            
            # CRITICAL: Store original search parameters to prevent hallucination during refinement
            if not continuation_message:
                # First execution - store the original params
                self._original_params = {
                    'city': params.get('city') or params.get('city_code'),
                    'check_in_date': params.get('check_in_date'),
                    'check_out_date': params.get('check_out_date'),
                    'adults': params.get('adults', 2)
                }
            
            # Add initial user message or continuation message
            if continuation_message:
                self.log("📥 Resuming with human feedback...")
                # Include context reminder with original params
                context = f"""CONTEXT REMINDER: You are searching for hotels in {self._original_params['city']}, 
check-in {self._original_params['check_in_date']}, check-out {self._original_params['check_out_date']}, 
for {self._original_params['adults']} adults. You MUST maintain these location and date parameters.

"""
                user_text = context + continuation_message.get('content', '')
            else:
                # Build EXPLICIT initial user message that triggers SearchHotels call
                city = self._original_params['city']
                check_in = self._original_params['check_in_date']
                check_out = self._original_params['check_out_date']
                adults = self._original_params['adults']
                
                user_text = f"""Search for hotels with these parameters:
- City: {city}
- Check-in: {check_in}
- Check-out: {check_out}
- Adults: {adults}

Call the SearchHotels tool now with these exact parameters."""
            
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
                    return self._force_completion()
            
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
    
    def _tool_search_hotels(self, params: SearchHotels) -> Dict[str, Any]:
        """
        Tool Implementation: Search for hotels using REAL Amadeus API.
        
        AUTONOMOUS ERROR CORRECTION: Passes errors to LLM instead of crashing.
        """
        self.log(f"🔍 Searching REAL hotels via Amadeus in: {params.city_code}")
        
        # Call REAL Amadeus API (returns hotels or error dict)
        result = self._search_hotels_real_api(params)
        
        # Check if it's an error response
        if isinstance(result, dict) and not result.get('success', True):
            # API call failed - return error to LLM for autonomous correction
            self.log(f"❌ API Error: {result.get('error')}", "ERROR")
            return result
        
        # Success - store results
        hotels = result
        self.hotel_search_results.extend(hotels)

        return {
            "success": True,
            "hotels_found_this_call": len(hotels),
            "total_hotels_stored": len(self.hotel_search_results),
            "message": f"✅ Real hotel data from Amadeus API stored. Found {len(hotels)} hotels.",
        }
    
    def _tool_analyze_and_filter(self, params: AnalyzeAndFilter) -> Dict[str, Any]:
        """Tool Implementation: Analyze and filter hotels."""
        
        self.log(f"📊 Analyzing {len(self.hotel_search_results)} stored hotels...")
        filtered_hotels = self.hotel_search_results.copy()
        
        # Apply default ranking by rating (descending) then price (ascending)
        filtered_hotels.sort(key=lambda h: (-h['rating'], h['price']))

        self.analysis_results['last_filtered_hotels'] = filtered_hotels
        
        return {
            "success": True,
            "filtered_count": len(filtered_hotels),
            "message": f"Analysis complete. {len(filtered_hotels)} hotels match constraints and are ranked by rating and price.",
            "top_3_summary": [{"id": h['id'], "name": h['name'], "price": h['price'], "rating": h['rating']} for h in filtered_hotels[:3]]
        }
    
    def _tool_reflect_and_modify_search(self, params: ReflectAndModifySearch) -> Dict[str, Any]:
        """Tool Implementation: Record reflection and prepare for new search."""
        self.log("🧠 Agent Reflection:")
        self.log(f"   Reasoning: {params.reasoning}")
        
        return {
            "success": True,
            "message": f"Reflection recorded. New strategy: {params.reasoning}. Please call 'SearchHotels' with the new parameters to proceed."
        }

    def _tool_provide_recommendation(self, params: ProvideRecommendation) -> Dict[str, Any]:
        """Tool Implementation: Store recommendation and signal HIL pause."""
        self.log(f"⭐ Recommendation provided for {len(params.top_hotel_ids)} hotels.")
        self.analysis_results['last_recommendation'] = params.model_dump()
        
        return {
            "success": True,
            "message": "Recommendation prepared. Waiting for Orchestrator to pause for human input."
        }
    
    def _tool_finalize_selection(self, params: FinalizeSelection) -> Dict[str, Any]:
        """Tool Implementation: Finalize the human's hotel selection and return SUCCESS status."""
        self.log(f"✅ Finalizing selection: Hotel ID {params.selected_hotel_id}")
        
        # Find the selected hotel
        selected_hotel = None
        for hotel in self.hotel_search_results:
            if hotel['id'] == params.selected_hotel_id:
                selected_hotel = hotel
                break
        
        if not selected_hotel:
            self.log(f"⚠️ Selected hotel ID {params.selected_hotel_id} not found in search results", "WARN")
            # Use first hotel as fallback
            selected_hotel = self.hotel_search_results[0] if self.hotel_search_results else {}
        
        return {
            "success": True,
            "status_code": "SUCCESS",
            "final_hotel": selected_hotel,
            "confirmation": params.confirmation_message
        }
    
    # ========================================================================
    # REAL AMADEUS API INTEGRATION WITH AUTONOMOUS ERROR CORRECTION
    # ========================================================================
    
    def _search_hotels_real_api(self, params: SearchHotels) -> Union[List[Dict], Dict[str, Any]]:
        """
        Search for hotels using REAL Amadeus API.
        
        AUTONOMOUS ERROR CORRECTION: Returns error dictionaries instead of crashing,
        allowing the LLM to self-correct and retry with proper city codes.
        
        Args:
            params: Validated SearchHotels parameters
            
        Returns:
            List of hotel dicts on success, or error dict on failure
        """
        try:
            self.log("📡 Calling Amadeus API for real hotel data...")
            
            # Call Amadeus client with search parameters
            hotels = self.amadeus_client.search_hotels(
                city_code=params.city_code,
                check_in_date=params.check_in_date,
                check_out_date=params.check_out_date,
                adults=params.adults,
                max_results=params.max_results
            )
            
            self.log(f"✅ Amadeus returned {len(hotels)} real hotels")
            return hotels
            
        except Exception as e:
            error_str = str(e)
            self.log(f"❌ Amadeus API call failed: {error_str}", "ERROR")
            
            # AUTONOMOUS ERROR CORRECTION: Return error dict with guidance
            # This allows the LLM to understand the error and self-correct
            error_response = {
                "success": False,
                "error": f"Amadeus API error: {error_str}",
                "error_details": {
                    "city_code_attempted": params.city_code,
                    "check_in_date": params.check_in_date,
                    "check_out_date": params.check_out_date
                }
            }
            
            # Add specific guidance based on error type
            if "Invalid city code format" in error_str or "city code" in error_str.lower():
                error_response["suggested_fix"] = (
                    f"City codes must be IATA codes (3 letters). "
                    f"Convert '{params.city_code}' to proper IATA code. "
                    f"Examples: 'Madrid'→'MAD', 'Barcelona'→'BCN', 'Paris'→'PAR', 'London'→'LON'"
                )
            elif "400" in error_str:
                error_response["suggested_fix"] = (
                    "Check that all parameters are in correct format: "
                    "city_code (3-letter IATA), dates (YYYY-MM-DD), adults (integer)"
                )
            else:
                error_response["suggested_fix"] = "Review all search parameters and try again with valid IATA codes"
            
            return error_response
    
    # ========================================================================
    # HIL AND FINAL RESPONSE FORMATTING
    # ========================================================================
    
    def _format_recommendation_for_pause(self) -> Dict[str, Any]:
        """Formats the output when the agent needs human input (HIL PAUSE)."""
        rec = self.analysis_results['last_recommendation']
        hotel_map = {h['id']: h for h in self.hotel_search_results}
        recommended_hotels = [hotel_map[hid] for hid in rec['top_hotel_ids'] if hid in hotel_map]
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": "HIL_PAUSE_REQUIRED",
            "recommendation_summary": rec['summary'],
            "recommended_hotels": recommended_hotels
        }

    def _format_final_response(self, selected_id: Optional[str] = None) -> Dict[str, Any]:
        """Formats the final structured output after human selection (HIL TERMINATION)."""
        
        if selected_id:
            final_hotel = next((h for h in self.hotel_search_results if h['id'] == selected_id), None)
            summary = f"User selected the hotel ID: {selected_id}. Final hotel secured."
        else:
            final_hotel = None
            summary = "Agent completed its task but no final selection was provided."

        return {
            "success": True,
            "agent": self.name,
            "status_code": "SUCCESS",
            "recommendation_summary": summary,
            "final_hotel": final_hotel
        }

    def _force_completion(self) -> Dict[str, Any]:
        """Fallback to force a completion if max iterations reached."""
        top_hotels = self.analysis_results.get('last_filtered_hotels', [])
        
        if not top_hotels:
            status = "STATUS_NO_RESULTS_FOUND"
            summary = "Search failed to return any hotels."
        else:
            status = "STATUS_INCOMPLETE_LOOP"
            summary = "Agent reached iteration limit before human pause or final recommendation. Returning best available analysis."

        return {
            "success": False,
            "agent": self.name,
            "status_code": status,
            "summary": summary,
            "recommended_hotels": top_hotels[:3]
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
        tool_list = [SearchHotels, AnalyzeAndFilter, ReflectAndModifySearch, ProvideRecommendation, FinalizeSelection]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        return tools

    def _build_system_instruction(self) -> str:
        """
        System instruction for autonomous hotel search with error recovery.
        
        The LLM handles ALL city code conversions autonomously using its training knowledge.
        NO hardcoded logic - the agent figures it out.
        """
        return """You are a highly autonomous Hotel Search Agent with error recovery capabilities.

    YOUR EFFICIENT WORKFLOW (HIL):
    1. **Initial Search**: Call `SearchHotels` with the city provided by user
    2. **Error Recovery** (if API rejects city format):
    a. Call `ReflectAndModifySearch` to analyze the error
    b. **IMMEDIATELY call `SearchHotels` again** with corrected city code
    c. Use your knowledge of IATA airport codes (MAD for Madrid, PAR for Paris, etc.)
    d. NEVER stop after reflection - you MUST retry the search
    3. **Analyze Results**: Once you have hotels, call `AnalyzeAndFilter`
    4. **Provide Options**: Call `ProvideRecommendation` to pause for user selection
    5. **Handle Feedback**: Process user choice or refinement requests

    CRITICAL ERROR RECOVERY RULES:
    - If you get error "Invalid city code format" → This means Amadeus needs IATA airport code
    - After `ReflectAndModifySearch` → MANDATORY to call `SearchHotels` again
    - Use your knowledge to convert: Madrid→MAD, Paris→PAR, London→LON, Copenhagen→CPH, etc.
    - If unsure of IATA code, try the 3-letter abbreviation of the city name
    - NEVER give text response when you should call a tool
    - Maximum 2 search attempts per city (initial + 1 retry)

    EXAMPLE SUCCESS FLOW:
    Turn 1: SearchHotels(city_code="Madrid") → ERROR "Invalid city code format"
    Turn 2: ReflectAndModifySearch(reasoning="Need IATA code. Madrid = MAD")
    Turn 3: SearchHotels(city_code="MAD") → SUCCESS ✅
    Turn 4: AnalyzeAndFilter() → SUCCESS
    Turn 5: ProvideRecommendation() → HIL PAUSE

    EXAMPLE FAILURE (DO NOT DO THIS):
    Turn 1: SearchHotels(city_code="Madrid") → ERROR
    Turn 2: ReflectAndModifySearch(reasoning="Need MAD instead")
    Turn 3: [Gives text response] → WRONG! ❌ You MUST call SearchHotels again!

    Remember: After reflection, ACTION is required, not explanation!"""