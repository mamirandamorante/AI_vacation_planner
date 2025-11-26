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

        genai.configure(api_key=gemini_api_key)

        self.model = genai.GenerativeModel(
            'gemini-2.5-flash',
            tools=self.gemini_tools, 
            system_instruction=self.system_instruction,
            generation_config={'temperature': 0.7}
        )
        self.log("✅ Enhanced Pure Agentic ItineraryAgent initialized")

    # =========================================================================
    # SYSTEM INSTRUCTION
    # =========================================================================
    
    def _build_system_instruction(self) -> str:
        """Build the system instruction for the agent."""
        return """You are an expert Itinerary Agent that creates day-by-day vacation plans.

YOU MUST ALWAYS CALL TOOLS. NEVER respond with just text.

WORKFLOW:
1. Call GenerateItinerary with trip parameters
2. Call ProvideItinerary to signal completion

DO NOT explain what you're doing. JUST CALL THE TOOLS."""

    # =========================================================================
    # PUBLIC ENTRY POINT - FIXED TO ALWAYS RETURN A DICT
    # =========================================================================

    def execute(self, params: Any, continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 5) -> Dict[str, Any]:
        """
        Main execution method - FIXED to always return a valid dict
        """
        try:
            # Handle both dict and Pydantic model inputs
            if hasattr(params, 'model_dump'):
                params_dict = params.model_dump()
            elif hasattr(params, 'dict'):
                params_dict = params.dict()
            else:
                params_dict = params
            
            # Store trip data for later use
            self.trip_data = params_dict
            
            # Extract key info
            departure_date = params_dict.get('departure_date', 'unknown')
            return_date = params_dict.get('return_date', 'unknown')
            destination = params_dict.get('destination', 'unknown')
            restaurants = params_dict.get('restaurants', [])
            attractions = params_dict.get('attractions', [])
            
            self.log(f"▶️ Starting itinerary generation for {destination}")
            self.log(f"📊 Data: {len(restaurants)} restaurants, {len(attractions)} attractions")
            
            # Generate itinerary directly - no LLM needed!
            self.log("🎯 Bypassing LLM - generating itinerary directly")
            
            # Call the tool function directly
            params_obj = GenerateItinerary(
                departure_date=departure_date,
                return_date=return_date,
                destination=destination,
                num_restaurants=len(restaurants),
                num_attractions=len(attractions),
                preferences="balanced schedule"
            )
            
            result = self._tool_generate_itinerary(params_obj)
            
            if result.get('success'):
                self.log("✅ Itinerary generated successfully")
                return self._format_itinerary_for_pause()
            else:
                self.log("❌ Itinerary generation failed", "ERROR")
                return {
                    "success": False,
                    "agent": self.name,
                    "status_code": "STATUS_INCOMPLETE",
                    "message": "Failed to generate itinerary"
                }
                
        except Exception as e:
            self.log(f"❌ Execute error: {str(e)}", "ERROR")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "agent": self.name,
                "status_code": "ERROR",
                "message": str(e)
            }

    # =========================================================================
    # TOOL IMPLEMENTATION METHODS
    # =========================================================================

    def _tool_generate_itinerary(self, params: GenerateItinerary) -> Dict[str, Any]:
        """Generate day-by-day itinerary from trip data"""
        self.log(f"📅 Generating itinerary for {params.destination}")
        
        try:
            # Calculate trip duration
            start = datetime.strptime(params.departure_date, '%Y-%m-%d')
            end = datetime.strptime(params.return_date, '%Y-%m-%d')
            num_days = (end - start).days
            
            if num_days <= 0:
                self.log("⚠️ Invalid dates - using 5 days as default", "WARN")
                num_days = 5
            
            self.log(f"Creating {num_days}-day itinerary...")
            
            # Generate itinerary using real trip data
            itinerary = []
            restaurants = self.trip_data.get('restaurants', [])[:10]
            attractions = self.trip_data.get('attractions', [])[:10]
            
            # Ensure we have data
            if not restaurants:
                self.log("⚠️ No restaurants available", "WARN")
                restaurants = [{'name': 'Local restaurant', 'formatted_address': 'Downtown', 'rating': 4.0}]
            
            if not attractions:
                self.log("⚠️ No attractions available", "WARN")
                attractions = [{'name': 'City exploration', 'formatted_address': 'City center', 'rating': 4.5}]
            
            for day_num in range(num_days):
                current_date = (start + timedelta(days=day_num)).strftime('%Y-%m-%d')
                
                # Select activities for this day
                morning_attraction = attractions[day_num % len(attractions)]
                afternoon_attraction = attractions[(day_num + 1) % len(attractions)]
                lunch_restaurant = restaurants[day_num % len(restaurants)]
                dinner_restaurant = restaurants[(day_num + 1) % len(restaurants)]
                
                day_plan = {
                    "day": day_num + 1,
                    "date": current_date,
                    "morning": {
                        "time": "9:00 AM - 12:00 PM",
                        "activity": morning_attraction.get('name', 'Explore city center'),
                        "location": morning_attraction.get('formatted_address', 'City center'),
                        "rating": morning_attraction.get('rating', 'N/A')
                    },
                    "lunch": {
                        "time": "12:30 PM - 2:00 PM",
                        "restaurant": lunch_restaurant.get('name', 'Local restaurant'),
                        "address": lunch_restaurant.get('formatted_address', 'Downtown'),
                        "rating": lunch_restaurant.get('rating', 'N/A')
                    },
                    "afternoon": {
                        "time": "2:30 PM - 6:00 PM",
                        "activity": afternoon_attraction.get('name', 'Free time / Shopping'),
                        "location": afternoon_attraction.get('formatted_address', 'Downtown area'),
                        "rating": afternoon_attraction.get('rating', 'N/A')
                    },
                    "dinner": {
                        "time": "7:00 PM - 9:00 PM",
                        "restaurant": dinner_restaurant.get('name', 'Dinner spot'),
                        "address": dinner_restaurant.get('formatted_address', 'City center'),
                        "rating": dinner_restaurant.get('rating', 'N/A')
                    }
                }
                itinerary.append(day_plan)
            
            self.current_itinerary = itinerary
            self.log(f"✅ Created {len(itinerary)}-day itinerary")
            
            return {
                "success": True,
                "itinerary_created": True,
                "num_days": num_days,
                "message": f"Generated {num_days}-day itinerary"
            }
            
        except Exception as e:
            self.log(f"❌ Error generating itinerary: {str(e)}", "ERROR")
            return {
                "success": False,
                "message": str(e)
            }
    
    def _tool_refine_itinerary(self, params: RefineItinerary) -> Dict[str, Any]:
        """Refine existing itinerary based on feedback"""
        self.log(f"🔧 Refining itinerary: {params.refinement_request}")
        
        if not self.current_itinerary:
            return {"success": False, "message": "No itinerary to refine"}
        
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
    # FORMAT ITINERARY AS BEAUTIFUL TEXT
    # =========================================================================
    
    def _format_itinerary_as_text(self) -> str:
        """Format the itinerary as beautiful, readable text"""
        if not self.current_itinerary or not self.trip_data:
            return "No itinerary available."
        
        # Extract trip details
        destination = self.trip_data.get('destination', 'Unknown')
        departure_date = self.trip_data.get('departure_date', 'Unknown')
        return_date = self.trip_data.get('return_date', 'Unknown')
        trip_summary = self.trip_data.get('trip_summary', '')
        num_days = len(self.current_itinerary)
        
        # Format dates nicely
        try:
            departure_formatted = datetime.strptime(departure_date, '%Y-%m-%d').strftime('%B %d, %Y')
            return_formatted = datetime.strptime(return_date, '%Y-%m-%d').strftime('%B %d, %Y')
        except:
            departure_formatted = departure_date
            return_formatted = return_date
        
        # Build the formatted text
        output = []
        
        # Summary Section
        output.append("## 🎉 Your Adventure")
        output.append("")
        
        # User's Original Request
        if trip_summary and trip_summary.strip():
            output.append(f"**Your Trip:** {trip_summary}")
            output.append("")
        else:
            output.append(f"**Your Trip:** A {num_days}-day vacation to {destination}")
            output.append("")
        
        # Trip Details
        output.append(f"**📍 Destination:** ***{destination}***")
        output.append(f"**📅 Travel Dates:** {departure_formatted} to {return_formatted} ({num_days} days)")
        output.append("")
        
        # What's Included
        restaurants_count = len([r for r in self.trip_data.get('restaurants', []) if r])
        attractions_count = len([a for a in self.trip_data.get('attractions', []) if a])
        
        output.append("**✨ Your Itinerary Includes:**")
        output.append(f"• {num_days} full days of activities")
        output.append(f"• {restaurants_count} curated restaurants")
        output.append(f"• {attractions_count} top attractions")
        output.append(f"• Balanced daily schedule")
        output.append("")
        
        output.append("---")
        output.append("")
        
        # FLIGHT SECTION - NEW!
        final_flight = self.trip_data.get('final_flight', {})
        if final_flight:
            output.append("## ✈️ Your Flights")
            output.append("")
            
            # Flight summary
            outbound = final_flight.get('outbound', {})
            return_flight = final_flight.get('return', {})
            
            if outbound:
                output.append(f"**Outbound Flight:** {outbound.get('airline', '')} {outbound.get('flight', '')}")
                output.append(f"• **Route:** {outbound.get('from', '')} → {outbound.get('to', '')}")
                
                try:
                    dep_time = datetime.fromisoformat(outbound.get('departure', '').replace('Z', '+00:00'))
                    arr_time = datetime.fromisoformat(outbound.get('arrival', '').replace('Z', '+00:00'))
                    output.append(f"• **Departure:** {dep_time.strftime('%B %d, %Y at %I:%M %p')}")
                    output.append(f"• **Arrival:** {arr_time.strftime('%B %d, %Y at %I:%M %p')}")
                except:
                    output.append(f"• **Departure:** {outbound.get('departure', 'N/A')}")
                    output.append(f"• **Arrival:** {outbound.get('arrival', 'N/A')}")
                
                output.append(f"• **Duration:** {outbound.get('duration', 'N/A')}")
                stops = outbound.get('stops', 0)
                output.append(f"• **Stops:** {'Direct flight' if stops == 0 else f'{stops} stop(s)'}")
                output.append("")
            
            if return_flight:
                output.append(f"**Return Flight:** {return_flight.get('airline', '')} {return_flight.get('flight', '')}")
                output.append(f"• **Route:** {return_flight.get('from', '')} → {return_flight.get('to', '')}")
                
                try:
                    dep_time = datetime.fromisoformat(return_flight.get('departure', '').replace('Z', '+00:00'))
                    arr_time = datetime.fromisoformat(return_flight.get('arrival', '').replace('Z', '+00:00'))
                    output.append(f"• **Departure:** {dep_time.strftime('%B %d, %Y at %I:%M %p')}")
                    output.append(f"• **Arrival:** {arr_time.strftime('%B %d, %Y at %I:%M %p')}")
                except:
                    output.append(f"• **Departure:** {return_flight.get('departure', 'N/A')}")
                    output.append(f"• **Arrival:** {return_flight.get('arrival', 'N/A')}")
                
                output.append(f"• **Duration:** {return_flight.get('duration', 'N/A')}")
                stops = return_flight.get('stops', 0)
                output.append(f"• **Stops:** {'Direct flight' if stops == 0 else f'{stops} stop(s)'}")
                output.append("")
            
            # Price
            price = final_flight.get('price', 'N/A')
            currency = final_flight.get('currency', 'USD')
            output.append(f"**Total Price:** ${price} {currency}")
            output.append("")
            
            output.append("---")
            output.append("")
        
        # Day-by-day itinerary
        output.append("## 📅 Day-by-Day Itinerary")
        output.append("")
        
        for day in self.current_itinerary:
            day_num = day['day']
            date = day['date']
            
            try:
                date_formatted = datetime.strptime(date, '%Y-%m-%d').strftime('%A, %B %d')
            except:
                date_formatted = date
            
            output.append(f"### **Day {day_num}: {date_formatted}**")
            output.append("")
            
            # Morning
            morning = day['morning']
            output.append(f"**🌅 Morning ({morning['time']})**")
            output.append(f"• **Activity:** ***{morning['activity']}***")
            output.append(f"• **Location:** {morning['location']}")
            if morning.get('rating') and morning['rating'] != 'N/A':
                output.append(f"• **Rating:** ⭐ {morning['rating']}/5")
            output.append("")
            
            # Lunch
            lunch = day['lunch']
            output.append(f"**🍽️ Lunch ({lunch['time']})**")
            output.append(f"• **Restaurant:** ***{lunch['restaurant']}***")
            output.append(f"• **Address:** {lunch['address']}")
            if lunch.get('rating') and lunch['rating'] != 'N/A':
                output.append(f"• **Rating:** ⭐ {lunch['rating']}/5")
            output.append("")
            
            # Afternoon
            afternoon = day['afternoon']
            output.append(f"**☀️ Afternoon ({afternoon['time']})**")
            output.append(f"• **Activity:** ***{afternoon['activity']}***")
            output.append(f"• **Location:** {afternoon['location']}")
            if afternoon.get('rating') and afternoon['rating'] != 'N/A':
                output.append(f"• **Rating:** ⭐ {afternoon['rating']}/5")
            output.append("")
            
            # Dinner
            dinner = day['dinner']
            output.append(f"**🌙 Dinner ({dinner['time']})**")
            output.append(f"• **Restaurant:** ***{dinner['restaurant']}***")
            output.append(f"• **Address:** {dinner['address']}")
            if dinner.get('rating') and dinner['rating'] != 'N/A':
                output.append(f"• **Rating:** ⭐ {dinner['rating']}/5")
            output.append("")
            
            output.append("---")
            output.append("")
        
        # Hotel section
        output.append("## 🏨 Your Accommodation")
        output.append("")
        final_hotel = self.trip_data.get('final_hotel', {})
        if final_hotel and final_hotel.get('name'):
            output.append(f"**Hotel:** ***{final_hotel.get('name')}***")
            
            # Get address - might be in different fields
            address = final_hotel.get('address') or final_hotel.get('formatted_address') or 'Address available at booking'
            output.append(f"**Address:** {address}")
            
            if final_hotel.get('rating'):
                output.append(f"**Rating:** ⭐ {final_hotel.get('rating')}/5")
            
            if final_hotel.get('price'):
                output.append(f"**Rate:** ${final_hotel.get('price')}/night")
            
            if final_hotel.get('room_type'):
                output.append(f"**Room:** {final_hotel.get('room_type')}")
        else:
            output.append("**[Hotel details from your selection]**")
        output.append("")
        
        result = "\n".join(output)
        self.log(f"✅ Generated formatted text: {len(result)} characters")
        return result

    # =========================================================================
    # HIL AND FINAL RESPONSE FORMATTING
    # =========================================================================
    
    def _format_itinerary_for_pause(self) -> Dict[str, Any]:
        """Format response to pause for human approval"""
        destination = self.trip_data.get('destination', 'Unknown') if self.trip_data else 'Unknown'
        
        # Generate beautiful formatted text
        formatted_itinerary = self._format_itinerary_as_text()
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": HIL_PAUSE_REQUIRED,
            "itinerary": self.current_itinerary,
            "formatted_itinerary": formatted_itinerary,
            "destination": destination,
            "num_days": len(self.current_itinerary) if self.current_itinerary else 0,
            "message": "Itinerary generated successfully"
        }

    def _format_final_response(self) -> Dict[str, Any]:
        """Format final approved itinerary"""
        formatted_itinerary = self._format_itinerary_as_text()
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": SUCCESS,
            "itinerary": self.current_itinerary,
            "formatted_itinerary": formatted_itinerary,
            "message": "Itinerary approved and finalized."
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _convert_proto_to_dict(self, proto_map: Any) -> Dict[str, Any]:
        """Convert protobuf map to dict"""
        return dict(proto_map)

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize schema by removing unsupported fields"""
        sanitized = prop_schema.copy()
        
        for field in ['default', 'title', 'examples', 'additionalProperties']:
            if field in sanitized:
                del sanitized[field]
        
        if 'anyOf' in sanitized:
            for item in sanitized['anyOf']:
                if 'type' in item and item['type'] != 'null':
                    sanitized.update(item)
                    break
            del sanitized['anyOf']
        
        if 'type' in sanitized and isinstance(sanitized['type'], str):
            sanitized['type'] = sanitized['type'].upper()
        
        if sanitized.get('type') == 'ARRAY' and 'items' in sanitized:
            sanitized['items'] = self._sanitize_property_schema(sanitized['items'])
        
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
    
    def _create_tool_response(self, function_call: Any, result: Dict[str, Any]) -> Any:
        """Create function response for Gemini"""
        return glm.Part(function_response=glm.FunctionResponse(name=function_call.name, response={'result': result}))