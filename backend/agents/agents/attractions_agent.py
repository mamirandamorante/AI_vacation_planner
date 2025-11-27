import json
from typing import Dict, Any, List, Optional
import sys
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
# FLATTENED TOOL SCHEMAS (Fixed - No Nested Models)
# =============================================================================

class SearchAttractions(BaseModel):
    """
    Tool for searching attraction options using Google Places API.
    All fields flattened to avoid nested model issues with Gemini.
    """
    city: str = Field(..., description="City name for attraction search (e.g., 'Paris', 'Tokyo').")
    
    # Flattened constraint fields (no nested FilterConstraints model)
    min_rating: Optional[float] = Field(None, description="Minimum rating required (e.g., 4.5). Leave None for no filter.")
    attraction_types: Optional[List[str]] = Field(None, description="Preferred attraction categories as list (e.g., ['museum', 'park', 'historical']). Leave None for all types.")
    interests: Optional[List[str]] = Field(None, description="User interests as list (e.g., ['art', 'history', 'nature']). Leave None for no filter.")
    max_entry_fee: Optional[float] = Field(None, description="Maximum entry fee acceptable (e.g., 50.0). Leave None for no limit.")
    is_indoor_outdoor: Optional[str] = Field(None, description="Filter for 'indoor' or 'outdoor' activities. Leave None for both.")
    wheelchair_accessible: Optional[bool] = Field(None, description="Filter for wheelchair accessible locations. Leave None for no filter.")
    
    # Other search parameters
    proximity_location: Optional[str] = Field(None, description="A landmark, street, or hotel name to prioritize results near this location.")
    target_date: Optional[str] = Field(None, description="Target visit date (YYYY-MM-DD) to check for opening hours or closed days.")
    max_results: int = Field(15, description="Maximum number of attractions to return (default: 15).")

class AnalyzeAndFilter(BaseModel):
    """Tool for analyzing and ranking attraction search results."""
    analysis_goal: str = Field(..., description="Primary ranking goal: 'most_popular', 'hidden_gems', 'family_friendly', 'closest_to_proximity_location', 'accessibility_prioritized'.")
    top_n: int = Field(10, description="Number of top attractions to recommend (default: 10, adjust based on trip duration).")

class ProvideRecommendation(BaseModel):
    """Tool for providing final attraction recommendations and signaling HIL pause."""
    top_attraction_ids: List[str] = Field(..., description="List of attraction IDs ranked by the LLM (typically 5-10+).")
    reasoning: str = Field(..., description="Detailed reasoning for why these attractions were selected.")
    summary: str = Field(..., description="Brief summary comparing options.")

# =============================================================================
# ENHANCED PURE AGENTIC ATTRACTIONS AGENT
# =============================================================================

class AttractionsAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str, places_api_key: str):
        super().__init__("AttractionsAgent", gemini_api_key)
        self.places_client = GooglePlacesClient(places_api_key)
        self.attraction_search_results = []
        self.analysis_results = {}
        
        self.tool_functions = {
            "SearchAttractions": self._tool_search_attractions,
            "AnalyzeAndFilter": self._tool_analyze_and_filter,
            "ProvideRecommendation": self._tool_provide_recommendation
        }
        
        self.tool_schemas = {
            "SearchAttractions": SearchAttractions,
            "AnalyzeAndFilter": AnalyzeAndFilter,
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
        self.log("✅ Product-Grade AttractionsAgent initialized with Google Places API")

    # =========================================================================
    # PUBLIC ENTRY POINT
    # =========================================================================

    def execute(self, params: Dict[str, Any], continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 5) -> Dict[str, Any]:
        chat = self.model.start_chat()
        
        if continuation_message:
            prompt = f"The user has reviewed the recommendations and provided feedback: {json.dumps(continuation_message)}. Use your tools to refine results or confirm the final choice."
            self.log(f"🔄 Resuming search based on human feedback: {continuation_message.get('feedback', 'New constraints/choice')}")
            
            if continuation_message.get('status') == FINAL_CHOICE:
                self.log(f"✅ User selected attraction ID: {continuation_message.get('attraction_id')}")
                return self._format_final_response(selected_id=continuation_message.get('attraction_id'))
        else:
            prompt = f"Find and recommend attractions using an efficient strategy (search, analyze, recommend) based on: {json.dumps(params)}"
            self.log(f"▶️ Starting initial attraction search for: {params.get('city')}")

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
                        self.log("⏸️ AttractionsAgent is ready for Human-in-the-Loop input.")
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
    # TOOL IMPLEMENTATION METHODS (Enhanced & Fixed)
    # =========================================================================

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        schema = self.tool_schemas.get(tool_name)
        func = self.tool_functions.get(tool_name)
        if not schema or not func:
            raise ValueError(f"Unknown tool or function: {tool_name}")
        validated_args = schema(**tool_args)
        return func(validated_args)
    
    def _tool_search_attractions(self, params: SearchAttractions) -> Dict[str, Any]:
        """
        Tool Implementation: Search for attractions using Google Places API.
        Works with flattened schema (no nested constraints object).
        """
        self.log(f"🔍 Searching attractions in: {params.city}")
        
        # Build constraints dict from flattened fields
        constraints = {
            'min_rating': params.min_rating,
            'attraction_types': params.attraction_types or [],
            'interests': params.interests or [],
            'max_entry_fee': params.max_entry_fee,
            'is_indoor_outdoor': params.is_indoor_outdoor,
            'wheelchair_accessible': params.wheelchair_accessible
        }
        
        # Remove None values
        constraints = {k: v for k, v in constraints.items() if v is not None}
        
        # Call Google Places API
        attractions = self.places_client.search_attractions(
            city=params.city,
            proximity_location=params.proximity_location, 
            target_date=params.target_date,
            max_results=params.max_results,
            constraints=constraints
        )
        
        # Deduplicate and store results
        current_ids = {a['id'] for a in self.attraction_search_results}
        new_attractions = [a for a in attractions if a['id'] not in current_ids]
        self.attraction_search_results.extend(new_attractions)

        # Create sample preview
        sample_preview = []
        for a in (new_attractions[:3] if new_attractions else attractions[:3]):
            photo_ref = None
            if 'photos' in a and len(a['photos']) > 0:
                photo_ref = a['photos'][0].get('name') or a['photos'][0].get('photo_reference')
                
            sample_preview.append({
                "id": a['id'], 
                "name": a['name'], 
                "rating": a.get('rating'),
                "has_photo": bool(photo_ref)
            })

        return {
            "success": True,
            "attractions_found_this_call": len(attractions),
            "total_attractions_stored": len(self.attraction_search_results),
            "message": f"Found {len(attractions)} attractions in {params.city}.",
            "sample_attractions": sample_preview
        }
    
    def _tool_analyze_and_filter(self, params: AnalyzeAndFilter) -> Dict[str, Any]:
        """
        Tool Implementation: Analyze and rank attractions.
        Includes accessibility and proximity logic.
        """
        if not self.attraction_search_results:
            return {"success": False, "message": "No attractions stored. Call SearchAttractions first."}

        self.log(f"📊 Ranking {len(self.attraction_search_results)} attractions by: {params.analysis_goal}")
        
        ranked_attractions = self.attraction_search_results.copy()
        
        if params.analysis_goal == 'most_popular':
            ranked_attractions.sort(key=lambda a: a.get('user_ratings_total', 0), reverse=True)
        elif params.analysis_goal == 'hidden_gems':
            ranked_attractions.sort(key=lambda a: (a.get('rating', 0), -a.get('user_ratings_total', 999999)), reverse=True)
        elif params.analysis_goal == 'closest_to_proximity_location':
            ranked_attractions.sort(key=lambda a: a.get('distance_meters', float('inf')))
        elif params.analysis_goal == 'accessibility_prioritized':
            ranked_attractions.sort(key=lambda a: (a.get('accessibility', {}).get('wheelchair_accessible_entrance', False), a.get('rating', 0)), reverse=True)
        else:
            ranked_attractions.sort(key=lambda a: a.get('rating', 0), reverse=True)

        self.analysis_results['last_filtered_attractions'] = ranked_attractions[:params.top_n]
        
        return {
            "success": True,
            "total_analyzed": len(self.attraction_search_results),
            "message": f"Ranked by {params.analysis_goal}. Top {params.top_n} selected.",
            "top_summary": [{"id": a['id'], "name": a['name'], "rating": a['rating'], "address": a.get('formatted_address')} for a in ranked_attractions[:params.top_n]]
        }

    def _tool_provide_recommendation(self, params: ProvideRecommendation) -> Dict[str, Any]:
        self.log(f"⭐ Recommendation provided for {len(params.top_attraction_ids)} attractions.")
        self.analysis_results['last_recommendation'] = params.model_dump()
        return {"success": True, "message": "Recommendation prepared. Waiting for HIL."}

    # =========================================================================
    # HIL AND FINAL RESPONSE FORMATTING
    # =========================================================================
    
    def _format_recommendation_for_pause(self) -> Dict[str, Any]:
        rec = self.analysis_results['last_recommendation']
        attraction_map = {a['id']: a for a in self.attraction_search_results}
        recommended_attractions = [attraction_map[aid] for aid in rec['top_attraction_ids'] if aid in attraction_map]
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": HIL_PAUSE_REQUIRED,
            "recommendation_summary": rec['summary'],
            "recommended_attractions": recommended_attractions
        }

    def _format_final_response(self, selected_id: Optional[str] = None) -> Dict[str, Any]:
        if selected_id:
            final_attraction = next((a for a in self.attraction_search_results if a['id'] == selected_id), None)
            summary = f"User selected attraction ID: {selected_id}."
        else:
            final_attraction = None
            summary = "Agent completed but no final selection provided."

        return {
            "success": True,
            "agent": self.name,
            "status_code": SUCCESS,
            "recommendation_summary": summary,
            "final_attraction": final_attraction
        }

    def _force_completion(self) -> Dict[str, Any]:
        top_attractions = self.analysis_results.get('last_filtered_attractions', [])
        if not top_attractions:
            status = "STATUS_NO_RESULTS_FOUND"
            summary = "Search failed to return any attractions."
        else:
            status = "STATUS_INCOMPLETE_LOOP"
            summary = "Agent reached iteration limit. Returning best available."

        return {
            "success": False,
            "agent": self.name,
            "status_code": status,
            "summary": summary,
            "recommended_attractions": top_attractions[:3]
        }

    # =========================================================================
    # HELPER METHODS (FIXED SCHEMA CONVERSION)
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
        tool_list = [SearchAttractions, AnalyzeAndFilter, ProvideRecommendation]
        tools = []
        for model in tool_list:
            tools.append(genai_types.Tool(function_declarations=[self._pydantic_to_function_declaration(model)]))
        return tools

    def _build_system_instruction(self) -> str:
        """
        Simplified system instruction to reduce Gemini confusion.
        Focuses on clear workflow without complex calculations.
        """
        return """You are an Attractions Search Agent. Find diverse attractions for vacation planning.

TOOLS AVAILABLE:
- SearchAttractions: Search for attractions in a city
- AnalyzeAndFilter: Rank attractions by quality/popularity
- ProvideRecommendation: Return final recommendations

YOUR WORKFLOW:

STEP 1: INITIAL SEARCH
- Call SearchAttractions with the city (use any filters if user specified them)
- Note how many results you got

STEP 2: CHECK IF YOU NEED MORE
- For 5+ day trips: Aim for 10+ attractions (to avoid repetition)
- For 3-4 day trips: 6-8 attractions is fine
- If you found enough → Continue to STEP 3
- If you need more → Call SearchAttractions again with different attraction_types

STEP 3: ANALYZE
- Call AnalyzeAndFilter to rank all attractions you found
- Use top_n to match trip needs:
  * 3-day trip: top_n=6
  * 5-day trip: top_n=10
  * 7-day trip: top_n=14

STEP 4: RECOMMEND
- Call ProvideRecommendation with your filtered list
- Include ALL attraction IDs from your filtered list

IMPORTANT RULES:
- Don't search more than 3 times
- The parameters contain: city, departure_date, return_date, proximity_location
- Calculate trip days from dates to determine how many attractions needed
- More days = more attractions to avoid repetition in itinerary

EXAMPLE - 5 DAY TRIP:
Turn 1: SearchAttractions(city="Madrid") → Found 6 attractions
Turn 2: SearchAttractions(city="Madrid", attraction_types=["museum", "park"]) → Found 5 more = 11 total
Turn 3: AnalyzeAndFilter(analysis_goal="most_popular", top_n=10) → Rank top 10
Turn 4: ProvideRecommendation(top_attraction_ids=[...10 ids...]) → Done!

Remember: Trip duration determines how many attractions you need!"""

    def _create_tool_response(self, function_call: Any, result: Dict[str, Any]) -> Any:
        return glm.Part(function_response=glm.FunctionResponse(name=function_call.name, response={'result': result}))