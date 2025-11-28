"""
OrchestratorAgent - TWO-PHASE HIL + INTELLIGENT CLARIFICATION
==============================================================
FIXED: Maintains conversation history across clarification rounds to prevent repeated questions.

This agent coordinates all specialist agents in a two-phase workflow:
- Phase 1 (HIL): FlightAgent → HotelAgent (with human selection)
- Phase 2 (Auto): RestaurantAgent → AttractionsAgent → ItineraryAgent

CRITICAL FIX:
- Added self.conversation_history to persist LLM conversation across clarification rounds
- LLM now remembers all previous user responses and won't ask the same questions
"""

import os
import sys
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import google.generativeai as genai
import google.generativeai.types as genai_types
import google.ai.generativelanguage as glm

# Import base agent
from .base_agent import BaseAgent

# --- HIL Status Codes (defined inline) ---
HIL_PAUSE_REQUIRED = "HIL_PAUSE_REQUIRED"
SUCCESS = "SUCCESS"
FINAL_CHOICE = "FINAL_CHOICE"
REFINE_SEARCH = "REFINE_SEARCH"

# =============================================================================
# PYDANTIC SCHEMAS FOR ORCHESTRATOR TOOLS
# =============================================================================

class RequestClarification(BaseModel):
    """
    STEP 3: Request clarification from user when critical information is missing.
    Use this tool ONLY when you genuinely cannot proceed without essential details.
    """
    questions: List[str] = Field(..., description="List of specific questions to ask the user. Each question should be clear and request ONE piece of information.")
    reasoning: str = Field(..., description="Brief explanation of why this information is needed to proceed with planning.")
    missing_required: List[str] = Field(default_factory=list, description="List of REQUIRED fields that are missing (e.g., 'origin', 'destination', 'departure_date').")
    missing_optional: List[str] = Field(default_factory=list, description="List of OPTIONAL preferences that would improve planning (e.g., 'dietary_restrictions', 'hotel_amenities').")

class FlightSearch(BaseModel):
    origin: str = Field(..., description="Departure city/airport code")
    destination: str = Field(..., description="Arrival city/airport code")
    departure_date: str = Field(..., description="Departure date (YYYY-MM-DD)")
    return_date: str = Field(..., description="Return date (YYYY-MM-DD)")
    passengers: int = Field(2, description="Number of passengers")
    max_stops: int = Field(2, description="Maximum number of stops")
    preferred_airline: Optional[str] = Field(None, description="Preferred airline if specified")

class HotelSearch(BaseModel):
    city: str = Field(..., description="Destination city for hotel search")
    check_in_date: str = Field(..., description="Check-in date (YYYY-MM-DD)")
    check_out_date: str = Field(..., description="Check-out date (YYYY-MM-DD)")
    adults: int = Field(2, description="Number of adults")
    budget_per_night: Optional[int] = Field(None, description="Maximum price per night in USD")
    amenities: Optional[List[str]] = Field(None, description="Desired amenities (e.g., 'pool', 'gym', 'city center')")

class RestaurantSearch(BaseModel):
    city: str = Field(..., description="City for restaurant search")
    dietary_restrictions: Optional[List[str]] = Field(None, description="Dietary restrictions (e.g., 'vegetarian', 'gluten-free')")
    cuisine_preference: Optional[str] = Field(None, description="Preferred cuisine type")
    proximity_location: Optional[str] = Field(None, description="Hotel name/address for proximity-based search")

class AttractionsSearch(BaseModel):
    city: str = Field(..., description="City for attractions search")
    interests: Optional[List[str]] = Field(None, description="User interests (e.g., 'museums', 'outdoor', 'nightlife')")
    accessibility_needs: Optional[List[str]] = Field(None, description="Accessibility requirements")
    proximity_location: Optional[str] = Field(None, description="Hotel name/address for proximity-based search")

class GenerateItinerary(BaseModel):
    origin: str = Field(..., description="Departure city")
    destination: str = Field(..., description="Arrival city")
    departure_date: str = Field(..., description="Trip start date")
    return_date: str = Field(..., description="Trip end date")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="User preferences and constraints")
    trip_summary: str = Field(..., description="Summary of finalized trip parameters.")

# =============================================================================
# TWO-PHASE ORCHESTRATOR AGENT
# =============================================================================

class OrchestratorAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str, flight_agent, hotel_agent, restaurant_agent, attractions_agent, itinerary_agent):
        """Initialize OrchestratorAgent with two-phase HIL and intelligent clarification."""
        super().__init__("OrchestratorAgent", gemini_api_key)
        
        # Store specialist agents
        self.flight_agent = flight_agent
        self.hotel_agent = hotel_agent
        self.restaurant_agent = restaurant_agent
        self.attractions_agent = attractions_agent
        self.itinerary_agent = itinerary_agent
        
        # Tool execution mapping - STEP 3: Added RequestClarification
        self.specialist_tools = {
            "RequestClarification": self._tool_request_clarification,  # STEP 3: NEW
            "FlightSearch": self._tool_flight_search,
            "HotelSearch": self._tool_hotel_search,
            "RestaurantSearch": self._tool_restaurant_search,
            "AttractionsSearch": self._tool_attractions_search,
            "GenerateItinerary": itinerary_agent.execute,
        }

        # Pydantic schema mapping - STEP 3: Added RequestClarification
        self.tool_schemas = {
            "RequestClarification": RequestClarification,  # STEP 3: NEW
            "FlightSearch": FlightSearch,
            "HotelSearch": HotelSearch,
            "RestaurantSearch": RestaurantSearch,
            "AttractionsSearch": AttractionsSearch,
            "GenerateItinerary": GenerateItinerary
        }

        # Storage for all results
        self.all_results = {}
        
        # CRITICAL FIX: Add conversation history to persist across clarification rounds
        self.conversation_history = []
        
        # Build system instruction and tools
        self.system_instruction = self._build_system_instruction()
        self.gemini_tools = self._create_gemini_tools()

        genai.configure(api_key=gemini_api_key)

        # Initialize Gemini model
        self.model = genai.GenerativeModel(
            'gemini-2.0-flash-exp',
            tools=self.gemini_tools,
            system_instruction=self.system_instruction,
            generation_config={'temperature': 0.7}
        )
        self.log("✅ OrchestratorAgent initialized with TWO-PHASE HIL + CLARIFICATION")

    # =========================================================================
    # STEP 3: CLARIFICATION HANDLING
    # =========================================================================

    def _tool_request_clarification(self, params: RequestClarification) -> Dict[str, Any]:
        """
        Handle clarification request from LLM.
        This doesn't execute - it returns a special status for main.py to handle.
        """
        self.log(f"⏸️  LLM requests clarification: {len(params.questions)} questions")
        self.log(f"   Reasoning: {params.reasoning}")
        
        return {
            "status": "clarification_needed",
            "questions": params.questions,
            "reasoning": params.reasoning,
            "missing_required": params.missing_required,
            "missing_optional": params.missing_optional
        }

    # =========================================================================
    # PHASE 1 TOOLS (HIL for Flight and Hotel)
    # =========================================================================

    def _tool_flight_search(self, params: FlightSearch) -> Dict[str, Any]:
        """Triggers FlightAgent (Phase 1)."""
        result = self._execute_phase1_agent(
            self.flight_agent,
            params.model_dump(),
            "FlightAgent",
            "flight"
        )
        
        if result.get('status') == 'awaiting_user_input':
            return result
        elif result.get('status') == 'success':
            self.all_results['final_flight'] = result['result'].get('final_flight')
            return {"success": True, "message": "Flight secured"}
        else:
            return {"success": False, "error": "Flight search failed"}

    def _tool_hotel_search(self, params: HotelSearch) -> Dict[str, Any]:
        """Triggers HotelAgent (Phase 1)."""
        result = self._execute_phase1_agent(
            self.hotel_agent,
            params.model_dump(),
            "HotelAgent",
            "hotel"
        )
        
        if result.get('status') == 'awaiting_user_input':
            return result
        elif result.get('status') == 'success':
            self.all_results['final_hotel'] = result['result'].get('final_hotel')
            return {"success": True, "message": "Hotel secured"}
        else:
            return {"success": False, "error": "Hotel search failed"}

    def _tool_restaurant_search(self, params: RestaurantSearch) -> Dict[str, Any]:
        """Phase 2 only - called automatically."""
        return {"success": True, "message": "Restaurant will be auto-selected in Phase 2"}

    def _tool_attractions_search(self, params: AttractionsSearch) -> Dict[str, Any]:
        """Phase 2 only - called automatically."""
        return {"success": True, "message": "Attractions will be auto-selected in Phase 2"}

    # =========================================================================
    # PUBLIC ENTRY POINTS
    # =========================================================================

    def execute(self, user_prompt: str, clarification_response: Optional[str] = None, max_turns: int = 10) -> Dict[str, Any]:
        """
        STEP 3: Main entry point with intelligent clarification support.
        
        CRITICAL FIX: Uses persistent conversation history instead of creating new chat sessions.
        This prevents the LLM from forgetting previous clarification responses.
        
        Args:
            user_prompt: Initial user vacation request
            clarification_response: User's answers to clarification questions (if any)
            max_turns: Max LLM conversation turns
            
        Returns:
            - If clarification needed: {"status": "clarification_needed", "questions": [...]}
            - If ready for Phase 1: {"status": "awaiting_user_input", "agent": "FlightAgent", ...}
            - If error: {"success": False, "error": "..."}
        """
        
        # CRITICAL FIX: Build full prompt with accumulated context
        if clarification_response:
            # Append clarification to conversation history
            full_prompt = f"""ORIGINAL REQUEST: {user_prompt}

ADDITIONAL INFORMATION PROVIDED BY USER: {clarification_response}

Now proceed with planning using ALL the information above. Do NOT ask questions that have already been answered."""
            self.log("📥 Processing clarification response...")
        else:
            # First time - initialize conversation history
            full_prompt = user_prompt
            self.conversation_history = []  # Reset history for new trip
        
        self.log(f"Starting TWO-PHASE orchestration: {full_prompt[:100]}...")
        
        # CRITICAL FIX: Use persistent chat or create new one only if empty
        if not self.conversation_history:
            # First interaction - start new chat
            chat = self.model.start_chat()
        else:
            # Continuing conversation - use existing history
            chat = self.model.start_chat(history=self.conversation_history)
        
        # Send message to LLM
        response = chat.send_message(full_prompt)
        
        # CRITICAL FIX: Update conversation history with user message and LLM response
        self.conversation_history.append({
            'role': 'user',
            'parts': [{'text': full_prompt}]
        })
        
        # Add LLM response to history
        if response.candidates and response.candidates[0].content:
            self.conversation_history.append({
                'role': 'model',
                'parts': [self._serialize_part(part) for part in response.candidates[0].content.parts]
            })
        
        # Extract function calls
        current_function_calls = []
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    current_function_calls.append(part.function_call)
        
        # DEBUG: Log what we got back
        if not current_function_calls:
            self.log(f"❌ LLM returned NO function calls. Response: {response.text if hasattr(response, 'text') else 'No text'}", "ERROR")
            return {"success": False, "error": "Could not parse trip request - LLM did not call any tools"}
        
        self.log(f"✅ LLM called tool: {current_function_calls[0].name}")
        
        # Execute first tool
        func_call = current_function_calls[0]
        tool_name = func_call.name
        tool_args = self._convert_proto_to_dict(func_call.args)
        
        # STEP 3: Check if LLM is requesting clarification
        if tool_name == "RequestClarification":
            self.log("⏸️  LLM requests clarification from user")
            return self._tool_request_clarification(RequestClarification(**tool_args))
        
        # Otherwise proceed with Phase 1
        self.log(f"🎯 Phase 1: Starting with {tool_name}")
        
        # Store trip details for Phase 2
        self.trip_details = tool_args.copy()
        self.trip_details['user_prompt'] = user_prompt
        
        try:
            result = self._execute_orchestrator_tool(tool_name, tool_args)
            
            # Check if paused for HIL
            if result.get('status') == 'awaiting_user_input':
                return {
                    "status": "awaiting_user_input",
                    "session_id": None,
                    "agent": result.get('agent'),
                    "item_type": result.get('item_type'),
                    "recommendations": result.get('recommendations', []),
                    "summary": result.get('summary', ''),
                    "session_state": {
                        "result": result,
                        "trip_details": self.trip_details,
                        "current_phase": "FLIGHT",
                        "conversation_history": self.conversation_history  # CRITICAL: Preserve history
                    }
                }
            
            return {"success": False, "error": "Unexpected result from FlightAgent"}
            
        except Exception as e:
            self.log(f"❌ Orchestration error: {str(e)}", "ERROR")
            return {"success": False, "error": str(e)}

    def resume(self, session_state: Dict[str, Any], user_decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resume orchestration after user makes a choice.
        
        CRITICAL FIX: Restores conversation history from session state.
        """
        self.log("▶️  Resuming TWO-PHASE orchestration...")
        
        current_phase = session_state.get('current_phase', 'FLIGHT')
        hil_result = session_state.get('result', {})
        trip_details = session_state.get('trip_details', {})
        
        # CRITICAL FIX: Restore conversation history
        self.conversation_history = session_state.get('conversation_history', [])
        
        agent_name = hil_result.get('agent')
        item_name = hil_result.get('item_type')
        
        # Get agent
        agent = self.flight_agent if agent_name == "FlightAgent" else self.hotel_agent
        
        # Resume the agent
        result = self._resume_phase1_agent(agent, hil_result, user_decision, agent_name, item_name)
        
        # Check if pausing again (refinement)
        if result.get('status') == 'awaiting_user_input':
            return {
                "status": "awaiting_user_input",
                "agent": result.get('agent'),
                "item_type": result.get('item_type'),
                "recommendations": result.get('recommendations', []),
                "summary": result.get('summary', ''),
                "session_state": {
                    "result": result,
                    "trip_details": trip_details,
                    "current_phase": current_phase,
                    "conversation_history": self.conversation_history  # CRITICAL: Keep history
                }
            }
        
        # Agent completed
        if result.get('status') == 'success':
            # Store result
            if agent_name == "FlightAgent":
                self.all_results['final_flight'] = result['result'].get('final_flight')
                self.log("✅ Flight secured! Moving to HotelAgent...")
                
                # Start HotelAgent
                hotel_params = {
                    'city': trip_details.get('destination'),
                    'check_in_date': trip_details.get('departure_date'),
                    'check_out_date': trip_details.get('return_date')
                }
                
                hotel_result = self._execute_phase1_agent(
                    self.hotel_agent,
                    hotel_params,
                    "HotelAgent",
                    "hotel"
                )
                
                if hotel_result.get('status') == 'awaiting_user_input':
                    return {
                        "status": "awaiting_user_input",
                        "agent": hotel_result.get('agent'),
                        "item_type": hotel_result.get('item_type'),
                        "recommendations": hotel_result.get('recommendations', []),
                        "summary": hotel_result.get('summary', ''),
                        "session_state": {
                            "result": hotel_result,
                            "trip_details": trip_details,
                            "current_phase": "HOTEL",
                            "conversation_history": self.conversation_history  # CRITICAL: Keep history
                        }
                    }
            
            elif agent_name == "HotelAgent":
                self.all_results['final_hotel'] = result['result'].get('final_hotel')
                self.log("✅ Hotel secured! Starting Phase 2...")
                
                # Execute Phase 2 (automatic)
                phase2_result = self._execute_phase2(trip_details)
                
                self.log(f"📊 Phase 2 result: {phase2_result.get('status')}")
                
                if phase2_result.get('status') == 'success':
                    formatted_itinerary = self.all_results.get('itinerary', {}).get('formatted_itinerary', '')
                    
                    self.log(f"📤 Sending formatted itinerary to frontend: {len(formatted_itinerary)} characters")
                    
                    if not formatted_itinerary:
                        self.log("⚠️  WARNING: Empty formatted itinerary!", "ERROR")
                        formatted_itinerary = "Error: Itinerary generation failed"
                    
                    return {
                        "status": "complete",
                        "success": True,
                        "data": formatted_itinerary,
                        "summary": "Complete vacation plan ready!",
                        "all_results": self.all_results
                    }
                else:
                    error_msg = phase2_result.get('error', 'Phase 2 failed')
                    self.log(f"❌ Phase 2 error: {error_msg}", "ERROR")
                    return {
                        "status": "error",
                        "success": False,
                        "error": error_msg
                    }
        
        return {"status": "error", "success": False, "error": "Resume failed - unexpected state"}

    def _execute_orchestrator_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute orchestrator tool with validation."""
        schema = self.tool_schemas.get(tool_name)
        func = self.specialist_tools.get(tool_name)
        if not schema or not func:
            raise ValueError(f"Unknown tool: {tool_name}")
        validated_args = schema(**tool_args)
        return func(validated_args)

    # =========================================================================
    # PHASE 1: HIL EXECUTION WRAPPER
    # =========================================================================

    def _execute_phase1_agent(self, agent, initial_params: Dict[str, Any], agent_name: str, item_name: str) -> Dict[str, Any]:
        """
        Execute Phase 1 agent with HIL support.
        Returns status for pausing or continuation.
        """
        self.log(f"🎯 Executing {agent_name} (Phase 1 - HIL enabled)...")
        
        # Execute agent once
        result = agent.execute(initial_params, continuation_message=None)
        
        # Check if HIL pause needed
        if result.get('status_code') == HIL_PAUSE_REQUIRED:
            self.log(f"⏸️  {agent_name} paused for user input")
            
            recommendations = result.get(f'recommended_{item_name}s', [])
            summary = result.get('summary', '')
            
            return {
                "status": "awaiting_user_input",
                "agent": agent_name,
                "item_type": item_name,
                "recommendations": recommendations,
                "summary": summary
            }
        
        # Check if successful
        if result.get('status_code') == SUCCESS:
            return {
                "status": "success",
                "result": result
            }
        
        return {
            "status": "error",
            "error": f"{agent_name} execution failed"
        }

    def _resume_phase1_agent(self, agent, hil_result: Dict[str, Any], user_decision: Dict[str, Any], agent_name: str, item_name: str) -> Dict[str, Any]:
        """Resume Phase 1 agent after user selection."""
        
        # Extract selected ID
        selected_id = user_decision.get('selected_id')
        feedback = user_decision.get('feedback', '')
        
        # Build continuation message as DICT with 'content' key (FlightAgent/HotelAgent expect this format)
        if selected_id:
            content = f"FINAL_CHOICE_TRIGGER: User selected {item_name} with ID: {selected_id}"
        else:
            content = f"User feedback: {feedback}"
        
        continuation_message = {'content': content}
        
        # Get original params from hil_result
        original_params = hil_result.get('original_params', {})
        
        # Resume agent with DICT continuation message
        result = agent.execute(original_params, continuation_message=continuation_message)
        
        # Check if pausing again
        if result.get('status_code') == HIL_PAUSE_REQUIRED:
            recommendations = result.get(f'recommended_{item_name}s', [])
            summary = result.get('summary', '')
            
            return {
                "status": "awaiting_user_input",
                "agent": agent_name,
                "item_type": item_name,
                "recommendations": recommendations,
                "summary": summary
            }
        
        # Success
        if result.get('status_code') == SUCCESS:
            return {
                "status": "success",
                "result": result
            }
        
        return {
            "status": "error",
            "error": f"{agent_name} resume failed"
        }

    # =========================================================================
    # PHASE 2: AUTOMATIC EXECUTION
    # =========================================================================

    def _execute_phase2(self, trip_details: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Phase 2: Automatic selection of restaurants, attractions, itinerary."""
        self.log("🚀 Starting Phase 2 (Automatic)...")
        
        # Get hotel location for proximity
        hotel_info = self.all_results.get('final_hotel', {})
        hotel_location = hotel_info.get('name', '') or trip_details.get('destination')
        
        # 1. RestaurantAgent (automatic)
        self.log("🍽️  Executing RestaurantAgent (automatic)...")
        restaurant_result = self.restaurant_agent.execute({
            'city': trip_details.get('destination'),
            'proximity_location': hotel_location,
            'min_rating': 4.0
        })
        
        # Store regardless of status
        self.all_results['final_restaurant'] = restaurant_result
        
        # 2. AttractionsAgent (automatic)
        self.log("🎭 Executing AttractionsAgent (automatic)...")
        attractions_result = self.attractions_agent.execute({
            'city': trip_details.get('destination'),
            'proximity_location': hotel_location,
            'min_rating': 4.0
        })
        
        # Store regardless of status
        self.all_results['final_attraction'] = attractions_result
        
        # 3. ItineraryAgent (automatic)
        self.log("📅 Executing ItineraryAgent (automatic)...")
        
        # CRITICAL FIX: Extract the actual lists from the results
        restaurants_list = restaurant_result.get('recommended_restaurants', [])
        attractions_list = attractions_result.get('recommended_attractions', [])
        
        self.log(f"📊 Passing to ItineraryAgent: {len(restaurants_list)} restaurants, {len(attractions_list)} attractions")
        
        itinerary_result = self.itinerary_agent.execute({
            'origin': trip_details.get('origin'),
            'destination': trip_details.get('destination'),
            'departure_date': trip_details.get('departure_date'),
            'return_date': trip_details.get('return_date'),
            'preferences': {},
            'trip_summary': f"Trip from {trip_details.get('origin')} to {trip_details.get('destination')}",
            'restaurants': restaurants_list,  # CRITICAL: Pass the actual list
            'attractions': attractions_list,   # CRITICAL: Pass the actual list
            'final_flight': self.all_results.get('final_flight', {}),  # CRITICAL: Pass flight details
            'final_hotel': self.all_results.get('final_hotel', {})     # CRITICAL: Pass hotel details
        })
        
        self.log(f"📊 ItineraryAgent returned status_code: {itinerary_result.get('status_code')}")
        
        # Store the itinerary result
        self.all_results['itinerary'] = itinerary_result
        
        # Check if itinerary was successfully generated
        if itinerary_result.get('status_code') == SUCCESS or itinerary_result.get('formatted_itinerary'):
            self.log("✅ Phase 2 completed successfully")
            return {"status": "success"}
        else:
            self.log(f"❌ ItineraryAgent failed with status: {itinerary_result.get('status_code')}", "ERROR")
            return {"status": "error", "error": "Itinerary generation failed"}

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _build_system_instruction(self) -> str:
        """STEP 3: System instruction with intelligent clarification guidance."""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        return f"""You are an intelligent vacation planning orchestrator with memory of past interactions.

CONTEXT:
- Current date: {current_date}
- All travel dates MUST be in the future
- You have conversation history - NEVER ask questions that were already answered

REQUIRED INFORMATION to start planning:
1. origin - Departure city/airport (where departing from)
2. destination - Arrival city/airport (where going to)
3. departure_date - Travel start date (YYYY-MM-DD format, MUST be future)
4. return_date - Travel end date (YYYY-MM-DD format, MUST be after departure)

YOUR WORKFLOW:

Step 1: Analyze the user's prompt carefully
Step 2: Extract what information you have:
   - Do you have origin? If not, need to ask
   - Do you have destination? Should have this
   - Do you have exact dates? If user says "December" without exact dates, need to ask
   - Do you have return date? Can calculate from "5 days" but prefer exact dates

Step 3: Decision:
   - If MISSING origin OR exact departure_date OR exact return_date → Call RequestClarification
   - If you HAVE all required info (origin, destination, departure_date, return_date) → Call FlightSearch

CRITICAL RULES:
- You MUST call a tool on EVERY turn - NEVER respond with just text
- If uncertain about dates, ask for exact dates in YYYY-MM-DD format
- When you have all 4 required fields with valid future dates, immediately call FlightSearch
- Keep clarification questions focused and brief (max 3 questions)

EXAMPLE 1:
User: "Plan a trip to Madrid in December for 5 days"
→ Call RequestClarification asking: "Where will you depart from? What are the exact dates?"

EXAMPLE 2:
User: "From Barcelona, December 15-20, 2025"
→ Call FlightSearch with origin=Barcelona, destination=Madrid, departure_date=2025-12-15, return_date=2025-12-20"""

    def _convert_proto_to_dict(self, proto_map) -> Dict[str, Any]:
        """Convert protobuf map to Python dict."""
        return dict(proto_map)

    def _serialize_part(self, part) -> Dict[str, Any]:
        """
        Serialize a response part for conversation history.
        Handles both text and function_call parts.
        """
        if hasattr(part, 'text') and part.text:
            return {'text': part.text}
        elif hasattr(part, 'function_call') and part.function_call:
            return {
                'function_call': {
                    'name': part.function_call.name,
                    'args': self._convert_proto_to_dict(part.function_call.args)
                }
            }
        else:
            return {'text': ''}

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize a property schema for Gemini compatibility."""
        sanitized = prop_schema.copy()
        if 'anyOf' in sanitized:
            for item in sanitized['anyOf']:
                if 'type' in item and item['type'] != 'null':
                    sanitized.update(item)
                    break
            del sanitized['anyOf']
        
        # Remove all unsupported fields
        for field in ['default', 'title', '$defs', 'examples', 'additionalProperties']:
            if field in sanitized:
                del sanitized[field]
        
        if 'type' in sanitized and isinstance(sanitized['type'], str):
            sanitized['type'] = sanitized['type'].upper()
        if sanitized.get('type') == 'ARRAY' and sanitized.get('items'):
            sanitized['items'] = self._sanitize_property_schema(sanitized['items'])
        if sanitized.get('type') == 'OBJECT' and sanitized.get('properties'):
            for key, val in sanitized['properties'].items():
                sanitized['properties'][key] = self._sanitize_property_schema(val)
        return sanitized

    def _pydantic_to_function_declaration(self, pydantic_model) -> Dict[str, Any]:
        """Convert Pydantic model to FunctionDeclaration dict."""
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

    def _create_gemini_tools(self) -> List:
        """STEP 3: Create Gemini tool declarations - includes RequestClarification."""
        tool_list = [RequestClarification, FlightSearch, HotelSearch, RestaurantSearch, AttractionsSearch, GenerateItinerary]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        return tools