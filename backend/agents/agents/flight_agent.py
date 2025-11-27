"""
FlightAgent - Production Version with Real Amadeus API Integration
"""

import json
import os
import sys
from typing import Dict, Any, List, Optional, Union, Tuple
from dotenv import load_dotenv

import google.generativeai as genai
from google.generativeai import types as genai_types 
from google.ai import generativelanguage as glm
from pydantic import BaseModel, Field, ValidationError

mcp_path = os.path.join(os.path.dirname(__file__), '..', '..', 'mcp-servers', 'flights')
if mcp_path not in sys.path:
    sys.path.insert(0, mcp_path)

from amadeus_client import AmadeusFlightClient

env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path)

class BaseAgent:
    def __init__(self, name, api_key):
        self.name = name
        self.api_key = api_key
    def log(self, message: str, level: str = "INFO"):
        print(f"[{self.name}][{level}] {message}")
    def format_error(self, e: Exception) -> Dict[str, Any]:
        return {"success": False, "error": f"Agent Error: {str(e)}"}

class SearchFlights(BaseModel):
    origin: str = Field(..., description="Origin airport IATA code (e.g., 'SFO').")
    destination: str = Field(..., description="Destination airport IATA code (e.g., 'CDG').")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format.")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format (optional).")
    passengers: int = Field(1, description="Number of passengers (default: 1).")
    cabin: str = Field("economy", description="Cabin class: economy, premium_economy, business, or first.")
    max_results: int = Field(20, description="Maximum number of flight results to return (default: 20).")

class AnalyzeAndFilter(BaseModel):
    analysis_criteria: str = Field("lowest_price", description="Analysis type: 'lowest_price', 'fastest', 'best_value', or 'most_convenient'.")
    max_price: Optional[int] = Field(None, description="Maximum total price allowed in USD (optional budget constraint).")

class ReflectAndModifySearch(BaseModel):
    reasoning: str = Field(..., description="Detailed explanation of why previous search failed or how to adjust based on feedback.")
    new_search_parameters: SearchFlights = Field(..., description="Complete new parameters for the next SearchFlights call.")

class ProvideRecommendation(BaseModel):
    top_flight_ids: List[str] = Field(default=[], description="List of 3-5 best flight IDs ranked by the LLM. Empty list if no flights found.")
    reasoning: str = Field(..., description="Detailed reasoning for why these flights were selected, or explanation of why no flights were found.")
    summary: str = Field(..., description="Brief summary comparing options and asking user to choose or provide refinement feedback. If no flights found, explain the issue.")
    user_input_required: bool = Field(True, description="MUST be True. Signals Orchestrator to pause for human input.")

class FinalizeSelection(BaseModel):
    selected_flight_id: str = Field(..., description="The ID of the flight the human selected.")
    confirmation_message: str = Field(..., description="Brief confirmation message to the human about their selection.")

class FlightAgent(BaseAgent):
    
    def __init__(self, gemini_api_key: str):
        super().__init__("FlightAgent", gemini_api_key)
        
        amadeus_api_key = os.getenv('AMADEUS_API_KEY')
        amadeus_api_secret = os.getenv('AMADEUS_API_SECRET')
        
        if not amadeus_api_key or not amadeus_api_secret:
            raise ValueError("AMADEUS_API_KEY and AMADEUS_API_SECRET must be set in environment variables!")
        
        self.amadeus_client = AmadeusFlightClient(amadeus_api_key, amadeus_api_secret)
        self.log("✅ Amadeus Flight Client initialized successfully")
        
        self.flight_search_results = []
        self.analysis_results = {}
        
        self.tool_functions = {
            "SearchFlights": self._tool_search_flights,
            "AnalyzeAndFilter": self._tool_analyze_and_filter,
            "ReflectAndModifySearch": self._tool_reflect_and_modify_search,
            "ProvideRecommendation": self._tool_provide_recommendation,
            "FinalizeSelection": self._tool_finalize_selection
        }
        
        self.tool_schemas = {
            "SearchFlights": SearchFlights,
            "AnalyzeAndFilter": AnalyzeAndFilter,
            "ReflectAndModifySearch": ReflectAndModifySearch,
            "ProvideRecommendation": ProvideRecommendation,
            "FinalizeSelection": FinalizeSelection
        }
        
        self.system_instruction = self._build_system_instruction()
        self.gemini_tools = self._create_gemini_tools()

        self.model = genai.GenerativeModel(
            'gemini-2.0-flash-exp',
            tools=self.gemini_tools, 
            system_instruction=self.system_instruction,
            generation_config={'temperature': 0.7}
        )
        self.log("✅ Enhanced Pure Agentic FlightAgent initialized with REAL Amadeus API")

    def execute(self, params: Dict[str, Any], continuation_message: Optional[Dict[str, Any]] = None, max_turns: int = 5) -> Dict[str, Any]:
        try:
            # Check for FINAL_CHOICE_TRIGGER in continuation message
            if continuation_message:
                content = continuation_message.get('content', '')
                
                # Detect final choice trigger
                if 'FINAL_CHOICE_TRIGGER' in content:
                    # Extract flight ID from content string
                    import re
                    match = re.search(r"flight ID ['\"](\d+)['\"]", content)
                    
                    if match:
                        selected_id = match.group(1)
                        self.log(f"🎯 FINAL CHOICE: Flight {selected_id} selected")
                        
                        # Find in current results
                        selected_flight = next((f for f in self.flight_search_results if f['id'] == selected_id), None)
                        
                        if selected_flight:
                            return {
                                "success": True,
                                "agent": self.name,
                                "status_code": "SUCCESS",
                                "message": f"Flight {selected_id} confirmed",
                                "final_flight": selected_flight
                            }
                        else:
                            # Flight not in results but ID is valid - return success anyway
                            self.log("⚠️ Flight not in results array, but returning SUCCESS")
                            return {
                                "success": True,
                                "agent": self.name,
                                "status_code": "SUCCESS",
                                "message": f"Flight {selected_id} confirmed",
                                "final_flight": {"id": selected_id}
                            }
                
                # Regular refinement feedback - start LLM conversation
                user_message = content
            else:
                # Initial execution
                self.log("▶️ Starting initial flight search...")
                user_message = (
                    f"Find flights from {params.get('origin')} to {params.get('destination')} "
                    f"departing {params.get('departure_date')}"
                )
                if params.get('return_date'):
                    user_message += f", returning {params.get('return_date')}"
                if params.get('budget'):
                    user_message += f", with a budget of ${params.get('budget')}"
                user_message += ". Start by calling SearchFlights with appropriate parameters."
            
            chat = self.model.start_chat()
            response = chat.send_message(user_message)
            
            for turn in range(max_turns):
                self.log(f"🔄 Turn {turn + 1}/{max_turns}")
                
                current_function_calls = []
                if response.candidates and response.candidates[0].content:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            current_function_calls.append(part.function_call)
                
                if not current_function_calls:
                    self.log("⚠️  LLM gave text response instead of tool call", "WARN")
                    break
                
                tool_results = []
                
                for func_call in current_function_calls:
                    tool_name = func_call.name
                    tool_args = self._convert_proto_to_dict(func_call.args)
                    
                    self.log(f"🛠️  LLM called tool: {tool_name}")
                    
                    result = self._execute_tool(tool_name, tool_args)
                    tool_results.append(self._create_tool_response(func_call, result))
                    
                    if tool_name == "ProvideRecommendation":
                        self.log("⏸️  HIL PAUSE - Recommendations ready for human")
                        return self._format_recommendation_for_pause()
                    
                    elif tool_name == "FinalizeSelection":
                        self.log("✅ Selection finalized - Returning SUCCESS")
                        return result
                
                tool_response_content = glm.Content(role="function", parts=tool_results)
                response = chat.send_message(tool_response_content)
            
            self.log("⚠️  Max turns reached without completion", "WARN")
            return self._force_completion()
            
        except Exception as e:
            self.log(f"❌ Error in execute: {str(e)}", "ERROR")
            import traceback
            traceback.print_exc()
            return self.format_error(e)

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        schema = self.tool_schemas.get(tool_name)
        func = self.tool_functions.get(tool_name)
        if not schema or not func:
            raise ValueError(f"Unknown tool or function mapping: {tool_name}")
        validated_args = schema(**tool_args)
        return func(validated_args)
    
    def _tool_search_flights(self, params: SearchFlights) -> Dict[str, Any]:
        self.log(f"🔍 Searching REAL flights via Amadeus: {params.origin} → {params.destination}")
        
        api_result = self._search_flights_real_api(params)
        
        if not api_result.get("success"):
            error_msg = api_result.get("error", "Unknown error")
            error_details = api_result.get("error_details", {})
            self.log(f"❌ API call failed: {error_msg}", "ERROR")
            return {
                "success": False,
                "error": error_msg,
                "message": f"❌ Flight search failed. {error_details.get('suggested_fix', 'Please review your search parameters.')}"
            }
        
        flights = api_result.get("flights", [])
        self.log(f"📦 Received {len(flights)} flights from Amadeus")
        
        valid_flights = []
        invalid_flights = []
        
        for flight in flights:
            if self._validate_route_match(flight, params.origin, params.destination):
                valid_flights.append(flight)
            else:
                invalid_flights.append(flight)
                outbound = flight.get('outbound', {})
                self.log(
                    f"⚠️  Filtered out mismatched route: {outbound.get('from')} → {outbound.get('to')} "
                    f"(expected: {params.origin} → {params.destination})",
                    "WARN"
                )
        
        self.log(f"✅ Route validation: {len(valid_flights)} valid, {len(invalid_flights)} filtered out")
        
        current_ids = {f['id'] for f in self.flight_search_results}
        new_flights = [f for f in valid_flights if f['id'] not in current_ids]
        self.flight_search_results.extend(new_flights)
        
        if len(valid_flights) == 0:
            return {
                "success": False,
                "flights_found_this_call": 0,
                "total_flights_stored": len(self.flight_search_results),
                "message": f"❌ No flights found matching {params.origin} → {params.destination}. The API returned {len(flights)} flights but none matched the requested route.",
                "suggestion": "Try searching with major airport codes (e.g., 'JFK' instead of 'NYC', 'MAD' for Madrid)"
            }
        
        return {
            "success": True,
            "flights_found_this_call": len(valid_flights),
            "flights_filtered": len(invalid_flights),
            "total_flights_stored": len(self.flight_search_results),
            "message": f"✅ Found {len(valid_flights)} matching flights. Call AnalyzeAndFilter to rank them.",
            "sample_flights": new_flights[:3] if new_flights else valid_flights[:3]
        }
    
    def _tool_analyze_and_filter(self, params: AnalyzeAndFilter) -> Dict[str, Any]:
        self.log(f"📊 Analyzing {len(self.flight_search_results)} stored flights...")
        filtered_flights = self.flight_search_results.copy()
        
        if params.max_price:
            original_count = len(filtered_flights)
            filtered_flights = [f for f in filtered_flights if f['price'] <= params.max_price]
            self.log(f"💰 Filtered by max price ${params.max_price}: {original_count} → {len(filtered_flights)} flights")

        if params.analysis_criteria == "lowest_price":
            filtered_flights.sort(key=lambda f: f['price'])
        elif params.analysis_criteria == "fastest":
            filtered_flights.sort(key=lambda f: self._parse_duration_minutes(f['outbound'].get('duration', '999h')))
        else:
            filtered_flights.sort(key=lambda f: (f['price'], self._parse_duration_minutes(f['outbound'].get('duration', '0h'))))

        self.analysis_results['last_filtered_flights'] = filtered_flights
        
        return {
            "success": True,
            "filtered_count": len(filtered_flights),
            "message": f"✅ Analyzed {len(filtered_flights)} flights ranked by {params.analysis_criteria}. Call ProvideRecommendation to show top 3-5 to user.",
            "top_3_summary": [
                {
                    "id": f['id'], 
                    "price": f['price'], 
                    "summary": f"{f['outbound'].get('stops', 0)} stops, {f['outbound'].get('duration', 'N/A')}"
                } for f in filtered_flights[:3]
            ]
        }
    
    def _tool_reflect_and_modify_search(self, params: ReflectAndModifySearch) -> Dict[str, Any]:
        self.log("🧠 Agent Reflection:")
        self.log(f"   Reasoning: {params.reasoning}")
        return {
            "success": True,
            "message": f"Reflection recorded. Call SearchFlights with the new parameters."
        }

    def _tool_provide_recommendation(self, params: ProvideRecommendation) -> Dict[str, Any]:
        self.log(f"⭐ Recommendation provided for {len(params.top_flight_ids)} flights.")
        self.analysis_results['last_recommendation'] = params.model_dump()
        return {
            "success": True,
            "message": "Recommendation prepared. Waiting for Orchestrator to pause for human input."
        }

    def _tool_finalize_selection(self, params: FinalizeSelection) -> Dict[str, Any]:
        selected_id = params.selected_flight_id
        self.log(f"✅ Finalizing selection: {selected_id}")
        
        selected_flight = next((f for f in self.flight_search_results if f['id'] == selected_id), None)
        
        if not selected_flight:
            return {
                "success": False,
                "error": f"Flight ID {selected_id} not found in search results"
            }
        
        return {
            "success": True,
            "agent": self.name,
            "status_code": "SUCCESS",
            "message": params.confirmation_message,
            "final_flight": selected_flight
        }

    def _search_flights_real_api(self, params: SearchFlights) -> Dict[str, Any]:
        try:
            self.log("📡 Calling Amadeus API for real flight data...")
            
            flights = self.amadeus_client.search_flights(
                origin=params.origin,
                destination=params.destination,
                departure_date=params.departure_date,
                return_date=params.return_date,
                adults=params.passengers,
                max_results=params.max_results
            )
            
            self.log(f"✅ Amadeus returned {len(flights)} real flights")
            return {"success": True, "flights": flights}
            
        except Exception as e:
            error_message = str(e)
            self.log(f"❌ Amadeus API call failed: {error_message}", "ERROR")
            
            error_details = {
                "origin": params.origin,
                "destination": params.destination,
                "departure_date": params.departure_date,
                "return_date": params.return_date
            }
            
            if "INVALID FORMAT" in error_message or "3-letter code" in error_message:
                error_details["suggested_fix"] = "Airport codes must be 3-letter IATA codes (e.g., 'SFO' for San Francisco, 'MAD' for Madrid)."
            elif "No flight" in error_message or "not found" in error_message.lower():
                error_details["suggested_fix"] = "No flights found for these parameters. Try different dates or nearby airports."
            else:
                error_details["suggested_fix"] = "Check if the search parameters are valid."
            
            return {
                "success": False,
                "error": error_message,
                "error_details": error_details
            }

    def _validate_route_match(self, flight: Dict[str, Any], expected_origin: str, expected_destination: str) -> bool:
        outbound = flight.get('outbound', {})
        actual_from = outbound.get('from', '').upper()
        actual_to = outbound.get('to', '').upper()
        
        expected_origin = expected_origin.upper()
        expected_destination = expected_destination.upper()
        
        origin_match = actual_from == expected_origin
        
        dest_aliases = {
            'NYC': ['JFK', 'LGA', 'EWR'],
            'LON': ['LHR', 'LGW', 'STN', 'LCY'],
            'PAR': ['CDG', 'ORY'],
            'BER': ['BER', 'SXF', 'TXL'],
            'MIL': ['MXP', 'LIN'],
            'ROM': ['FCO', 'CIA'],
            'TYO': ['NRT', 'HND']
        }
        
        dest_match = (
            actual_to == expected_destination or
            actual_to in dest_aliases.get(expected_destination, []) or
            expected_destination in dest_aliases.get(actual_to, [])
        )
        
        return origin_match and dest_match

    def _format_recommendation_for_pause(self) -> Dict[str, Any]:
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

    def _force_completion(self) -> Dict[str, Any]:
        top_flights = self.analysis_results.get('last_filtered_flights', [])
        
        if not top_flights:
            status = "STATUS_NO_RESULTS_FOUND"
            summary = "Search failed to return any flights."
        else:
            status = "STATUS_INCOMPLETE_LOOP"
            summary = "Agent reached iteration limit. Returning best available analysis."

        return {
            "success": False,
            "agent": self.name,
            "status_code": status,
            "summary": summary,
            "recommended_flights": top_flights[:3]
        }
    
    def _parse_duration_minutes(self, duration_str: str) -> int:
        try:
            total_minutes = 0
            duration_str = duration_str.replace('PT', '')
            
            if 'H' in duration_str:
                hours_str = duration_str.split('H')[0]
                total_minutes += int(hours_str) * 60
                duration_str = duration_str.split('H')[1] if 'H' in duration_str else ''
            
            if 'M' in duration_str:
                minutes_str = duration_str.replace('M', '')
                if minutes_str:
                    total_minutes += int(minutes_str)
            
            return total_minutes
        except:
            return 999999

    def _convert_proto_to_dict(self, proto_map) -> Dict[str, Any]:
        return dict(proto_map)

    def _create_tool_response(self, func_call, result: Dict[str, Any]):
        return glm.Part(
            function_response=glm.FunctionResponse(
                name=func_call.name,
                response={'result': result}
            )
        )

    def _sanitize_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        python_type = prop_schema.get("type", "string")
        
        type_map = {
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT"
        }
        
        gemini_type = type_map.get(python_type, "STRING")
        description = prop_schema.get("description", "")
        
        result = {"type": gemini_type, "description": description}
        
        if python_type == "array" and "items" in prop_schema:
            result["items"] = self._sanitize_property_schema(prop_schema["items"])
        
        if "enum" in prop_schema:
            result["enum"] = prop_schema["enum"]
        
        return result

    def _pydantic_to_function_declaration(self, pydantic_model: Any) -> Dict[str, Any]:
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
            "parameters": {
                "type": "OBJECT",
                "properties": sanitized_properties,
                "required": required_params
            }
        }

    def _create_gemini_tools(self) -> List[Any]:
        tool_list = [SearchFlights, AnalyzeAndFilter, ReflectAndModifySearch, ProvideRecommendation, FinalizeSelection]
        tools = []
        for pydantic_model in tool_list:
            declaration_dict = self._pydantic_to_function_declaration(pydantic_model)
            tools.append(genai_types.Tool(function_declarations=[declaration_dict]))
        return tools

    def _build_system_instruction(self) -> str:
        return """You are a highly autonomous Flight Search Agent. Your goal is to find the best flights and pause for human confirmation.

YOUR WORKFLOW:
1. Call SearchFlights with appropriate parameters
2. Call AnalyzeAndFilter to rank the flights
3. Call ProvideRecommendation with top 3-5 flight IDs to pause for human input
4. When you see "FINAL_CHOICE_TRIGGER", call FinalizeSelection immediately

CRITICAL RULES:
- ALWAYS call a tool on every turn - NEVER give text-only responses
- After SearchFlights succeeds, immediately call AnalyzeAndFilter
- After AnalyzeAndFilter succeeds, immediately call ProvideRecommendation
- Never skip steps or give text responses"""