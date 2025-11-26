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
# AGENTIC TOOL SCHEMAS - LLM makes ALL decisions
# =============================================================================

class AnalyzeAvailableOptions(BaseModel):
    """Analyze all available restaurants and attractions before planning."""
    analysis_notes: str = Field(..., description="Your strategic notes about the available options")

class SelectForTimeSlot(BaseModel):
    """Select a specific restaurant or attraction for a time slot with reasoning."""
    day_number: int = Field(..., description="Which day (1-5)")
    time_slot: str = Field(..., description="Which slot: 'morning', 'lunch', 'afternoon', or 'dinner'")
    selected_item_id: str = Field(..., description="ID/name of the selected restaurant or attraction")
    reasoning: str = Field(..., description="Why you selected this item for this slot")

class ReviewItinerary(BaseModel):
    """Review the current itinerary for quality, variety, and issues."""
    review_notes: str = Field(..., description="Your assessment of the itinerary quality")
    has_issues: bool = Field(..., description="Are there problems like repeats or poor distribution?")
    improvement_suggestions: Optional[str] = Field(None, description="What to fix if there are issues")

class FinalizeItinerary(BaseModel):
    """Signal that the itinerary is complete and ready for user."""
    final_summary: str = Field(..., description="Brief summary of the final itinerary")
    total_days: int = Field(..., description="Number of days planned")

# =============================================================================
# TRULY AGENTIC ITINERARY AGENT
# =============================================================================

class ItineraryAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str):
        super().__init__("ItineraryAgent", gemini_api_key)
        self.current_itinerary = []
        self.trip_data = None
        self.available_restaurants = []
        self.available_attractions = []
        self.used_items = set()  # Track what LLM has already selected
        
        self.tool_functions = {
            "AnalyzeAvailableOptions": self._tool_analyze_options,
            "SelectForTimeSlot": self._tool_select_for_slot,
            "ReviewItinerary": self._tool_review_itinerary,
            "FinalizeItinerary": self._tool_finalize_itinerary
        }
        
        self.tool_schemas = {
            "AnalyzeAvailableOptions": AnalyzeAvailableOptions,
            "SelectForTimeSlot": SelectForTimeSlot,
            "ReviewItinerary": ReviewItinerary,
            "FinalizeItinerary": FinalizeItinerary
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
        self.log("✅ Truly Agentic ItineraryAgent initialized")

    # =========================================================================
    # SYSTEM INSTRUCTION - Forces agentic workflow
    # =========================================================================
    
    def _build_system_instruction(self) -> str:
        """Build the system instruction for the agent."""
        return """You are an expert Itinerary Planning Agent. You build INTELLIGENT vacation itineraries.

YOUR WORKFLOW (FOLLOW THIS EXACTLY):

1. Call AnalyzeAvailableOptions first
   - Study all restaurants and attractions
   - Note ratings, locations, types
   - Plan your distribution strategy

2. Build the itinerary day-by-day using SelectForTimeSlot
   - For each day, for each time slot (morning/lunch/afternoon/dinner)
   - Choose items strategically considering:
     * Variety (don't repeat items on adjacent days)
     * Quality (prioritize higher-rated options)
     * Proximity (items near each other on same day)
     * Logic (museums in morning, restaurants at meal times)
   - ALWAYS provide clear reasoning for each selection

3. Call ReviewItinerary when complete
   - Check for repeats
   - Verify good distribution
   - Ensure quality

4. If issues found, use SelectForTimeSlot to fix them

5. Call FinalizeItinerary when satisfied

CRITICAL RULES:
- YOU choose which specific items go in which slots
- Avoid repeating restaurants/attractions on consecutive days
- Use higher-rated options when possible
- Think strategically about geography and timing
- NEVER just assign items randomly

You are making INTELLIGENT decisions, not following a script."""

    # =========================================================================
    # AGENTIC EXECUTION - LLM drives the process
    # =========================================================================

    def execute(self, params: Any, continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 30) -> Dict[str, Any]:
        """
        Execute with TRUE agenticness - LLM makes all decisions
        """
        try:
            # Handle both dict and Pydantic model inputs
            if hasattr(params, 'model_dump'):
                params_dict = params.model_dump()
            elif hasattr(params, 'dict'):
                params_dict = params.dict()
            else:
                params_dict = params
            
            # Store trip data
            self.trip_data = params_dict
            
            # Extract key info
            departure_date = params_dict.get('departure_date', 'unknown')
            return_date = params_dict.get('return_date', 'unknown')
            destination = params_dict.get('destination', 'unknown')
            
            # Get available options
            self.available_restaurants = params_dict.get('restaurants', [])[:15]
            self.available_attractions = params_dict.get('attractions', [])[:15]
            
            self.log(f"▶️ Starting AGENTIC itinerary generation for {destination}")
            self.log(f"📊 Available: {len(self.available_restaurants)} restaurants, {len(self.available_attractions)} attractions")
            
            # Calculate trip details
            try:
                start = datetime.strptime(departure_date, '%Y-%m-%d')
                end = datetime.strptime(return_date, '%Y-%m-%d')
                num_days = (end - start).days
            except:
                num_days = 5
            
            # Initialize empty itinerary structure
            self.current_itinerary = []
            for day_num in range(num_days):
                current_date = (start + timedelta(days=day_num)).strftime('%Y-%m-%d')
                self.current_itinerary.append({
                    "day": day_num + 1,
                    "date": current_date,
                    "morning": {},
                    "lunch": {},
                    "afternoon": {},
                    "dinner": {}
                })
            
            self.used_items = set()
            
            # Build initial prompt with all context
            initial_prompt = f"""You are building a {num_days}-day itinerary for {destination}.

AVAILABLE RESTAURANTS ({len(self.available_restaurants)}):
{self._format_restaurants_list()}

AVAILABLE ATTRACTIONS ({len(self.available_attractions)}):
{self._format_attractions_list()}

YOUR TASK:
Build a {num_days}-day itinerary with intelligent selections.

Each day needs:
- Morning: attraction
- Lunch: restaurant
- Afternoon: attraction
- Dinner: restaurant

Start by calling AnalyzeAvailableOptions to study what's available."""

            # Start LLM conversation
            chat = self.model.start_chat()
            response = chat.send_message(initial_prompt)
            
            # Run agentic loop
            for turn in range(max_turns):
                self.log(f"🔄 Turn {turn + 1}/{max_turns}")
                
                # Extract tool calls
                current_function_calls = []
                if response.candidates and response.candidates[0].content:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            current_function_calls.append(part.function_call)
                
                if not current_function_calls:
                    self.log(f"⚠️ Turn {turn + 1}: LLM stopped without calling tools", "WARN")
                    break
                
                # Execute tools
                tool_results = []
                finalized = False
                
                for func_call in current_function_calls:
                    tool_name = func_call.name
                    tool_args = self._convert_proto_to_dict(func_call.args)
                    
                    self.log(f"🛠️ LLM called tool: {tool_name}")
                    
                    try:
                        result = self._execute_tool(tool_name, tool_args)
                        tool_results.append(self._create_tool_response(func_call, result))
                        
                        if tool_name == 'FinalizeItinerary':
                            finalized = True
                            self.log("✅ LLM finalized the itinerary")
                            
                    except Exception as e:
                        self.log(f"❌ Tool execution failed: {e}", "ERROR")
                        error_result = {"success": False, "error": str(e)}
                        tool_results.append(self._create_tool_response(func_call, error_result))
                
                if finalized:
                    return self._format_itinerary_for_pause()
                
                # Send tool results back to LLM
                tool_response_content = glm.Content(
                    role="function",
                    parts=tool_results
                )
                response = chat.send_message(tool_response_content)
            
            # If we hit max turns, check if itinerary is complete enough
            if self._is_itinerary_complete():
                self.log("✅ Itinerary completed (max turns reached)")
                return self._format_itinerary_for_pause()
            
            return {
                "success": False,
                "agent": self.name,
                "status_code": "STATUS_INCOMPLETE",
                "message": "Failed to complete itinerary within iteration limit"
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
    # AGENTIC TOOL IMPLEMENTATIONS - Pure LLM decision making
    # =========================================================================

    def _tool_analyze_options(self, params: AnalyzeAvailableOptions) -> Dict[str, Any]:
        """LLM analyzes available options"""
        self.log(f"🧠 LLM Analysis: {params.analysis_notes[:100]}...")
        
        return {
            "success": True,
            "message": "Analysis recorded. Now use SelectForTimeSlot to build the itinerary.",
            "reminder": f"You have {len(self.available_restaurants)} restaurants and {len(self.available_attractions)} attractions to work with."
        }
    
    def _tool_select_for_slot(self, params: SelectForTimeSlot) -> Dict[str, Any]:
        """LLM selects specific item for specific slot"""
        day_idx = params.day_number - 1
        slot = params.time_slot
        item_id = params.selected_item_id
        
        self.log(f"✏️ Day {params.day_number} {slot}: {item_id}")
        self.log(f"   Reasoning: {params.reasoning[:80]}...")
        
        # Find the actual item
        if slot in ['lunch', 'dinner']:
            item = self._find_restaurant(item_id)
            if not item:
                return {
                    "success": False,
                    "error": f"Restaurant '{item_id}' not found in available options"
                }
            
            self.current_itinerary[day_idx][slot] = {
                "time": "12:30 PM - 2:00 PM" if slot == 'lunch' else "7:00 PM - 9:00 PM",
                "restaurant": item.get('name'),
                "address": item.get('formatted_address', 'Address TBD'),
                "rating": item.get('rating', 'N/A')
            }
        else:  # morning or afternoon
            item = self._find_attraction(item_id)
            if not item:
                return {
                    "success": False,
                    "error": f"Attraction '{item_id}' not found in available options"
                }
            
            self.current_itinerary[day_idx][slot] = {
                "time": "9:00 AM - 12:00 PM" if slot == 'morning' else "2:30 PM - 6:00 PM",
                "activity": item.get('name'),
                "location": item.get('formatted_address', 'Location TBD'),
                "rating": item.get('rating', 'N/A')
            }
        
        self.used_items.add(item_id)
        
        # Check completion
        is_complete = self._is_itinerary_complete()
        
        return {
            "success": True,
            "message": f"✅ Selected for Day {params.day_number} {slot}",
            "items_used": len(self.used_items),
            "itinerary_complete": is_complete,
            "next_step": "Call FinalizeItinerary when all slots filled" if is_complete else "Continue selecting for remaining slots"
        }
    
    def _tool_review_itinerary(self, params: ReviewItinerary) -> Dict[str, Any]:
        """LLM reviews the itinerary quality"""
        self.log(f"🔍 LLM Review: {params.review_notes[:100]}...")
        
        if params.has_issues:
            self.log(f"⚠️ Issues found: {params.improvement_suggestions}")
            return {
                "success": True,
                "has_issues": True,
                "message": "Issues detected. Use SelectForTimeSlot to make corrections.",
                "suggestions": params.improvement_suggestions
            }
        
        return {
            "success": True,
            "has_issues": False,
            "message": "Itinerary looks good! Call FinalizeItinerary to complete."
        }
    
    def _tool_finalize_itinerary(self, params: FinalizeItinerary) -> Dict[str, Any]:
        """LLM signals completion"""
        self.log(f"⭐ Finalized: {params.final_summary}")
        
        return {
            "success": True,
            "message": "Itinerary finalized and ready for user",
            "total_days": params.total_days
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _format_restaurants_list(self) -> str:
        """Format restaurant list for LLM"""
        lines = []
        for i, r in enumerate(self.available_restaurants, 1):
            lines.append(f"{i}. {r.get('name')} (★{r.get('rating', 'N/A')}) - {r.get('formatted_address', 'Address N/A')}")
        return "\n".join(lines)
    
    def _format_attractions_list(self) -> str:
        """Format attraction list for LLM"""
        lines = []
        for i, a in enumerate(self.available_attractions, 1):
            lines.append(f"{i}. {a.get('name')} (★{a.get('rating', 'N/A')}) - {a.get('formatted_address', 'Location N/A')}")
        return "\n".join(lines)
    
    def _find_restaurant(self, item_id: str) -> Optional[Dict]:
        """Find restaurant by name or ID"""
        for r in self.available_restaurants:
            if item_id.lower() in r.get('name', '').lower():
                return r
        return None
    
    def _find_attraction(self, item_id: str) -> Optional[Dict]:
        """Find attraction by name or ID"""
        for a in self.available_attractions:
            if item_id.lower() in a.get('name', '').lower():
                return a
        return None
    
    def _is_itinerary_complete(self) -> bool:
        """Check if all slots are filled"""
        for day in self.current_itinerary:
            for slot in ['morning', 'lunch', 'afternoon', 'dinner']:
                if not day.get(slot):
                    return False
                # Check if slot has actual data
                slot_data = day[slot]
                if slot in ['lunch', 'dinner']:
                    if not slot_data.get('restaurant'):
                        return False
                else:
                    if not slot_data.get('activity'):
                        return False
        return True

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool with validation"""
        schema = self.tool_schemas.get(tool_name)
        func = self.tool_functions.get(tool_name)
        if not schema or not func:
            raise ValueError(f"Unknown tool: {tool_name}")
        validated_args = schema(**tool_args)
        return func(validated_args)

    # =========================================================================
    # FORMAT ITINERARY AS BEAUTIFUL TEXT (same as before)
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
        
        if trip_summary and trip_summary.strip():
            output.append(f"**Your Trip:** {trip_summary}")
            output.append("")
        else:
            output.append(f"**Your Trip:** A {num_days}-day vacation to {destination}")
            output.append("")
        
        output.append(f"**📍 Destination:** ***{destination}***")
        output.append(f"**📅 Travel Dates:** {departure_formatted} to {return_formatted} ({num_days} days)")
        output.append("")
        
        restaurants_count = len([r for r in self.trip_data.get('restaurants', []) if r])
        attractions_count = len([a for a in self.trip_data.get('attractions', []) if a])
        
        output.append("**✨ Your Itinerary Includes:**")
        output.append(f"• {num_days} full days of activities")
        output.append(f"• {restaurants_count} curated restaurants")
        output.append(f"• {attractions_count} top attractions")
        output.append(f"• Intelligently planned by AI for optimal experience")
        output.append("")
        
        output.append("---")
        output.append("")
        
        # FLIGHT SECTION
        final_flight = self.trip_data.get('final_flight', {})
        if final_flight:
            output.append("## ✈️ Your Flights")
            output.append("")
            
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
            morning = day.get('morning', {})
            if morning.get('activity'):
                output.append(f"**🌅 Morning ({morning.get('time', '9:00 AM - 12:00 PM')})**")
                output.append(f"• **Activity:** ***{morning['activity']}***")
                output.append(f"• **Location:** {morning.get('location', 'N/A')}")
                if morning.get('rating') and morning['rating'] != 'N/A':
                    output.append(f"• **Rating:** ⭐ {morning['rating']}/5")
                output.append("")
            
            # Lunch
            lunch = day.get('lunch', {})
            if lunch.get('restaurant'):
                output.append(f"**🍽️ Lunch ({lunch.get('time', '12:30 PM - 2:00 PM')})**")
                output.append(f"• **Restaurant:** ***{lunch['restaurant']}***")
                output.append(f"• **Address:** {lunch.get('address', 'N/A')}")
                if lunch.get('rating') and lunch['rating'] != 'N/A':
                    output.append(f"• **Rating:** ⭐ {lunch['rating']}/5")
                output.append("")
            
            # Afternoon
            afternoon = day.get('afternoon', {})
            if afternoon.get('activity'):
                output.append(f"**☀️ Afternoon ({afternoon.get('time', '2:30 PM - 6:00 PM')})**")
                output.append(f"• **Activity:** ***{afternoon['activity']}***")
                output.append(f"• **Location:** {afternoon.get('location', 'N/A')}")
                if afternoon.get('rating') and afternoon['rating'] != 'N/A':
                    output.append(f"• **Rating:** ⭐ {afternoon['rating']}/5")
                output.append("")
            
            # Dinner
            dinner = day.get('dinner', {})
            if dinner.get('restaurant'):
                output.append(f"**🌙 Dinner ({dinner.get('time', '7:00 PM - 9:00 PM')})**")
                output.append(f"• **Restaurant:** ***{dinner['restaurant']}***")
                output.append(f"• **Address:** {dinner.get('address', 'N/A')}")
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
        
        formatted_itinerary = self._format_itinerary_as_text()
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": HIL_PAUSE_REQUIRED,
            "itinerary": self.current_itinerary,
            "formatted_itinerary": formatted_itinerary,
            "destination": destination,
            "num_days": len(self.current_itinerary) if self.current_itinerary else 0,
            "message": "Agentic itinerary generated successfully"
        }

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _convert_proto_to_dict(self, proto_map: Any) -> Dict[str, Any]:
        return dict(proto_map)

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
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
        tool_list = [AnalyzeAvailableOptions, SelectForTimeSlot, ReviewItinerary, FinalizeItinerary]
        tools = []
        for model in tool_list:
            tools.append(genai_types.Tool(function_declarations=[self._pydantic_to_function_declaration(model)]))
        return tools
    
    def _create_tool_response(self, function_call: Any, result: Dict[str, Any]) -> Any:
        return glm.Part(function_response=glm.FunctionResponse(name=function_call.name, response={'result': result}))