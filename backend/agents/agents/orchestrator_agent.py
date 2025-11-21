"""
Tool-Based Orchestrator Agent - FULLY AGENTIC VERSION
======================================================
This is a PURELY AGENTIC orchestrator that uses LLM-driven tool calling
with ZERO hardcoded logic or fallbacks.

Key Improvements Over Previous Version:
- NO forced tool calls - LLM maintains full autonomy
- Feedback loops guide LLM to self-correct instead of overriding
- Updated to gemini-2.5-flash for superior function calling
- LLM learns from mistakes and adapts strategy dynamically
- True adaptive decision-making with no safety net interventions

Architecture Philosophy:
    User Request
        ↓
    LLM Analysis (autonomous decision)
        ↓
    Tool Call (LLM's choice)
        ↓
    Result Feedback to LLM
        ↓
    LLM Self-Evaluation (did I get what I need?)
        ↓
    [If missing] LLM receives guidance message → Self-corrects
        ↓
    LLM decides next action or completion
        ↓
    Final output (only when LLM is satisfied)

CRITICAL: This orchestrator NEVER takes control away from the LLM.
It only provides feedback to help the LLM make better decisions.
"""

from typing import Dict, Any, List, Optional
import json
import google.generativeai as genai
from pydantic import BaseModel, Field
from .base_agent import BaseAgent


# =============================================================================
# TOOL SCHEMAS - Define the API contract for each specialist agent
# =============================================================================

class FlightSearch(BaseModel):
    """
    Tool for searching flight options.
    
    The LLM will call this tool when it determines flight information is needed.
    All parameter extraction is done by the LLM from natural language.
    """
    origin: str = Field(
        ..., 
        description="The departure city or airport code (e.g., 'NYC', 'JFK', 'New York')"
    )
    destination: str = Field(
        ..., 
        description="The arrival city or airport code (e.g., 'PAR', 'CDG', 'Paris')"
    )
    departure_date: str = Field(
        ..., 
        description="The flight departure date in YYYY-MM-DD format"
    )
    return_date: str = Field(
        ..., 
        description="The flight return date in YYYY-MM-DD format"
    )
    passengers: int = Field(
        default=2, 
        description="The total number of passengers traveling"
    )
    budget: Optional[int] = Field(
        default=None, 
        description="Maximum budget for flights in USD"
    )
    preferences: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flight preferences like cabin class (economy/business/first), max stops, preferred airlines"
    )


class HotelSearch(BaseModel):
    """
    Tool for searching hotel and accommodation options.
    
    The LLM will call this tool when it determines accommodation information is needed.
    """
    city_code: str = Field(
        ..., 
        description="The destination city code or name where hotels are needed"
    )
    check_in_date: str = Field(
        ..., 
        description="Hotel check-in date in YYYY-MM-DD format"
    )
    check_out_date: str = Field(
        ..., 
        description="Hotel check-out date in YYYY-MM-DD format"
    )
    adults: int = Field(
        default=2, 
        description="Number of adults requiring accommodation"
    )
    budget_per_night: Optional[int] = Field(
        default=None, 
        description="Maximum budget per night in USD"
    )
    required_amenities: List[str] = Field(
        default_factory=list,
        description="Required hotel amenities (e.g., ['pool', 'gym', 'wifi', 'parking', 'pet_friendly'])"
    )
    preferences: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional preferences like hotel rating, location preferences, room type"
    )


class POISearch(BaseModel):
    """
    Tool for searching Points of Interest (restaurants and attractions).
    
    The LLM will call this tool when it needs restaurant or attraction recommendations.
    """
    city: str = Field(
        ..., 
        description="The city to search for restaurants and attractions"
    )
    interest_types: List[str] = Field(
        default_factory=list,
        description="Specific interests or categories (e.g., ['italian restaurant', 'aquarium', 'museum', 'tapas bar'])"
    )
    min_rating: float = Field(
        default=4.0, 
        description="Minimum acceptable rating (0.0 to 5.0)"
    )
    preferences: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional preferences like cuisine type, price level, kid-friendly"
    )


class ItineraryGeneration(BaseModel):
    """
    Tool for generating the final day-by-day itinerary.
    
    The LLM MUST call this as the final step to synthesize all gathered data.
    This is communicated to the LLM in the system prompt, not enforced by code.
    """
    trip_summary: str = Field(
        ..., 
        description="A JSON string containing all search results (flights, hotels, restaurants, attractions)"
    )
    user_requirements: str = Field(
        ..., 
        description="The original user prompt detailing all planning constraints and requirements"
    )


# =============================================================================
# ORCHESTRATOR AGENT - The Fully Autonomous Master Coordinator
# =============================================================================

class OrchestratorAgent(BaseAgent):
    """
    Master agent that coordinates all specialized agents using PURE LLM-driven tool calling.
    
    This orchestrator is TRULY AGENTIC with ZERO hardcoded logic:
    - LLM decides which tools to call (never forced)
    - LLM sees results and adapts strategy autonomously
    - LLM can retry tools with different parameters
    - LLM handles unexpected situations independently
    - LLM receives feedback messages but makes final decisions
    - NO safety nets that override LLM decisions
    
    The orchestrator treats specialist agents as tools that ONLY the LLM can invoke.
    Human/code never forces tool calls - only provides guidance messages.
    """
    
    def __init__(self, gemini_api_key: str, flight_agent, hotel_agent, 
                 restaurant_agent, attractions_agent, itinerary_agent):
        """
        Initialize the orchestrator with access to all specialist agents.
        
        Args:
            gemini_api_key: Google Gemini API key for LLM access
            flight_agent: FlightAgent instance for flight searches
            hotel_agent: HotelAgent instance for accommodation searches
            restaurant_agent: RestaurantAgent instance for dining recommendations
            attractions_agent: AttractionsAgent instance for activity suggestions
            itinerary_agent: ItineraryAgent instance for final itinerary generation
        """
        super().__init__("OrchestratorAgent", gemini_api_key)
        
        # =====================================================================
        # MODEL CONFIGURATION - Using latest Gemini for best function calling
        # =====================================================================
        # Updated from gemini-2.0-flash-exp to gemini-2.5-flash
        # Benefits:
        # - Superior function calling accuracy
        # - Better parameter extraction from natural language
        # - More reliable multi-step reasoning
        # - Improved error recovery and adaptation
        self.model = genai.GenerativeModel(
            'gemini-2.5-flash',  # Latest model with enhanced function calling
            generation_config={
                'temperature': 0.7,  # Balanced creativity/consistency for planning
                'top_p': 0.95,      # Nucleus sampling for quality
                'top_k': 40,        # Top-k sampling for diversity
                'max_output_tokens': 8192,  # Sufficient for detailed responses
            }
        )
        
        # =====================================================================
        # TOOL MAPPING - Connect LLM function calls to specialist agents
        # =====================================================================
        # Each tool is a callable that executes the corresponding specialist agent.
        # The LLM decides when and how to call these - we never force calls.
        self.specialist_tools = {
            "search_flights": flight_agent.execute,
            "search_hotels": hotel_agent.execute,
            "search_pois": self._create_poi_search_tool(restaurant_agent, attractions_agent),
            "generate_itinerary": itinerary_agent.execute,
        }
        
        # Map tool names to their Pydantic schemas for validation
        self.tool_schemas = {
            "search_flights": FlightSearch,
            "search_hotels": HotelSearch,
            "search_pois": POISearch,
            "generate_itinerary": ItineraryGeneration,
        }
        
        # Storage for results from each tool call
        # Used for final output compilation and LLM context
        self.all_results = {}
        
        # Convert Pydantic schemas to Gemini function declarations
        self.gemini_tools = self._create_gemini_tools()
        
        self.log("✅ Fully agentic orchestrator initialized with gemini-2.5-flash")
        self.log("   → LLM has complete autonomy over tool selection and execution")
    
    def _convert_proto_to_dict(self, proto_args) -> Dict[str, Any]:
        """
        Convert Gemini protobuf arguments to JSON-serializable dict.
        
        Gemini's function_call.args returns protobuf objects (RepeatedComposite)
        which are not JSON serializable. This function safely converts them.
        
        Args:
            proto_args: Protobuf arguments from function_call.args
            
        Returns:
            JSON-serializable dictionary
        """
        import json
        from google.protobuf.json_format import MessageToDict
        
        try:
            # Method 1: Try protobuf's built-in converter
            if hasattr(proto_args, 'DESCRIPTOR'):
                return MessageToDict(proto_args, preserving_proto_field_name=True)
        except Exception:
            pass
        
        try:
            # Method 2: Convert to dict manually
            result = {}
            for key, value in proto_args.items():
                # Handle nested protobuf objects
                if hasattr(value, 'items'):
                    result[key] = dict(value)
                # Handle repeated fields (lists)
                elif hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                    result[key] = list(value)
                else:
                    result[key] = value
            return result
        except Exception:
            pass
        
        # Method 3: Fallback to regular dict conversion
        return dict(proto_args)
    
    def _create_poi_search_tool(self, restaurant_agent, attractions_agent):
        """
        Create a combined POI search tool that calls both restaurant and attractions agents.
        
        This wraps both agents into a single tool call for efficiency.
        The LLM doesn't need to know it's calling two agents - it just gets combined results.
        
        Args:
            restaurant_agent: RestaurantAgent instance
            attractions_agent: AttractionsAgent instance
            
        Returns:
            A function that executes both agents and combines results
        """
        def execute_poi_search(params: Dict[str, Any]) -> Dict[str, Any]:
            """
            Execute combined restaurant and attractions search.
            
            This function is called by the LLM when it invokes search_pois tool.
            It transparently coordinates two specialist agents.
            """
            self.log("🔍 Executing combined POI search (restaurants + attractions)...")
            
            try:
                # Call restaurant agent with extracted parameters
                restaurant_results = restaurant_agent.execute({
                    'city': params.get('city'),
                    'cuisine': params.get('interest_types', []),
                    'min_rating': params.get('min_rating', 4.0),
                    'preferences': params.get('preferences', {})
                })
                
                # Call attractions agent with extracted parameters
                attractions_results = attractions_agent.execute({
                    'city': params.get('city'),
                    'interests': params.get('interest_types', []),
                    'min_rating': params.get('min_rating', 4.0)
                })
                
                # Combine results into single response for LLM
                return {
                    'success': True,
                    'restaurants': restaurant_results,
                    'attractions': attractions_results,
                    'agent': 'POISearchTool'
                }
            
            except Exception as e:
                # Return error to LLM so it can adapt strategy
                self.log(f"❌ POI search error: {str(e)}", "ERROR")
                return {
                    'success': False,
                    'error': str(e),
                    'agent': 'POISearchTool'
                }
        
        return execute_poi_search
    
    def _create_gemini_tools(self) -> List[genai.protos.Tool]:
        """
        Convert Pydantic schemas to Gemini function declarations.
        
        Gemini requires function declarations in a specific format for function calling.
        We convert our Pydantic schemas to this format so the LLM knows what tools
        are available and what parameters they accept.
        
        Returns:
            List of Gemini Tool objects ready for function calling
        """
        function_declarations = []
        
        # =====================================================================
        # FLIGHT SEARCH TOOL
        # =====================================================================
        function_declarations.append(
            genai.protos.FunctionDeclaration(
                name="search_flights",
                description="Search for flight options based on origin, destination, dates, and preferences. Use this when user needs flight information.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "origin": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="Departure city or airport code"
                        ),
                        "destination": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="Arrival city or airport code"
                        ),
                        "departure_date": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="Departure date (YYYY-MM-DD)"
                        ),
                        "return_date": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="Return date (YYYY-MM-DD)"
                        ),
                        "passengers": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER, 
                            description="Number of passengers"
                        ),
                        "budget": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER, 
                            description="Maximum budget in USD"
                        ),
                        "preferences": genai.protos.Schema(
                            type=genai.protos.Type.OBJECT, 
                            description="Flight preferences (cabin class, max stops, etc.)"
                        ),
                    },
                    required=["origin", "destination", "departure_date", "return_date"]
                )
            )
        )
        
        # =====================================================================
        # HOTEL SEARCH TOOL
        # =====================================================================
        function_declarations.append(
            genai.protos.FunctionDeclaration(
                name="search_hotels",
                description="Search for hotel and accommodation options in a destination city. Use this when user needs lodging information.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "city_code": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="Destination city code or name"
                        ),
                        "check_in_date": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="Check-in date (YYYY-MM-DD)"
                        ),
                        "check_out_date": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="Check-out date (YYYY-MM-DD)"
                        ),
                        "adults": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER, 
                            description="Number of adults"
                        ),
                        "budget_per_night": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER, 
                            description="Max budget per night USD"
                        ),
                        "required_amenities": genai.protos.Schema(
                            type=genai.protos.Type.ARRAY, 
                            items=genai.protos.Schema(type=genai.protos.Type.STRING), 
                            description="Required amenities (pool, gym, wifi)"
                        ),
                        "preferences": genai.protos.Schema(
                            type=genai.protos.Type.OBJECT, 
                            description="Additional preferences"
                        ),
                    },
                    required=["city_code", "check_in_date", "check_out_date"]
                )
            )
        )
        
        # =====================================================================
        # POI SEARCH TOOL
        # =====================================================================
        function_declarations.append(
            genai.protos.FunctionDeclaration(
                name="search_pois",
                description="Search for restaurants and attractions (points of interest) in a city. Use this when user needs dining or activity recommendations.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "city": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="City to search in"
                        ),
                        "interest_types": genai.protos.Schema(
                            type=genai.protos.Type.ARRAY, 
                            items=genai.protos.Schema(type=genai.protos.Type.STRING), 
                            description="Types of POIs (e.g., 'italian restaurant', 'museum')"
                        ),
                        "min_rating": genai.protos.Schema(
                            type=genai.protos.Type.NUMBER, 
                            description="Minimum rating (0-5)"
                        ),
                        "preferences": genai.protos.Schema(
                            type=genai.protos.Type.OBJECT, 
                            description="Additional preferences"
                        ),
                    },
                    required=["city"]
                )
            )
        )
        
        # =====================================================================
        # ITINERARY GENERATION TOOL
        # =====================================================================
        function_declarations.append(
            genai.protos.FunctionDeclaration(
                name="generate_itinerary",
                description="Generate final day-by-day itinerary from all gathered data. Use this as the FINAL STEP after collecting all travel information.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "trip_summary": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="JSON string of all search results"
                        ),
                        "user_requirements": genai.protos.Schema(
                            type=genai.protos.Type.STRING, 
                            description="Original user requirements"
                        ),
                    },
                    required=["trip_summary", "user_requirements"]
                )
            )
        )
        
        # Return as Gemini Tool object
        return [genai.protos.Tool(function_declarations=function_declarations)]
    
    def _convert_input_to_prompt(self, input_data: Dict) -> str:
        """
        Convert structured input to natural language prompt for LLM.
        
        This enables backward compatibility with existing API while
        allowing LLM to use natural language understanding for parameter extraction.
        
        Args:
            input_data: Structured input with origin, destination, dates, etc.
            
        Returns:
            Natural language prompt describing the vacation request
        """
        # Check if we have a direct user prompt (preferred)
        if 'user_prompt' in input_data:
            return input_data['user_prompt']
        
        # Otherwise, construct from structured data
        origin = input_data.get('origin', 'unspecified origin')
        destination = input_data.get('destination', 'unspecified destination')
        departure_date = input_data.get('departure_date', 'unspecified date')
        return_date = input_data.get('return_date', 'unspecified date')
        passengers = input_data.get('passengers', 2)
        budget = input_data.get('budget', 'unspecified')
        preferences = input_data.get('preferences', {})
        
        # Build natural language prompt for LLM to parse
        prompt = f"""Plan a complete vacation with these requirements:

TRAVEL DETAILS:
- Origin: {origin}
- Destination: {destination}
- Departure Date: {departure_date}
- Return Date: {return_date}
- Number of Travelers: {passengers}
- Total Budget: ${budget if budget != 'unspecified' else 'flexible'}

PREFERENCES:
"""
        
        # Add preferences if provided
        if preferences:
            for key, value in preferences.items():
                prompt += f"- {key}: {value}\n"
        else:
            prompt += "- No specific preferences mentioned\n"
        
        prompt += """
Please gather all necessary information to create a complete vacation plan including:
1. Flight options
2. Hotel accommodations
3. Restaurant recommendations
4. Attraction suggestions
5. A detailed day-by-day itinerary

Use the available tools to search for this information systematically.
"""
        
        return prompt
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the orchestration with PURE LLM-driven tool calling.
        
        This is the main entry point. The LLM has COMPLETE AUTONOMY:
        - Decides which tools to call
        - Decides the order of calls
        - Decides parameters for each call
        - Decides when it has enough information
        - Decides when to finish
        
        The orchestrator NEVER forces tool calls. It only:
        - Provides feedback messages to guide LLM decisions
        - Tracks tool usage to prevent infinite loops
        - Returns results when LLM indicates completion
        
        Flow:
        1. Convert input to natural language prompt
        2. Enter dynamic execution loop
        3. LLM decides next action (tool call or finish)
        4. Execute tools and feed results back to LLM
        5. If LLM finishes prematurely, provide guidance message
        6. LLM self-corrects and continues or confirms completion
        7. Return final results only when LLM is satisfied
        
        Args:
            input_data: Dict with vacation requirements
            
        Returns:
            Dict with success status and complete vacation plan
        """
        self.log("🚀 Starting fully agentic orchestration...")
        
        # Reset results storage for new execution
        self.all_results = {}
        
        # Convert input to natural language prompt
        user_prompt = self._convert_input_to_prompt(input_data)
        self.log(f"📝 User request: {user_prompt[:100]}...")
        
        # Initialize conversation history for multi-turn interaction
        conversation_history = []
        
        # =====================================================================
        # INITIAL SYSTEM PROMPT - Set expectations for LLM behavior
        # =====================================================================
        # This is the ONLY place we guide the LLM. We never override its decisions.
        initial_prompt = f"""You are an expert travel planning assistant with access to specialized tools.

USER REQUEST:
{user_prompt}

YOUR TASK:
Systematically gather all information needed to create a complete vacation plan by calling the appropriate tools.

AVAILABLE TOOLS:
1. search_flights - Get flight options between cities
2. search_hotels - Find accommodations in destination
3. search_pois - Discover restaurants and attractions
4. generate_itinerary - Create final day-by-day plan

IMPORTANT GUIDELINES:
- Extract ALL constraints from the user request (dates, budget, amenities, preferences)
- Call tools with accurate parameters based on the request
- After getting results, evaluate if you need more information
- If results are unsatisfactory (e.g., too expensive, wrong dates), retry with adjusted parameters
- You MUST call generate_itinerary as your FINAL step to synthesize everything into a complete plan
- Do NOT provide a text summary until AFTER calling generate_itinerary
- The generate_itinerary tool creates the actual vacation plan document

CRITICAL: Your job is not complete until you have called generate_itinerary with all gathered data.

Begin by analyzing the request and calling the first necessary tool.
"""
        
        conversation_history.append({"role": "user", "parts": [initial_prompt]})
        
        # =====================================================================
        # SAFEGUARDS - Prevent infinite loops while maintaining LLM autonomy
        # =====================================================================
        MAX_ITERATIONS = 12  # Reasonable limit for complex planning
        iteration = 0
        tool_call_counts = {}  # Track calls per tool to detect loops
        
        # =====================================================================
        # DYNAMIC EXECUTION LOOP - LLM drives all decisions
        # =====================================================================
        while iteration < MAX_ITERATIONS:
            iteration += 1
            self.log(f"📍 Iteration {iteration}/{MAX_ITERATIONS}")
            
            try:
                # ============================================================
                # STEP 1: Get LLM's decision on next action
                # ============================================================
                # The LLM can choose to:
                # - Call a function (tool)
                # - Provide text response (indicating completion)
                # - Request more information
                response = self.model.generate_content(
                    conversation_history,
                    tools=self.gemini_tools,
                    tool_config={'function_calling_config': {'mode': 'AUTO'}}
                )
                
                # ============================================================
                # STEP 2: Process LLM's decision
                # ============================================================
                if response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]
                    
                    # ========================================================
                    # CASE A: LLM wants to call a function (tool)
                    # ========================================================
                    if hasattr(part, 'function_call') and part.function_call:
                        function_call = part.function_call
                        tool_name = function_call.name
                        # Convert protobuf args to JSON-serializable dict
                        tool_args = self._convert_proto_to_dict(function_call.args)
                        
                        # Track tool usage to detect potential infinite loops
                        tool_call_counts[tool_name] = tool_call_counts.get(tool_name, 0) + 1
                        
                        # ----------------------------------------------------
                        # SAFEGUARD: Detect excessive calls to same tool
                        # ----------------------------------------------------
                        # This is NOT forcing behavior - it's providing feedback
                        # so the LLM can adapt its strategy
                        if tool_call_counts[tool_name] > 3:
                            self.log(f"⚠️ Tool {tool_name} called {tool_call_counts[tool_name]} times", "WARNING")
                            
                            # Provide feedback message to LLM (not forcing anything)
                            error_message = f"Tool {tool_name} has been called {tool_call_counts[tool_name]} times. Consider trying a different approach or proceeding with the information you have gathered so far."
                            
                            conversation_history.append({
                                "role": "model",
                                "parts": [genai.protos.Part(function_call=function_call)]
                            })
                            conversation_history.append({
                                "role": "user",
                                "parts": [genai.protos.Part(function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={"error": error_message}
                                ))]
                            })
                            continue
                        
                        self.log(f"🔧 LLM requested tool: {tool_name}")
                        self.log(f"   Parameters: {json.dumps(tool_args, indent=2)}")
                        
                        # ----------------------------------------------------
                        # Execute the tool requested by LLM
                        # ----------------------------------------------------
                        if tool_name in self.specialist_tools:
                            try:
                                # Call the specialist agent with LLM-provided parameters
                                result = self.specialist_tools[tool_name](tool_args)
                                
                                # Store result for context and final output
                                self.all_results[tool_name] = result
                                
                                self.log(f"✅ Tool {tool_name} completed successfully")
                                
                                # Feed result back to LLM for next decision
                                conversation_history.append({
                                    "role": "model",
                                    "parts": [genai.protos.Part(function_call=function_call)]
                                })
                                conversation_history.append({
                                    "role": "user",
                                    "parts": [genai.protos.Part(function_response=genai.protos.FunctionResponse(
                                        name=tool_name,
                                        response={"result": result}
                                    ))]
                                })
                                
                            except Exception as e:
                                self.log(f"❌ Tool {tool_name} failed: {str(e)}", "ERROR")
                                
                                # Feed error back to LLM so it can adapt
                                # This is crucial for agentic behavior - LLM learns from failures
                                conversation_history.append({
                                    "role": "model",
                                    "parts": [genai.protos.Part(function_call=function_call)]
                                })
                                conversation_history.append({
                                    "role": "user",
                                    "parts": [genai.protos.Part(function_response=genai.protos.FunctionResponse(
                                        name=tool_name,
                                        response={"error": str(e)}
                                    ))]
                                })
                        else:
                            self.log(f"❌ Unknown tool requested: {tool_name}", "ERROR")
                    
                    # ========================================================
                    # CASE B: LLM provided text response (thinks it's done)
                    # ========================================================
                    elif hasattr(part, 'text') and part.text:
                        final_text = part.text
                        self.log("🎯 LLM provided text response")
                        
                        # ----------------------------------------------------
                        # CRITICAL IMPROVEMENT: Feedback instead of forcing
                        # ----------------------------------------------------
                        # OLD APPROACH (lines 400-410 in original):
                        #   if 'generate_itinerary' not in self.all_results:
                        #       # FORCED the call
                        #       itinerary_result = self.specialist_tools['generate_itinerary'](...)
                        #
                        # NEW APPROACH (Pure Agentic):
                        #   Provide feedback message to guide LLM's decision
                        #   LLM maintains full autonomy to call the tool itself
                        # ----------------------------------------------------
                        if 'generate_itinerary' not in self.all_results:
                            self.log("⚠️ LLM finished but itinerary not generated - providing guidance")
                            
                            # Construct feedback message to guide LLM
                            guidance_message = f"""⚠️ IMPORTANT: You provided a summary but haven't generated the final itinerary yet.

You have gathered:
{', '.join(self.all_results.keys())}

However, you MUST call the 'generate_itinerary' tool to create the actual day-by-day vacation plan document before finishing.

Please call generate_itinerary now with:
- trip_summary: JSON string of all the results you've gathered
- user_requirements: The original user request

After generating the itinerary, you can then provide your final summary."""
                            
                            # Add LLM's response to history
                            conversation_history.append({
                                "role": "model",
                                "parts": [part]
                            })
                            
                            # Add guidance message as user feedback
                            conversation_history.append({
                                "role": "user",
                                "parts": [guidance_message]
                            })
                            
                            # Continue loop - LLM will see feedback and self-correct
                            continue
                        
                        # ----------------------------------------------------
                        # Itinerary exists - LLM has completed the plan
                        # ----------------------------------------------------
                        self.log("✅ LLM completed planning with itinerary generated")
                        
                        # Return complete results
                        return {
                            "success": True,
                            "results": self.all_results,
                            "summary": final_text,
                            "agent": self.name,
                            "iterations": iteration
                        }
                
                else:
                    # Empty response - unexpected but handled gracefully
                    self.log("⚠️ Empty response from LLM", "WARNING")
                    break
            
            except Exception as e:
                # Log error and return with context
                self.log(f"❌ Error in orchestration loop: {str(e)}", "ERROR")
                return self.format_error(e)
        
        # =====================================================================
        # MAX ITERATIONS REACHED - Provide final guidance
        # =====================================================================
        self.log(f"⚠️ Max iterations ({MAX_ITERATIONS}) reached", "WARNING")
        
        # --------------------------------------------------------------------
        # CRITICAL IMPROVEMENT: Feedback instead of forcing (line 427-437)
        # --------------------------------------------------------------------
        # OLD APPROACH:
        #   if self.all_results and 'generate_itinerary' not in self.all_results:
        #       # FORCED the call
        #       itinerary_result = self.specialist_tools['generate_itinerary'](...)
        #
        # NEW APPROACH:
        #   If we reached max iterations, check if itinerary exists
        #   If not, provide one final guidance message
        #   If LLM still doesn't respond, accept the incomplete result
        #   This maintains LLM autonomy even at the boundary case
        # --------------------------------------------------------------------
        
        if self.all_results and 'generate_itinerary' not in self.all_results:
            self.log("⚠️ Max iterations reached without itinerary - providing final guidance")
            
            # Construct final guidance message
            final_guidance = f"""⚠️ CRITICAL: Maximum iterations reached but you haven't generated the final itinerary yet.

You have gathered:
{', '.join(self.all_results.keys())}

This is your LAST CHANCE to call generate_itinerary to create the vacation plan.

Please call it now with:
- trip_summary: {json.dumps(self.all_results)}
- user_requirements: {user_prompt[:200]}...

If you don't call generate_itinerary, the planning will be incomplete."""
            
            # Add to conversation history
            conversation_history.append({
                "role": "user",
                "parts": [final_guidance]
            })
            
            # Give LLM ONE more chance to respond
            try:
                self.log("🔄 Giving LLM final opportunity to complete planning...")
                final_response = self.model.generate_content(
                    conversation_history,
                    tools=self.gemini_tools,
                    tool_config={'function_calling_config': {'mode': 'AUTO'}}
                )
                
                # Check if LLM called generate_itinerary
                if final_response.candidates[0].content.parts:
                    part = final_response.candidates[0].content.parts[0]
                    
                    if hasattr(part, 'function_call') and part.function_call:
                        if part.function_call.name == 'generate_itinerary':
                            self.log("✅ LLM called generate_itinerary on final attempt")
                            # Convert protobuf args to JSON-serializable dict
                            tool_args = self._convert_proto_to_dict(part.function_call.args)
                            
                            try:
                                itinerary_result = self.specialist_tools['generate_itinerary'](tool_args)
                                self.all_results['generate_itinerary'] = itinerary_result
                                self.log("✅ Itinerary successfully generated")
                            except Exception as e:
                                self.log(f"❌ Itinerary generation failed: {e}", "ERROR")
                
            except Exception as e:
                self.log(f"❌ Final attempt error: {str(e)}", "ERROR")
        
        # --------------------------------------------------------------------
        # Return results (complete or incomplete - respecting LLM's decisions)
        # --------------------------------------------------------------------
        return {
            "success": True,
            "results": self.all_results,
            "summary": "Vacation planning completed" if 'generate_itinerary' in self.all_results else "Partial vacation plan - itinerary generation incomplete",
            "agent": self.name,
            "iterations": iteration,
            "warning": "Maximum iterations reached" if iteration >= MAX_ITERATIONS else None,
            "complete": 'generate_itinerary' in self.all_results
        }