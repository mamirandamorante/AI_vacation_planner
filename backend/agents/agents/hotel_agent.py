import json
from typing import Dict, Any, List, Optional, Union
import google.generativeai as genai
from google.generativeai import types as genai_types 
from google.ai import generativelanguage as glm
from pydantic import BaseModel, Field, ValidationError

# --- HIL Status Codes (Match Orchestrator) ---
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
# TOOL SCHEMAS
# =============================================================================

class FilterConstraints(BaseModel):
    """Structured filtering constraints derived from user requirements."""
    max_price: Optional[int] = Field(None, description="Maximum total price allowed in USD per night.")
    min_rating: Optional[float] = Field(4.0, description="Minimum star rating required (e.g., 4.5).")
    required_amenities: List[str] = Field(default_factory=list, description="List of required hotel amenities (e.g., ['free_wifi', 'pool', 'concierge']).")

class RankingWeights(BaseModel):
    """Defines the relative importance of factors for ranking hotels."""
    price_weight: float = Field(0.4, description="Weight (0.0 to 1.0) for prioritizing lower price.")
    rating_weight: float = Field(0.4, description="Weight (0.0 to 1.0) for prioritizing higher user rating.")
    distance_weight: float = Field(0.2, description="Weight (0.0 to 1.0) for prioritizing lower distance to center/POI.")

class SearchHotels(BaseModel):
    """Tool for searching hotel options."""
    city_code: str = Field(..., description="City IATA code or name (e.g., 'NYC', 'Paris').")
    check_in_date: str = Field(..., description="Check-in date in YYYY-MM-DD format.")
    check_out_date: str = Field(..., description="Check-out date in YYYY-MM-DD format.")
    adults: int = Field(1, description="Number of adults.")
    search_location: Optional[str] = Field(None, description="Specific Point of Interest (e.g., 'Eiffel Tower') or neighborhood name (e.g., 'Le Marais').")
    search_radius_km: Optional[float] = Field(None, description="Search radius in kilometers around the specified search_location (Max 5.0).")

class AnalyzeAndFilter(BaseModel):
    """Tool for analyzing and filtering hotel search results against complex user criteria."""
    analysis_goal: str = Field(..., description="Primary analysis type: 'lowest_price', 'best_location', 'best_value'.")
    constraints: FilterConstraints = Field(default_factory=FilterConstraints, description="Structured filtering constraints derived from user requirements.")
    ranking_weights: RankingWeights = Field(default_factory=RankingWeights, 
        description="The relative importance of price, rating, and distance for the final recommendation score.")

class ReflectAndModifySearch(BaseModel):
    """Tool for strategic reflection and search modification."""
    reasoning: str = Field(..., description="Detailed explanation of why previous search failed or how to adjust the search based on human feedback.")
    new_search_parameters: SearchHotels = Field(..., description="Complete new parameters for the next search_hotels call.")

class ProvideRecommendation(BaseModel):
    """Tool for providing final hotel recommendations and explicitly signaling the need for user feedback."""
    top_hotel_ids: List[str] = Field(..., description="List of the 3-5 best hotel IDs ranked by the LLM.")
    reasoning: str = Field(..., description="Detailed reasoning for why these hotels were selected.")
    summary: str = Field(..., description="Brief summary comparing options and explicitly asking the user to choose one or provide refinement feedback.")
    user_input_required: bool = Field(True, description="MUST be True. Signals the Orchestrator to pause and ask the human to choose a hotel or provide refinement feedback.")


# =============================================================================
# ENHANCED PURE AGENTIC HOTEL AGENT
# =============================================================================

class HotelAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str, travel_api_client: Any = None):
        
        # --- FIX: Use gemini_api_key which is the argument name ---
        super().__init__("HotelAgent", gemini_api_key)
        
        self.api_client = travel_api_client # Placeholder for Amadeus/Google Places client
        
        if not travel_api_client:
            self.log("⚠️ No API client provided - will use MOCK data", "WARN")
            
        self.hotel_search_results = []
        self.analysis_results = {}
        
        self.tool_functions = {
            "SearchHotels": self._tool_search_hotels,
            "AnalyzeAndFilter": self._tool_analyze_and_filter,
            "ReflectAndModifySearch": self._tool_reflect_and_modify_search,
            "ProvideRecommendation": self._tool_provide_recommendation
        }
        
        self.tool_schemas = {
            "SearchHotels": SearchHotels,
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
        self.log("✅ Enhanced Pure Agentic HotelAgent initialized")


    # =========================================================================
    # PUBLIC ENTRY POINT (HIL Flow Controller)
    # =========================================================================

    def execute(self, params: Dict[str, Any], continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 5) -> Dict[str, Any]:
        """
        Triggers the autonomous process. Handles initial search or continuation 
        (resumption) based on user feedback.
        """
        
        chat = self.model.start_chat()
        
        if continuation_message:
            prompt = f"The user has reviewed the last recommendations and provided this feedback: {json.dumps(continuation_message)}. Analyze the results and immediately use your tools (ReflectAndModifySearch or AnalyzeAndFilter) to meet the new request. If the user chose a hotel, simply confirm."
            self.log(f"🔄 Resuming search based on human feedback: {continuation_message.get('feedback', 'New constraints/choice')}")
            
            if continuation_message.get('status') == FINAL_CHOICE:
                 self.log(f"✅ User selected hotel ID: {continuation_message.get('hotel_id')}")
                 return self._format_final_response(selected_id=continuation_message.get('hotel_id'))
        
        else:
            prompt = f"Find and recommend hotels with a complete strategy (search, analyze, recommend) based on the following initial parameters: {json.dumps(params)}"
            self.log(f"▶️ Starting initial hotel search for: {params.get('city_code')}")

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
            
        return self._force_completion()


    # =========================================================================
    # TOOL CONVERSION & HELPER FIXES (For robust tool calling - Omitted logic for brevity)
    # =========================================================================

    def _convert_proto_to_dict(self, proto_map: Any) -> Dict[str, Any]:
        return dict(proto_map)

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
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
        tool_list = [SearchHotels, AnalyzeAndFilter, ReflectAndModifySearch, ProvideRecommendation]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        return tools


    def _build_system_instruction(self) -> str:
        return """You are a highly autonomous Hotel Search Agent. Your goal is to find the best hotels and pause the workflow for human confirmation.

YOUR WORKFLOW (HIL):
1.  **Search**: Call `SearchHotels`.
2.  **Analyze**: Use `AnalyzeAndFilter` to apply constraints, use the provided `ranking_weights`, and identify 3-5 top options.
3.  **HIL PAUSE**: Call `ProvideRecommendation`. This tool MUST set `user_input_required=True` to signal the orchestrator to pause and ask the human for a choice.
4.  **RESUME**: If the orchestrator provides human feedback (e.g., "Too expensive, search for cheaper"), **you MUST call `ReflectAndModifySearch`** to articulate your new strategy and adjusted search/filter parameters before rerunning the search.
5.  **FINAL CHOICE**: If the orchestrator provides a `FINAL_CHOICE` message, confirm the choice and terminate the loop by returning the final result structure.

CRITICAL RULES:
- Maintain persistent memory of ALL search results across iterations.
- Never choose a hotel yourself; always use `ProvideRecommendation` to get human confirmation/refinement."""


    # =========================================================================
    # TOOL IMPLEMENTATION METHODS
    # =========================================================================

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        schema = self.tool_schemas.get(tool_name)
        func = self.tool_functions.get(tool_name)
        validated_args = schema(**tool_args)
        return func(validated_args)
    
    def _tool_search_hotels(self, params: SearchHotels) -> Dict[str, Any]:
        self.log(f"🔍 Searching hotels in: {params.city_code}")
        flights = self._generate_mock_hotels(params)
        self.hotel_search_results.extend(flights)

        return {
            "success": True,
            "hotels_found_this_call": len(flights),
            "total_hotels_stored": len(self.hotel_search_results),
            "message": "Mock hotel data stored.",
        }
    
    def _tool_analyze_and_filter(self, params: AnalyzeAndFilter) -> Dict[str, Any]:
        self.log(f"📊 Analyzing {len(self.hotel_search_results)} stored hotels...")
        filtered_flights = self.hotel_search_results.copy()
        
        if params.ranking_weights:
            self.log(f"📝 Applying ranking with weights: P={params.ranking_weights.price_weight}, R={params.ranking_weights.rating_weight}")
            filtered_flights.sort(key=lambda h: (h['rating'], -h['price']), reverse=True)

        self.analysis_results['last_filtered_hotels'] = filtered_flights
        
        return {
            "success": True,
            "filtered_count": len(filtered_flights),
            "message": f"Analysis complete. {len(filtered_flights)} hotels match constraints and are ranked.",
            "top_3_summary": [{"id": h['id'], "name": h['name'], "price": h['price'], "rating": h['rating']} for h in filtered_flights[:3]]
        }
    
    def _tool_reflect_and_modify_search(self, params: ReflectAndModifySearch) -> Dict[str, Any]:
        self.log("🧠 Agent Reflection:")
        self.log(f"   Reasoning: {params.reasoning}")
        
        return {
            "success": True,
            "message": f"Reflection recorded. New strategy: {params.reasoning}. Please call 'SearchHotels' with the new parameters to proceed."
        }

    def _tool_provide_recommendation(self, params: ProvideRecommendation) -> Dict[str, Any]:
        self.log(f"⭐ Recommendation provided for {len(params.top_hotel_ids)} hotels.")
        self.analysis_results['last_recommendation'] = params.model_dump()
        
        return {
            "success": True,
            "message": "Recommendation prepared. Waiting for Orchestrator to pause for human input."
        }


    # =========================================================================
    # HIL and FINAL RESPONSE FORMATTING
    # =========================================================================
    
    def _format_recommendation_for_pause(self) -> Dict[str, Any]:
        rec = self.analysis_results['last_recommendation']
        hotel_map = {h['id']: h for h in self.hotel_search_results}
        recommended_hotels = [hotel_map[hid] for hid in rec['top_hotel_ids'] if hid in hotel_map]
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": HIL_PAUSE_REQUIRED,
            "recommendation_summary": rec['summary'],
            "recommended_hotels": recommended_hotels
        }

    def _format_final_response(self, selected_id: Optional[str] = None) -> Dict[str, Any]:
        
        if selected_id:
            final_hotel = next((h for h in self.hotel_search_results if h['id'] == selected_id), None)
            summary = f"User selected the hotel ID: {selected_id}. Final hotel secured."
        else:
            final_hotel = None
            summary = "Agent completed its task but no final selection was provided."

        return {
            "success": True,
            "agent": self.name,
            "status_code": SUCCESS,
            "recommendation_summary": summary,
            "final_hotel": final_hotel
        }

    def _force_completion(self) -> Dict[str, Any]:
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
        
    def _generate_mock_hotels(self, params: SearchHotels) -> List[Dict]:
        return [
            {"id": "HT001", "name": "Boutique Le Marais", "price": 450, "currency": "USD", "rating": 4.8, "mock": True, "amenities": ["free_wifi", "concierge", "breakfast"], "location": {"city": params.city_code, "distance_to_center": "0.5 km"}, "room_type": "Deluxe Suite"},
            {"id": "HT002", "name": "Classic Saint-Germain", "price": 520, "currency": "USD", "rating": 4.6, "mock": True, "amenities": ["free_wifi", "concierge", "gym"], "location": {"city": params.city_code, "distance_to_center": "1.2 km"}, "room_type": "Executive Double"},
            {"id": "HT003", "name": "Charming Budget Stay", "price": 280, "currency": "USD", "rating": 4.1, "mock": True, "amenities": ["free_wifi", "parking"], "location": {"city": params.city_code, "distance_to_center": "3.5 km"}, "room_type": "Standard Room"},
        ]