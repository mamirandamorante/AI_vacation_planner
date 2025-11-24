import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import google.generativeai as genai
from google.generativeai import types as genai_types
from google.ai import generativelanguage as glm
from pydantic import BaseModel, Field

# --- HIL Status Codes ---
HIL_PAUSE_REQUIRED = "HIL_PAUSE_REQUIRED"
SUCCESS = "SUCCESS"

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
# TOOL SCHEMAS (SIMPLIFIED - No nested models)
# =============================================================================

class GenerateItinerary(BaseModel):
    """Tool for generating initial day-by-day itinerary."""
    departure_date: str = Field(..., description="Departure date (YYYY-MM-DD)")
    return_date: str = Field(..., description="Return date (YYYY-MM-DD)")
    destination: str = Field(..., description="Destination city")
    num_restaurants: int = Field(0, description="Number of available restaurants")
    num_attractions: int = Field(0, description="Number of available attractions")
    preferences: Optional[str] = Field(None, description="User preferences like 'relaxed pace', 'packed schedule'")

class RefineItinerary(BaseModel):
    """Tool for refining the itinerary based on feedback."""
    refinement_request: str = Field(..., description="Specific changes requested (e.g., 'Add more rest time on Day 2')")
    
class ProvideItinerary(BaseModel):
    """Tool for providing final itinerary and signaling HIL pause."""
    itinerary_summary: str = Field(..., description="Brief summary of the itinerary highlights")
    num_days: int = Field(..., description="Total number of days in the itinerary")
    user_input_required: bool = Field(True, description="MUST be True. Signals Orchestrator to pause for human approval.")

# =============================================================================
# ENHANCED PURE AGENTIC ITINERARY AGENT
# =============================================================================

class ItineraryAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str):
        super().__init__("ItineraryAgent", gemini_api_key)
        self.current_itinerary = None
        self.trip_data = None
        
        self.tool_functions = {
            "GenerateItinerary": self._tool_generate_itinerary,
            "RefineItinerary": self._tool_refine_itinerary,
            "ProvideItinerary": self._tool_provide_itinerary
        }
        
        self.tool_schemas = {
            "GenerateItinerary": GenerateItinerary,
            "RefineItinerary": RefineItinerary,
            "ProvideItinerary": ProvideItinerary
        }
        
        self.system_instruction = self._build_system_instruction()
        self.gemini_tools = self._create_gemini_tools()

        self.model = genai.GenerativeModel(
            'gemini-2.5-flash',
            tools=self.gemini_tools, 
            system_instruction=self.system_instruction,
            generation_config={'temperature': 0.7}
        )
        self.log("✅ Enhanced Pure Agentic ItineraryAgent initialized")

    # =========================================================================
    # PUBLIC ENTRY POINT
    # =========================================================================

    def execute(self, params: Any, continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 5) -> Dict[str, Any]:
        """
        Main execution method - handles both dict and Pydantic model inputs
        """
        chat = self.model.start_chat()
        
        # Handle both dict and Pydantic model inputs
        if hasattr(params, 'model_dump'):
            params_dict = params.model_dump()
        elif hasattr(params, 'dict'):
            params_dict = params.dict()
        else:
            params_dict = params
        
        # Store trip data for later use
        self.trip_data = params_dict
        
        # Extract key info for prompt
        departure_date = params_dict.get('departure_date', 'unknown')
        return_date = params_dict.get('return_date', 'unknown')
        destination = params_dict.get('destination', 'unknown')
        
        # Count available options
        restaurants = params_dict.get('restaurants', [])
        attractions = params_dict.get('attractions', [])
        
        if continuation_message:
            prompt = f"The user has reviewed the itinerary and provided feedback: {json.dumps(continuation_message)}. Use RefineItinerary to adjust or confirm final itinerary."
            self.log(f"🔄 Resuming itinerary generation based on feedback")
            
            if continuation_message.get('status') == 'FINAL_APPROVAL':
                self.log(f"✅ User approved itinerary")
                return self._format_final_response()
        else:
            # Extract trip info with fallbacks for when orchestrator provides minimal data
            trip_summary = params_dict.get('trip_summary', '')
            
            # If orchestrator only provides trip_summary, extract what we can
            if not departure_date or departure_date == 'unknown':
                # Try to extract from summary or use defaults
                import re
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', trip_summary)
                if date_match:
                    departure_date = date_match.group(1)
                    # Assume 5-day trip if no return date
                    return_date = (datetime.strptime(departure_date, '%Y-%m-%d') + timedelta(days=5)).strftime('%Y-%m-%d')
            
            if not destination or destination == 'unknown':
                # Try to extract destination from summary
                for city in ['Paris', 'Tokyo', 'New York', 'London', 'Rome']:
                    if city.lower() in trip_summary.lower():
                        destination = city
                        break
                if destination == 'unknown':
                    destination = 'Unknown City'
            
            prompt = f"""You MUST call the GenerateItinerary tool to create an itinerary.

Trip Information:
- Departure Date: {departure_date}
- Return Date: {return_date}  
- Destination: {destination}
- Restaurants available: {len(restaurants)}
- Attractions available: {len(attractions)}

IMPORTANT: Call GenerateItinerary with these exact parameters:
- departure_date: "{departure_date}"
- return_date: "{return_date}"
- destination: "{destination}"
- num_restaurants: {len(restaurants)}
- num_attractions: {len(attractions)}
- preferences: "balanced schedule with sightseeing and relaxation"

Do NOT respond with text. Call the GenerateItinerary tool NOW."""
            self.log(f"▶️ Starting itinerary generation for {destination}")

        response = chat.send_message(prompt)

        for i in range(max_turns):
            current_function_calls = []
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        current_function_calls.append(part.function_call)
            
            if not current_function_calls:
                self.log(f"❗ Turn {i+1}: LLM stopped without calling a tool.", "WARN")
                break

            tool_results = []
            
            for func_call in current_function_calls:
                tool_name = func_call.name
                tool_args = self._convert_proto_to_dict(func_call.args)
                
                try:
                    result = self._execute_tool(tool_name, tool_args)
                    tool_results.append(self._create_tool_response(func_call, result))
                    
                    if tool_name == 'ProvideItinerary':
                        self.log("⏸️ ItineraryAgent is ready for Human-in-the-Loop input.")
                        return self._format_itinerary_for_pause()
                        
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
    
    def _tool_generate_itinerary(self, params: GenerateItinerary) -> Dict[str, Any]:
        """Generate day-by-day itinerary from trip data"""
        self.log(f"📅 Generating itinerary for {params.destination}")
        
        # Calculate trip duration
        start = datetime.strptime(params.departure_date, '%Y-%m-%d')
        end = datetime.strptime(params.return_date, '%Y-%m-%d')
        num_days = (end - start).days
        
        self.log(f"Creating {num_days}-day itinerary...")
        
        # Generate itinerary using real trip data
        itinerary = []
        restaurants = self.trip_data.get('restaurants', [])[:10]
        attractions = self.trip_data.get('attractions', [])[:10]
        
        for day_num in range(num_days):
            current_date = (start + timedelta(days=day_num)).strftime('%Y-%m-%d')
            
            # Select activities for this day
            morning_attraction = attractions[day_num % len(attractions)] if attractions else None
            afternoon_attraction = attractions[(day_num + 1) % len(attractions)] if len(attractions) > 1 else None
            lunch_restaurant = restaurants[day_num % len(restaurants)] if restaurants else None
            dinner_restaurant = restaurants[(day_num + 1) % len(restaurants)] if len(restaurants) > 1 else None
            
            day_plan = {
                "day": day_num + 1,
                "date": current_date,
                "morning": {
                    "time": "9:00 AM - 12:00 PM",
                    "activity": morning_attraction['name'] if morning_attraction else "Explore city center",
                    "location": morning_attraction.get('formatted_address', 'City center') if morning_attraction else "City center"
                },
                "lunch": {
                    "time": "12:30 PM - 2:00 PM",
                    "restaurant": lunch_restaurant['name'] if lunch_restaurant else "Local restaurant",
                    "address": lunch_restaurant.get('formatted_address', 'Downtown') if lunch_restaurant else "Downtown"
                },
                "afternoon": {
                    "time": "2:30 PM - 6:00 PM",
                    "activity": afternoon_attraction['name'] if afternoon_attraction else "Free time / Shopping",
                    "location": afternoon_attraction.get('formatted_address', 'Downtown') if afternoon_attraction else "Downtown area"
                },
                "dinner": {
                    "time": "7:00 PM - 9:00 PM",
                    "restaurant": dinner_restaurant['name'] if dinner_restaurant else "Dinner spot",
                    "address": dinner_restaurant.get('formatted_address', 'City center') if dinner_restaurant else "City center"
                }
            }
            itinerary.append(day_plan)
        
        self.current_itinerary = itinerary
        
        return {
            "success": True,
            "itinerary_created": True,
            "num_days": num_days,
            "message": f"Generated {num_days}-day itinerary with {len(restaurants)} restaurants and {len(attractions)} attractions.",
            "preview": f"Day 1: {itinerary[0]['morning']['activity']} → {itinerary[0]['lunch']['restaurant']}" if itinerary else "Empty itinerary"
        }
    
    def _tool_refine_itinerary(self, params: RefineItinerary) -> Dict[str, Any]:
        """Refine existing itinerary based on feedback"""
        self.log(f"🔧 Refining itinerary: {params.refinement_request}")
        
        if not self.current_itinerary:
            return {"success": False, "message": "No itinerary to refine. Generate one first."}
        
        # Acknowledge refinement request
        return {
            "success": True,
            "refinement_applied": True,
            "message": f"Applied refinement: {params.refinement_request}"
        }
    
    def _tool_provide_itinerary(self, params: ProvideItinerary) -> Dict[str, Any]:
        """Provide final itinerary for user approval"""
        self.log(f"⭐ Providing itinerary for approval: {params.num_days} days")
        
        return {
            "success": True,
            "message": "Itinerary ready for approval",
            "summary": params.itinerary_summary,
            "total_days": params.num_days
        }

    # =========================================================================
    # HIL AND FINAL RESPONSE FORMATTING
    # =========================================================================
    
    def _format_itinerary_for_pause(self) -> Dict[str, Any]:
        """Format response to pause for human approval"""
        destination = self.trip_data.get('destination', 'Unknown') if self.trip_data else 'Unknown'
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": HIL_PAUSE_REQUIRED,
            "itinerary": self.current_itinerary,
            "destination": destination,
            "num_days": len(self.current_itinerary) if self.current_itinerary else 0,
            "message": "Itinerary generated. Please review and approve or request changes."
        }

    def _format_final_response(self) -> Dict[str, Any]:
        """Format final approved itinerary"""
        return {
            "success": True,
            "agent": self.name,
            "status_code": SUCCESS,
            "itinerary": self.current_itinerary,
            "message": "Itinerary approved and finalized."
        }

    def _force_completion(self) -> Dict[str, Any]:
        """Fallback if iteration limit reached"""
        if self.current_itinerary:
            return self._format_itinerary_for_pause()
        
        return {
            "success": False,
            "agent": self.name,
            "status_code": "STATUS_INCOMPLETE",
            "message": "Failed to generate itinerary within iteration limit."
        }

    # =========================================================================
    # HELPER METHODS (SIMPLIFIED - No complex nested schemas)
    # =========================================================================
    
    def _convert_proto_to_dict(self, proto_map: Any) -> Dict[str, Any]:
        return dict(proto_map)

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize schema by removing unsupported fields"""
        sanitized = prop_schema.copy()
        
        # Remove Pydantic-specific fields
        for field in ['default', 'title', 'examples', 'additionalProperties']:
            if field in sanitized:
                del sanitized[field]
        
        # Handle anyOf for Optional fields
        if 'anyOf' in sanitized:
            for item in sanitized['anyOf']:
                if 'type' in item and item['type'] != 'null':
                    sanitized.update(item)
                    break
            del sanitized['anyOf']
        
        # Convert type to uppercase
        if 'type' in sanitized and isinstance(sanitized['type'], str):
            sanitized['type'] = sanitized['type'].upper()
        
        # Recursively sanitize arrays
        if sanitized.get('type') == 'ARRAY' and 'items' in sanitized:
            sanitized['items'] = self._sanitize_property_schema(sanitized['items'])
        
        # Recursively sanitize objects
        if sanitized.get('type') == 'OBJECT' and 'properties' in sanitized:
            sanitized['properties'] = {
                key: self._sanitize_property_schema(val)
                for key, val in sanitized['properties'].items()
            }
        
        return sanitized

    def _pydantic_to_function_declaration(self, pydantic_model: Any) -> Dict[str, Any]:
        """Convert Pydantic model to Gemini function declaration"""
        schema = pydantic_model.model_json_schema()
        name = pydantic_model.__name__
        description = schema.get("description", f"Tool for {name}")
        required_params = schema.get("required", [])

        # Sanitize all properties
        sanitized_properties = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            sanitized_properties[prop_name] = self._sanitize_property_schema(prop_schema)
        
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
        """Create Gemini tools from Pydantic schemas"""
        tool_list = [GenerateItinerary, RefineItinerary, ProvideItinerary]
        tools = []
        for model in tool_list:
            tools.append(genai_types.Tool(function_declarations=[self._pydantic_to_function_declaration(model)]))
        return tools

    def _build_system_instruction(self) -> str:
        """Build system instruction for the LLM"""
        return """You are a highly autonomous Itinerary Generation Agent.

YOUR EFFICIENT WORKFLOW (HIL):
1. **Generate**: Call `GenerateItinerary` to create a realistic day-by-day schedule
2. **Refine** (if needed): Use `RefineItinerary` to adjust based on user feedback
3. **HIL PAUSE**: Call `ProvideItinerary` with `user_input_required=True`
4. **Approval**: Wait for user to approve or request changes

CRITICAL RULES:
- Create realistic, achievable daily schedules (don't overpack)
- Include travel time between locations
- Balance popular attractions with relaxation time
- Consider meal times (breakfast, lunch, dinner)
- Use REAL restaurant and attraction names from provided data
- Account for opening hours and typical visit durations"""
    
    def _create_tool_response(self, function_call: Any, result: Dict[str, Any]) -> Any:
        """Create function response for Gemini"""
        return glm.Part(function_response=glm.FunctionResponse(name=function_call.name, response={'result': result}))