import json
from typing import Dict, Any, List, Optional
import sys
import inspect
from pathlib import Path
import google.generativeai as genai
from google.generativeai import types as genai_types
from google.ai import generativelanguage as glm
from pydantic import BaseModel, Field, ValidationError

# Add mcp-servers to path for Google Places client
mcp_path = Path(__file__).parent.parent.parent / 'mcp-servers'
sys.path.insert(0, str(mcp_path))

from places.google_places_client import GooglePlacesClient

# --- HIL Status Codes ---
HIL_PAUSE_REQUIRED = "HIL_PAUSE_REQUIRED"
SUCCESS = "SUCCESS"
FINAL_CHOICE = "FINAL_CHOICE"
REFINE_SEARCH = "REFINE_SEARCH"

# =============================================================================
# BASE AGENT (CLEANED)
# The debugging line was removed from here.
# =============================================================================

class BaseAgent:
    """Placeholder for BaseAgent class with logging and utility methods."""
    def __init__(self, name, api_key):
        self.name = name
        self.api_key = api_key
        # Ensure your external BaseAgent.py is also clean if you use one
        
    def log(self, message: str, level: str = "INFO"):
        print(f"[{self.name}][{level}] {message}")
    
    def format_error(self, e: Exception) -> Dict[str, Any]:
        return {"success": False, "error": f"Agent Error: {str(e)}"}

# =============================================================================
# TOOL SCHEMAS (Product-Grade Enhancements)
# =============================================================================

class FilterConstraints(BaseModel):
    """Structured filtering constraints for restaurant search."""
    min_rating: Optional[float] = Field(4.0, description="Minimum rating required (e.g., 4.5).")
    price_level: Optional[int] = Field(None, description="Price level 1-4 (1=Cheap, 4=Very Expensive).")
    cuisine_types: List[str] = Field(default_factory=list, description="Preferred cuisines (e.g., ['italian', 'japanese']).")
    dietary_restrictions: List[str] = Field(default_factory=list, description="Dietary needs (e.g., ['vegetarian', 'vegan']).")
    atmosphere: List[str] = Field(default_factory=list, description="Desired vibe (e.g., ['romantic', 'family_friendly']).")
    open_now: Optional[bool] = Field(None, description="Only return currently open restaurants.")

class SearchRestaurants(BaseModel):
    """Tool for searching restaurant options using Google Places API."""
    city: str = Field(..., description="City name for restaurant search (e.g., 'Paris', 'Tokyo').")
    constraints: FilterConstraints = Field(default_factory=FilterConstraints, description="Structured filtering constraints to apply immediately to the API search.")
    proximity_location: Optional[str] = Field(None, description="A landmark, street, or hotel name to prioritize results near this location.")
    target_datetime: Optional[str] = Field(None, description="Target visit date/time (ISO 8601 or YYYY-MM-DD HH:MM) to check opening hours.")
    max_results: int = Field(15, description="Maximum number of restaurants to return (default: 15).")

class AnalyzeAndFilter(BaseModel):
    """Tool for analyzing and ranking restaurant search results."""
    analysis_goal: str = Field(..., description="Primary ranking goal: 'best_rated', 'best_value', 'closest_to_proximity_location', 'most_popular'.")
    top_n: int = Field(5, description="Number of top restaurants to recommend (default: 5).")

class ReflectAndModifySearch(BaseModel):
    """Tool for strategic reflection and search modification based on feedback."""
    reasoning: str = Field(..., description="Detailed explanation of why previous search failed or how to adjust based on human feedback.")
    new_search_parameters: SearchRestaurants = Field(..., description="Complete new parameters for the next SearchRestaurants call.")

class ProvideRecommendation(BaseModel):
    """Tool for providing final restaurant recommendations and signaling HIL pause."""
    top_restaurant_ids: List[str] = Field(..., description="List of 3-5 best restaurant IDs ranked by the LLM.")
    reasoning: str = Field(..., description="Detailed reasoning for why these restaurants were selected.")
    summary: str = Field(..., description="Brief summary comparing options and asking user to choose or provide refinement feedback.")
    user_input_required: bool = Field(True, description="MUST be True. Signals Orchestrator to pause for human input.")

# =============================================================================
# ENHANCED PURE AGENTIC RESTAURANT AGENT (FIXED)
# =============================================================================

class RestaurantAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str, places_api_key: str):
        super().__init__("RestaurantAgent", gemini_api_key)
        self.places_client = GooglePlacesClient(places_api_key)
        
        # --- DEBUG LINE NOW CORRECTLY PLACED ---
        try:
            print(f"\n>>>> DEBUG: RestaurantAgent is loading client from: {inspect.getfile(self.places_client.__class__)}")
        except Exception:
             print("\n>>>> DEBUG: Could not determine client file path.")
        # ---------------------------------------
        
        self.restaurant_search_results = []
        self.analysis_results = {}
        
        self.tool_functions = {
            "SearchRestaurants": self._tool_search_restaurants,
            "AnalyzeAndFilter": self._tool_analyze_and_filter,
            "ReflectAndModifySearch": self._tool_reflect_and_modify_search,
            "ProvideRecommendation": self._tool_provide_recommendation
        }
        
        self.tool_schemas = {
            "SearchRestaurants": SearchRestaurants,
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
        self.log("✅ Product-Grade RestaurantAgent initialized with Google Places API")

    # =========================================================================
    # PUBLIC ENTRY POINT
    # =========================================================================

    def execute(self, params: Dict[str, Any], continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 5) -> Dict[str, Any]:
        chat = self.model.start_chat()
        
        if continuation_message:
            prompt = f"The user has reviewed the recommendations and provided feedback: {json.dumps(continuation_message)}. Use your tools to refine results or confirm the final choice."
            self.log(f"🔄 Resuming search based on human feedback: {continuation_message.get('feedback', 'New constraints/choice')}")
            
            if continuation_message.get('status') == FINAL_CHOICE:
                self.log(f"✅ User selected restaurant ID: {continuation_message.get('restaurant_id')}")
                return self._format_final_response(selected_id=continuation_message.get('restaurant_id'))
        else:
            prompt = f"Find and recommend restaurants using an efficient strategy (search, analyze, recommend) based on: {json.dumps(params)}"
            self.log(f"▶️ Starting initial restaurant search for: {params.get('city')}")

        response = chat.send_message(prompt)

        for i in range(max_turns):
            current_function_calls = []
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        current_function_calls.append(part.function_call)
            
            if not current_function_calls:
                self.log(f"❗ Turn {i+1}: LLM stopped without calling a tool. Text: {getattr(response, 'text', 'No text')}", "WARN")
                break

            tool_results = []
            
            for func_call in current_function_calls:
                tool_name = func_call.name
                tool_args = self._convert_proto_to_dict(func_call.args)
                
                try:
                    result = self._execute_tool(tool_name, tool_args)
                    tool_results.append(self._create_tool_response(func_call, result))
                    
                    if tool_name == 'ProvideRecommendation':
                        self.log("⏸️ RestaurantAgent is ready for Human-in-the-Loop input.")
                        return self._format_recommendation_for_pause()
                        
                except Exception as e:
                    self.log(f"❌ Tool execution failed for {tool_name}: {e}", "ERROR")
                    error_result = {"success": False, "error": f"Tool error: {str(e)}"}
                    tool_results.append(self._create_tool_response(func_call, error_result))
            
            tool_response_content = glm.Content(
                role="function",
                parts=tool_results
            )
            response = chat.send_message(tool_response_content)
            
        return self._force_completion()

    # =========================================================================
    # TOOL IMPLEMENTATION METHODS
    # =========================================================================

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        schema = self.tool_schemas.get(tool_name)
        func = self.tool_functions.get(tool_name)
        if not schema or not func:
            raise ValueError(f"Unknown tool or function: {tool_name}")
        validated_args = schema(**tool_args)
        return func(validated_args)
    
    def _tool_search_restaurants(self, params: SearchRestaurants) -> Dict[str, Any]:
        self.log(f"🔍 Searching restaurants in: {params.city}")
        
        # FIX: Changed 'location' to 'city' to match the updated client signature.
        # This fixes the 'unexpected keyword argument' if the client is properly loaded.
        restaurants = self.places_client.search_restaurants(
            city=params.city,
            proximity_location=params.proximity_location, 
            target_datetime=params.target_datetime,
            max_results=params.max_results,
            constraints=params.constraints.model_dump() # Passing constraints dict
        )
        
        current_ids = {r['id'] for r in self.restaurant_search_results}
        new_restaurants = [r for r in restaurants if r['id'] not in current_ids]
        self.restaurant_search_results.extend(new_restaurants)

        sample_preview = []
        for r in (new_restaurants[:3] if new_restaurants else restaurants[:3]):
            photo_ref = None
            if 'photos' in r and len(r['photos']) > 0:
                photo_ref = r['photos'][0].get('name') or r['photos'][0].get('photo_reference')
                
            sample_preview.append({
                "id": r['id'], 
                "name": r['name'], 
                "rating": r.get('rating'),
                "has_photo": bool(photo_ref)
            })

        return {
            "success": True,
            "restaurants_found_this_call": len(restaurants),
            "total_restaurants_stored": len(self.restaurant_search_results),
            "message": f"Found {len(restaurants)} restaurants in {params.city}.",
            "sample_restaurants": sample_preview
        }
    
    def _tool_analyze_and_filter(self, params: AnalyzeAndFilter) -> Dict[str, Any]:
        if not self.restaurant_search_results:
            return {"success": False, "message": "No restaurants stored. Call SearchRestaurants first."}

        self.log(f"📊 Ranking {len(self.restaurant_search_results)} restaurants by: {params.analysis_goal}")
        
        ranked_restaurants = self.restaurant_search_results.copy()
        
        if params.analysis_goal == 'best_rated':
            ranked_restaurants.sort(key=lambda r: r.get('rating', 0), reverse=True)
        elif params.analysis_goal == 'most_popular':
            ranked_restaurants.sort(key=lambda r: r.get('user_ratings_total', 0), reverse=True)
        elif params.analysis_goal == 'best_value':
            ranked_restaurants.sort(key=lambda r: (r.get('rating', 0), -r.get('price_level', 5)), reverse=True)
        elif params.analysis_goal == 'closest_to_proximity_location':
            ranked_restaurants.sort(key=lambda r: r.get('distance_meters', float('inf')))
        else:
            ranked_restaurants.sort(key=lambda r: r.get('rating', 0), reverse=True)

        self.analysis_results['last_filtered_restaurants'] = ranked_restaurants[:params.top_n]
        
        return {
            "success": True,
            "total_analyzed": len(self.restaurant_search_results),
            "message": f"Ranked by {params.analysis_goal}. Top {params.top_n} selected.",
            "top_summary": [{"id": r['id'], "name": r['name'], "rating": r['rating'], "address": r.get('formatted_address')} for r in ranked_restaurants[:params.top_n]]
        }
    
    def _tool_reflect_and_modify_search(self, params: ReflectAndModifySearch) -> Dict[str, Any]:
        self.log(f"🧠 Reflection: {params.reasoning}")
        return {"success": True, "message": f"Reflection recorded. Proceed with SearchRestaurants using new parameters."}

    def _tool_provide_recommendation(self, params: ProvideRecommendation) -> Dict[str, Any]:
        self.log(f"⭐ Recommendation provided for {len(params.top_restaurant_ids)} restaurants.")
        self.analysis_results['last_recommendation'] = params.model_dump()
        return {"success": True, "message": "Recommendation prepared. Waiting for HIL."}

    # =========================================================================
    # HIL AND FINAL RESPONSE FORMATTING
    # =========================================================================
    
    def _format_recommendation_for_pause(self) -> Dict[str, Any]:
        rec = self.analysis_results['last_recommendation']
        restaurant_map = {r['id']: r for r in self.restaurant_search_results}
        recommended_restaurants = [restaurant_map[rid] for rid in rec['top_restaurant_ids'] if rid in restaurant_map]
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": HIL_PAUSE_REQUIRED,
            "recommendation_summary": rec['summary'],
            "recommended_restaurants": recommended_restaurants
        }

    def _format_final_response(self, selected_id: Optional[str] = None) -> Dict[str, Any]:
        if selected_id:
            final_restaurant = next((r for r in self.restaurant_search_results if r['id'] == selected_id), None)
            summary = f"User selected restaurant ID: {selected_id}."
        else:
            final_restaurant = None
            summary = "Agent completed but no final selection provided."

        return {
            "success": True,
            "agent": self.name,
            "status_code": SUCCESS,
            "recommendation_summary": summary,
            "final_restaurant": final_restaurant
        }

    def _force_completion(self) -> Dict[str, Any]:
        top_restaurants = self.analysis_results.get('last_filtered_restaurants', [])
        if not top_restaurants:
            status = "STATUS_NO_RESULTS_FOUND"
            summary = "Search failed to return any restaurants."
        else:
            status = "STATUS_INCOMPLETE_LOOP"
            summary = "Agent reached iteration limit. Returning best available."

        return {
            "success": False,
            "agent": self.name,
            "status_code": status,
            "summary": summary,
            "recommended_restaurants": top_restaurants[:3]
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _convert_proto_to_dict(self, proto_map: Any) -> Dict[str, Any]:
        return dict(proto_map)

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any], defs: Dict[str, Any] = None) -> Dict[str, Any]:
        if defs is None:
            defs = {}
        
        sanitized = prop_schema.copy()
        
        if 'anyOf' in sanitized:
            for item in sanitized['anyOf']:
                if 'type' in item and item['type'] != 'null':
                    sanitized.update(item)
                    break
            del sanitized['anyOf']
        
        for field in ['default', 'title', '$defs', 'examples']:
            if field in sanitized:
                del sanitized[field]
        
        if 'type' in sanitized and isinstance(sanitized['type'], str):
            sanitized['type'] = sanitized['type'].upper()
        
        if sanitized.get('type') == 'ARRAY' and 'items' in sanitized:
            sanitized['items'] = self._sanitize_property_schema(sanitized['items'], defs)
        
        if sanitized.get('type') == 'OBJECT' and 'properties' in sanitized:
            sanitized['properties'] = {
                key: self._sanitize_property_schema(val, defs)
                for key, val in sanitized['properties'].items()
            }
        
        return sanitized

    def _pydantic_to_function_declaration(self, pydantic_model: Any) -> Dict[str, Any]:
        schema = pydantic_model.model_json_schema()
        name = pydantic_model.__name__
        description = schema.get("description", f"Tool for {name}")
        definitions = schema.get("$defs", {})
        required_params = schema.get("required", [])

        def expand_refs(prop_schema: Dict[str, Any], defs: Dict[str, Any]) -> Dict[str, Any]:
            if '$ref' in prop_schema:
                ref_name = prop_schema['$ref'].split('/')[-1]
                
                if ref_name in defs:
                    expanded = defs[ref_name].copy()
                    
                    if 'properties' in expanded:
                        expanded['properties'] = {
                            k: expand_refs(v, defs) 
                            for k, v in expanded['properties'].items()
                        }
                    
                    return self._sanitize_property_schema(expanded, defs)
                else:
                    return {"type": "OBJECT", "properties": {}}
            
            return self._sanitize_property_schema(prop_schema, defs)

        sanitized_properties = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            sanitized_properties[prop_name] = expand_refs(prop_schema, definitions)
        
        return {
            "name": name,
            "description": description,
            "parameters": {
                "type": "OBJECT",
                "properties": sanitized_properties,
                "required": required_params
            }
        }

    def _create_gemini_tools(self) -> List[Any]:
        tool_list = [SearchRestaurants, AnalyzeAndFilter, ReflectAndModifySearch, ProvideRecommendation]
        tools = []
        for model in tool_list:
            tools.append(genai_types.Tool(function_declarations=[self._pydantic_to_function_declaration(model)]))
        return tools

    def _build_system_instruction(self) -> str:
        return """You are a highly autonomous Restaurant Search Agent.

YOUR EFFICIENT WORKFLOW (HIL):
1. **Search**: **MUST** call `SearchRestaurants` with `constraints` (rating, dietary, atmosphere, price) and `proximity_location` (if known). Use `target_datetime` to check opening hours if relevant.
2. **Analyze & Rank**: Use `AnalyzeAndFilter` to rank results. Prioritize based on user preferences (best_rated, best_value, etc.).
3. **HIL PAUSE**: Call `ProvideRecommendation`. Set `user_input_required=True`.
4. **RESUME**: If feedback is simple ("Need cheaper"), call `SearchRestaurants` directly. If complex, call `ReflectAndModifySearch` first.
5. **FINAL CHOICE**: Confirm with `FINAL_CHOICE` signal.

CRITICAL RULES:
- Use real data from Google Places API.
- Prioritize dietary restrictions and atmosphere when selecting top candidates.
- Do not recommend closed locations if a datetime is provided."""
    
    def _create_tool_response(self, function_call: Any, result: Dict[str, Any]) -> Any:
        return glm.Part(function_response=glm.FunctionResponse(name=function_call.name, response={'result': result}))