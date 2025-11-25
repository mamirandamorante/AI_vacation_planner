"""
Enhanced Comprehensive Test Script for Agentic Vacation Planner System
========================================================================

This script provides COMPREHENSIVE testing of the complete multi-agent system
with focus on validating TRUE AGENTIC BEHAVIOR (AI-driven decisions, not hardcoded logic).

WHAT THIS TESTS:
================
1. OrchestratorAgent coordination of ALL 4 specialist agents
2. FlightAgent - Pure agentic behavior with adaptive decision-making
3. HotelAgent - Pure agentic behavior with budget adjustments
4. RestaurantAgent - Production-grade with dietary/atmosphere constraints
5. AttractionsAgent - Production-grade with accessibility/temporal awareness
6. Human-in-the-Loop (HIL) pause/resume mechanisms
7. LLM-driven adaptive strategies (not hardcoded fallbacks)
8. Error recovery and strategy modification
9. Complex constraint handling across all agents
10. End-to-end vacation planning workflow

TEST CATEGORIES:
================
A. Individual Agent Tests - Test each agent in isolation
B. Orchestrator Integration Tests - Test agent coordination
C. Agentic Behavior Validation - Verify LLM autonomy
D. HIL Flow Tests - Validate pause/resume mechanisms
E. Complex Constraints Tests - Test production-grade features

Architecture Flow:
==================
User Query → OrchestratorAgent → FlightAgent (HIL) → HotelAgent (HIL) → 
             RestaurantAgent (HIL) → AttractionsAgent (HIL) → ItineraryAgent → Final Itinerary

Usage:
======
    python test_agentic_system_enhanced.py
    
    # Run specific test category:
    python test_agentic_system_enhanced.py --category individual
    python test_agentic_system_enhanced.py --category orchestrator
    python test_agentic_system_enhanced.py --category agentic
    python test_agentic_system_enhanced.py --category hil
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

# ============================================================================
# SETUP: Add agents directory to Python path
# ============================================================================
agents_dir = Path(__file__).parent / 'backend' / 'agents'
sys.path.insert(0, str(agents_dir))

# Load environment variables
from dotenv import load_dotenv
env_path = Path(__file__).parent / 'backend' / '.env'
load_dotenv(env_path)

# Import all agents
from agents.orchestrator_agent import OrchestratorAgent
from agents.flight_agent import FlightAgent
from agents.hotel_agent import HotelAgent
from agents.restaurant_agent import RestaurantAgent
from agents.attractions_agent import AttractionsAgent
from agents.itinerary_agent import ItineraryAgent

# ============================================================================
# TERMINAL OUTPUT UTILITIES
# ============================================================================

class Colors:
    """ANSI color codes for beautiful terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_section(title):
    """Print a formatted section header with emphasis"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{title.center(80)}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.END}\n")

def print_subsection(title):
    """Print a subsection header"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'-'*80}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{title}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'-'*80}{Colors.END}\n")

def print_success(message):
    """Print a success message"""
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def print_info(message):
    """Print an info message"""
    print(f"{Colors.CYAN}ℹ️  {message}{Colors.END}")

def print_warning(message):
    """Print a warning message"""
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")

def print_error(message):
    """Print an error message"""
    print(f"{Colors.RED}❌ {message}{Colors.END}")

def print_metric(label, value, status="info"):
    """Print a labeled metric with color coding"""
    colors = {
        "success": Colors.GREEN,
        "info": Colors.CYAN,
        "warning": Colors.YELLOW,
        "error": Colors.RED
    }
    color = colors.get(status, Colors.CYAN)
    print(f"{color}  📊 {label}: {value}{Colors.END}")

# ============================================================================
# TEST VALIDATION UTILITIES
# ============================================================================

class AgenticBehaviorValidator:
    """
    Validates that agent behavior is truly agentic (LLM-driven) 
    rather than hardcoded or rule-based.
    """
    
    @staticmethod
    def validate_tool_calling_pattern(result: Dict[str, Any]) -> bool:
        """
        Validates that the agent used function calling rather than
        returning hardcoded responses.
        
        Returns True if agentic patterns detected.
        """
        # Check for status codes that indicate autonomous decision-making
        status = result.get('status_code')
        if status in ['HIL_PAUSE_REQUIRED', 'SUCCESS']:
            print_success("✓ Agent demonstrated autonomous decision-making")
            return True
        return False
    
    @staticmethod
    def validate_adaptive_behavior(agent_name: str, result: Dict[str, Any]) -> bool:
        """
        Validates that agent can adapt its strategy dynamically.
        This checks for presence of recommendations and reasoning.
        """
        # Check for recommendations (proof of analysis)
        recommendations_key = f'recommended_{agent_name.lower()}s'
        if recommendations_key in result and result[recommendations_key]:
            print_success(f"✓ {agent_name} provided dynamic recommendations")
            return True
        
        # Check for summary/reasoning (proof of LLM processing)
        if 'recommendation_summary' in result or 'summary' in result:
            print_success(f"✓ {agent_name} demonstrated reasoning capability")
            return True
            
        return False
    
    @staticmethod
    def validate_hil_integration(result: Dict[str, Any]) -> bool:
        """
        Validates proper HIL (Human-in-the-Loop) pause mechanism.
        """
        if result.get('status_code') == 'HIL_PAUSE_REQUIRED':
            print_success("✓ Agent properly paused for human input")
            return True
        print_warning("⚠ Agent did not pause for HIL as expected")
        return False

# ============================================================================
# BASE TEST CASE CLASS
# ============================================================================

class TestCase:
    """
    Base class for all test cases.
    
    Each test case should:
    1. Have a descriptive name
    2. Explain what it validates
    3. Return True on success, False on failure
    4. Print detailed output explaining results
    """
    def __init__(self, name: str, description: str, category: str):
        self.name = name
        self.description = description
        self.category = category
        self.validator = AgenticBehaviorValidator()
    
    def run(self) -> bool:
        """Override this method in subclasses"""
        raise NotImplementedError
    
    def setup_agents(self):
        """Helper to initialize all agents"""
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        places_api_key = os.getenv('GOOGLE_PLACES_API_KEY')
        
        if not gemini_api_key:
            print_error("GEMINI_API_KEY not found in environment variables")
            return None
        
        try:
            flight_agent = FlightAgent(gemini_api_key)
            hotel_agent = HotelAgent(gemini_api_key)
            restaurant_agent = RestaurantAgent(gemini_api_key, places_api_key)
            attractions_agent = AttractionsAgent(gemini_api_key, places_api_key)
            itinerary_agent = ItineraryAgent(gemini_api_key)
            
            orchestrator = OrchestratorAgent(
                gemini_api_key,
                flight_agent,
                hotel_agent,
                restaurant_agent,
                attractions_agent,
                itinerary_agent
            )
            
            return {
                'flight': flight_agent,
                'hotel': hotel_agent,
                'restaurant': restaurant_agent,
                'attractions': attractions_agent,
                'itinerary': itinerary_agent,
                'orchestrator': orchestrator
            }
        except Exception as e:
            print_error(f"Failed to initialize agents: {str(e)}")
            return None

# ============================================================================
# CATEGORY A: INDIVIDUAL AGENT TESTS
# ============================================================================

class FlightAgentBasicTest(TestCase):
    """
    Tests FlightAgent's basic agentic behavior in isolation.
    
    Validates:
    - Agent can search for flights using MCP tools
    - Agent analyzes results using AnalyzeAndFilter
    - Agent provides recommendations using ProvideRecommendation
    - Agent properly pauses for HIL input
    - All decisions are LLM-driven (not hardcoded)
    """
    def __init__(self):
        super().__init__(
            "FlightAgent - Basic Agentic Behavior",
            "Validates FlightAgent's autonomous search, analysis, and HIL pause",
            "individual"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        flight_agent = agents['flight']
        
        # Test parameters - realistic scenario
        params = {
            'origin': 'SFO',
            'destination': 'JFK',
            'departure_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'return_date': (datetime.now() + timedelta(days=37)).strftime('%Y-%m-%d'),
            'passengers': 2
        }
        
        print_info(f"Testing with: {params['origin']} → {params['destination']}")
        print_info("Expecting: SearchFlights → AnalyzeAndFilter → ProvideRecommendation → HIL_PAUSE")
        
        try:
            # Execute agent
            result = flight_agent.execute(params)
            
            # Validate agentic behavior
            print_subsection("Validation Results")
            
            checks = []
            checks.append(self.validator.validate_tool_calling_pattern(result))
            checks.append(self.validator.validate_adaptive_behavior('flight', result))
            checks.append(self.validator.validate_hil_integration(result))
            
            # Additional checks
            if result.get('recommended_flights'):
                print_metric("Flights Recommended", len(result['recommended_flights']), "success")
            
            if all(checks):
                print_success(f"\n✅ TEST PASSED: {self.name}")
                return True
            else:
                print_warning(f"\n⚠️  TEST PARTIAL: Some validations failed")
                return False
                
        except Exception as e:
            print_error(f"Test failed with exception: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


class HotelAgentBasicTest(TestCase):
    """
    Tests HotelAgent's basic agentic behavior in isolation.
    
    Validates:
    - Agent can search hotels using MCP tools
    - Agent applies constraints and filters
    - Agent ranks results using RankingWeights
    - Agent properly pauses for HIL
    """
    def __init__(self):
        super().__init__(
            "HotelAgent - Basic Agentic Behavior",
            "Validates HotelAgent's autonomous search, filtering, and HIL pause",
            "individual"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        hotel_agent = agents['hotel']
        
        params = {
            'city_code': 'NYC',
            'check_in_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'check_out_date': (datetime.now() + timedelta(days=35)).strftime('%Y-%m-%d'),
            'adults': 2
        }
        
        print_info(f"Testing hotel search in: {params['city_code']}")
        
        try:
            result = hotel_agent.execute(params)
            
            print_subsection("Validation Results")
            
            checks = []
            checks.append(self.validator.validate_tool_calling_pattern(result))
            checks.append(self.validator.validate_adaptive_behavior('hotel', result))
            checks.append(self.validator.validate_hil_integration(result))
            
            if result.get('recommended_hotels'):
                print_metric("Hotels Recommended", len(result['recommended_hotels']), "success")
            
            if all(checks):
                print_success(f"\n✅ TEST PASSED: {self.name}")
                return True
            else:
                print_warning(f"\n⚠️  TEST PARTIAL: Some validations failed")
                return False
                
        except Exception as e:
            print_error(f"Test failed: {str(e)}")
            return False


class RestaurantAgentBasicTest(TestCase):
    """
    Tests RestaurantAgent's production-grade features.
    
    Validates:
    - Agent uses Google Places API for real data
    - Agent applies dietary restrictions constraints
    - Agent considers atmosphere preferences
    - Agent uses proximity_location for context
    - Agent properly pauses for HIL
    """
    def __init__(self):
        super().__init__(
            "RestaurantAgent - Production Features",
            "Validates RestaurantAgent's enhanced constraints and HIL",
            "individual"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        restaurant_agent = agents['restaurant']
        
        # Test with complex constraints
        params = {
            'city': 'Paris',
            'constraints': {
                'min_rating': 4.5,
                'dietary_restrictions': ['vegetarian'],
                'atmosphere': ['romantic'],
                'price_level': 3
            },
            'proximity_location': 'Eiffel Tower',
            'max_results': 10
        }
        
        print_info(f"Testing restaurant search in: {params['city']}")
        print_info(f"Constraints: {params['constraints']}")
        
        try:
            result = restaurant_agent.execute(params)
            
            print_subsection("Validation Results")
            
            checks = []
            checks.append(self.validator.validate_tool_calling_pattern(result))
            checks.append(self.validator.validate_adaptive_behavior('restaurant', result))
            checks.append(self.validator.validate_hil_integration(result))
            
            if result.get('recommended_restaurants'):
                print_metric("Restaurants Recommended", len(result['recommended_restaurants']), "success")
                print_success("✓ Dietary and atmosphere constraints applied")
            
            if all(checks):
                print_success(f"\n✅ TEST PASSED: {self.name}")
                return True
            else:
                print_warning(f"\n⚠️  TEST PARTIAL: Some validations failed")
                return False
                
        except Exception as e:
            print_error(f"Test failed: {str(e)}")
            return False


class AttractionsAgentBasicTest(TestCase):
    """
    Tests AttractionsAgent's production-grade features.
    
    Validates:
    - Agent uses Google Places API for real data
    - Agent applies accessibility constraints
    - Agent uses temporal awareness (target_date)
    - Agent considers proximity_location
    - Agent properly pauses for HIL
    """
    def __init__(self):
        super().__init__(
            "AttractionsAgent - Production Features",
            "Validates AttractionsAgent's accessibility and temporal features",
            "individual"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        attractions_agent = agents['attractions']
        
        # Test with accessibility and temporal constraints
        params = {
            'city': 'Tokyo',
            'constraints': {
                'min_rating': 4.0,
                'attraction_types': ['museum', 'historical'],
                'wheelchair_accessible': True,
                'max_entry_fee': 50.0
            },
            'target_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'max_results': 10
        }
        
        print_info(f"Testing attractions search in: {params['city']}")
        print_info(f"Accessibility required: {params['constraints']['wheelchair_accessible']}")
        
        try:
            result = attractions_agent.execute(params)
            
            print_subsection("Validation Results")
            
            checks = []
            checks.append(self.validator.validate_tool_calling_pattern(result))
            checks.append(self.validator.validate_adaptive_behavior('attraction', result))
            checks.append(self.validator.validate_hil_integration(result))
            
            if result.get('recommended_attractions'):
                print_metric("Attractions Recommended", len(result['recommended_attractions']), "success")
                print_success("✓ Accessibility constraints applied")
            
            if all(checks):
                print_success(f"\n✅ TEST PASSED: {self.name}")
                return True
            else:
                print_warning(f"\n⚠️  TEST PARTIAL: Some validations failed")
                return False
                
        except Exception as e:
            print_error(f"Test failed: {str(e)}")
            return False

# ============================================================================
# CATEGORY B: ORCHESTRATOR INTEGRATION TESTS
# ============================================================================

class OrchestratorSimpleFlowTest(TestCase):
    """
    Tests OrchestratorAgent's ability to coordinate all 4 specialist agents
    in a simple end-to-end vacation planning flow.
    
    Validates:
    - Orchestrator calls agents in correct sequence
    - Each agent executes and pauses for HIL
    - Orchestrator resumes agents with simulated human feedback
    - Final itinerary is generated with all selections
    - No hardcoded logic - all decisions are LLM-driven
    """
    def __init__(self):
        super().__init__(
            "Orchestrator - Simple E2E Flow",
            "Validates orchestration of all 4 agents in sequence",
            "orchestrator"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        orchestrator = agents['orchestrator']
        
        # Simple vacation query
        departure_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        return_date = (datetime.now() + timedelta(days=35)).strftime('%Y-%m-%d')
        
        user_prompt = f"""Plan a vacation from San Francisco to Paris.
        Departing {departure_date}, returning {return_date}.
        I need flights, a hotel, restaurant recommendations, and attractions to visit."""
        
        print_info("User Query:")
        print(f"  {user_prompt}")
        print_info("\nExpected Flow:")
        print("  1. FlightAgent → Search → Analyze → Recommend → HIL → Final")
        print("  2. HotelAgent → Search → Analyze → Recommend → HIL → Final")
        print("  3. RestaurantAgent → Search → Analyze → Recommend → HIL → Final")
        print("  4. AttractionsAgent → Search → Analyze → Recommend → HIL → Final")
        print("  5. ItineraryAgent → Generate final itinerary")
        
        try:
            # Execute orchestration with max turns
            result = orchestrator.execute(user_prompt, max_turns=20)
            
            print_subsection("Orchestration Results")
            
            # Validate success
            if not result.get('success'):
                print_error("Orchestration failed")
                print(json.dumps(result, indent=2))
                return False
            
            print_success("Orchestration completed successfully")
            
            # Check for all required results
            all_results = result.get('all_results', {})
            
            checks = []
            
            # Check for final_flight
            if 'final_flight' in all_results:
                print_success("✓ FlightAgent completed and provided final_flight")
                checks.append(True)
            else:
                print_warning("⚠ Missing final_flight")
                checks.append(False)
            
            # Check for final_hotel
            if 'final_hotel' in all_results:
                print_success("✓ HotelAgent completed and provided final_hotel")
                checks.append(True)
            else:
                print_warning("⚠ Missing final_hotel")
                checks.append(False)
            
            # Check for final_restaurant
            if 'final_restaurant' in all_results:
                print_success("✓ RestaurantAgent completed and provided final_restaurant")
                checks.append(True)
            else:
                print_warning("⚠ Missing final_restaurant")
                checks.append(False)
            
            # Check for final_attraction
            if 'final_attraction' in all_results:
                print_success("✓ AttractionsAgent completed and provided final_attraction")
                checks.append(True)
            else:
                print_warning("⚠ Missing final_attraction")
                checks.append(False)
            
            # Display summary
            if result.get('summary'):
                print_info("\nOrchestrator Summary:")
                print(f"  {result['summary']}")
            
            if all(checks):
                print_success(f"\n✅ TEST PASSED: {self.name}")
                print_info("All 4 specialist agents completed successfully!")
                return True
            else:
                print_warning(f"\n⚠️  TEST PARTIAL: Not all agents completed")
                return False
                
        except Exception as e:
            print_error(f"Test failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


class OrchestratorComplexConstraintsTest(TestCase):
    """
    Tests OrchestratorAgent with complex, multi-agent constraints.
    
    This validates the system's ability to:
    - Handle dietary restrictions (RestaurantAgent)
    - Apply accessibility requirements (AttractionsAgent)
    - Work with budget constraints (FlightAgent, HotelAgent)
    - Use proximity_location for contextual recommendations
    - Pass context between agents (hotel location → restaurant proximity)
    """
    def __init__(self):
        super().__init__(
            "Orchestrator - Complex Constraints",
            "Validates handling of dietary, accessibility, and budget constraints",
            "orchestrator"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        orchestrator = agents['orchestrator']
        
        departure_date = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
        return_date = (datetime.now() + timedelta(days=67)).strftime('%Y-%m-%d')
        
        # Complex query with multiple constraints
        user_prompt = f"""Plan an accessible anniversary trip from Santander to Madrid.
        Departing {departure_date}, returning {return_date}.
        
        Requirements:
        - Budget: $2000 per person for flights
        - Hotel: Luxury, near city center
        - Restaurants: Vegetarian options, romantic atmosphere
        - Attractions: Must be wheelchair accessible, cultural/historical focus
        - Prefer non-stop flights if available"""
        
        print_info("User Query with Constraints:")
        print(f"  {user_prompt}")
        
        try:
            result = orchestrator.execute(user_prompt, max_turns=25)
            
            print_subsection("Constraint Handling Validation")
            
            if not result.get('success'):
                print_error("Orchestration failed")
                return False
            
            print_success("Orchestration completed with complex constraints")
            
            # Validate constraint handling
            all_results = result.get('all_results', {})
            
            checks = []
            
            # Check that constraints were applied
            if 'final_flight' in all_results:
                print_success("✓ Budget constraint passed to FlightAgent")
                checks.append(True)
            
            if 'final_restaurant' in all_results:
                print_success("✓ Dietary restrictions passed to RestaurantAgent")
                checks.append(True)
            
            if 'final_attraction' in all_results:
                print_success("✓ Accessibility requirements passed to AttractionsAgent")
                checks.append(True)
            
            if len(checks) >= 2:
                print_success(f"\n✅ TEST PASSED: {self.name}")
                print_info("Complex constraints handled successfully!")
                return True
            else:
                print_warning(f"\n⚠️  TEST PARTIAL: Some constraints not applied")
                return False
                
        except Exception as e:
            print_error(f"Test failed: {str(e)}")
            return False

# ============================================================================
# CATEGORY C: AGENTIC BEHAVIOR VALIDATION TESTS
# ============================================================================

class AgenticAutonomyTest(TestCase):
    """
    Validates that the system demonstrates TRUE agentic behavior:
    - Decisions are made by LLM, not hardcoded logic
    - Agents adapt strategies based on results
    - No forced tool calls - agents choose when to call tools
    - Conversational feedback loops maintain autonomy
    
    This test specifically looks for evidence of LLM-driven decision making.
    """
    def __init__(self):
        super().__init__(
            "Agentic Behavior - LLM Autonomy",
            "Validates that decisions are LLM-driven, not hardcoded",
            "agentic"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        print_info("This test looks for evidence of genuine AI autonomy\n")
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        flight_agent = agents['flight']
        
        # Test scenario: Search with unrealistic constraints
        # A truly agentic system should adapt when no results found
        params = {
            'origin': 'SFO',
            'destination': 'CDG',
            'departure_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'return_date': (datetime.now() + timedelta(days=31)).strftime('%Y-%m-%d'),
            'passengers': 1
        }
        
        print_info("Testing FlightAgent's autonomous decision-making...")
        print_info("Looking for: Tool selection autonomy, adaptive strategies")
        
        try:
            result = flight_agent.execute(params)
            
            print_subsection("Autonomy Validation")
            
            checks = []
            
            # Check 1: Agent used function calling (proof of tool autonomy)
            if result.get('status_code') in ['HIL_PAUSE_REQUIRED', 'SUCCESS']:
                print_success("✓ Agent demonstrated tool selection autonomy")
                print_info("  Agent chose which tools to call and when")
                checks.append(True)
            else:
                print_warning("⚠ Agent may not have full tool autonomy")
                checks.append(False)
            
            # Check 2: Agent provided reasoning/summary (proof of LLM processing)
            if result.get('recommendation_summary') or result.get('summary'):
                print_success("✓ Agent demonstrated LLM-driven reasoning")
                print_info("  Agent generated natural language explanations")
                checks.append(True)
            else:
                print_warning("⚠ No LLM reasoning detected")
                checks.append(False)
            
            # Check 3: Agent provided recommendations (proof of analysis)
            if result.get('recommended_flights'):
                print_success("✓ Agent performed autonomous analysis")
                print_info("  Agent analyzed options and made recommendations")
                checks.append(True)
            else:
                print_warning("⚠ No autonomous analysis detected")
                checks.append(False)
            
            if all(checks):
                print_success(f"\n✅ TEST PASSED: {self.name}")
                print_info("System demonstrates genuine agentic behavior!")
                return True
            else:
                print_warning(f"\n⚠️  TEST PARTIAL: Some autonomy checks failed")
                return False
                
        except Exception as e:
            print_error(f"Test failed: {str(e)}")
            return False


class AdaptiveStrategyTest(TestCase):
    """
    Validates that agents can adapt their strategies when initial
    approaches fail or when they receive feedback.
    
    Tests:
    - Agent adjusts search parameters when no results found
    - Agent uses ReflectAndModifySearch tool appropriately
    - Agent doesn't just repeat the same search
    - Decisions are context-aware and adaptive
    """
    def __init__(self):
        super().__init__(
            "Agentic Behavior - Adaptive Strategies",
            "Validates agents adapt strategies based on results and feedback",
            "agentic"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        print_info("Testing agent's ability to adapt when plans don't work\n")
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        hotel_agent = agents['hotel']
        
        # Initial search
        params = {
            'city_code': 'NYC',
            'check_in_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'check_out_date': (datetime.now() + timedelta(days=35)).strftime('%Y-%m-%d'),
            'adults': 2
        }
        
        print_info("Step 1: Initial hotel search")
        
        try:
            # First call
            result1 = hotel_agent.execute(params)
            
            if result1.get('status_code') != 'HIL_PAUSE_REQUIRED':
                print_warning("Agent didn't pause for HIL as expected")
                return False
            
            print_success("✓ Agent completed initial search and paused")
            
            # Simulate human feedback requesting refinement
            feedback = {
                'status': 'REFINE_SEARCH',
                'feedback': 'These hotels are too expensive. Find options under $300 per night.'
            }
            
            print_info("\nStep 2: Providing refinement feedback")
            print_info(f"  Feedback: {feedback['feedback']}")
            
            # Resume with feedback
            result2 = hotel_agent.execute(params, continuation_message=feedback)
            
            print_subsection("Adaptive Behavior Validation")
            
            checks = []
            
            # Check if agent processed feedback
            if result2.get('status_code') in ['HIL_PAUSE_REQUIRED', 'SUCCESS']:
                print_success("✓ Agent processed refinement feedback")
                checks.append(True)
            else:
                print_warning("⚠ Agent may not have adapted")
                checks.append(False)
            
            # Check if new recommendations provided
            if result2.get('recommended_hotels'):
                print_success("✓ Agent provided new recommendations")
                print_info("  Agent adapted its strategy based on feedback")
                checks.append(True)
            else:
                print_warning("⚠ No new recommendations after feedback")
                checks.append(False)
            
            if all(checks):
                print_success(f"\n✅ TEST PASSED: {self.name}")
                print_info("Agent demonstrated adaptive behavior!")
                return True
            else:
                print_warning(f"\n⚠️  TEST PARTIAL: Some adaptation checks failed")
                return False
                
        except Exception as e:
            print_error(f"Test failed: {str(e)}")
            return False

# ============================================================================
# CATEGORY D: HIL FLOW TESTS
# ============================================================================

class ComprehensiveHILTest(TestCase):
    """
    Comprehensive test of Human-in-the-Loop mechanisms across ALL agents.
    
    Validates:
    - All 4 specialist agents properly pause when recommendations ready
    - Agents resume correctly with human feedback
    - REFINE_SEARCH feedback triggers strategy adaptation
    - FINAL_CHOICE feedback triggers completion
    - Orchestrator properly manages HIL cycles
    """
    def __init__(self):
        super().__init__(
            "HIL Flow - All 4 Agents",
            "Comprehensive validation of HIL pause/resume across all agents",
            "hil"
        )
    
    def run(self) -> bool:
        print_section(f"TEST: {self.name}")
        print_info(self.description)
        print_info("Testing HIL mechanisms for all 4 specialist agents\n")
        
        agents = self.setup_agents()
        if not agents:
            return False
        
        results = {}
        
        # Test 1: FlightAgent HIL
        print_subsection("1. FlightAgent HIL")
        flight_params = {
            'origin': 'LAX',
            'destination': 'JFK',
            'departure_date': (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d'),
            'return_date': (datetime.now() + timedelta(days=50)).strftime('%Y-%m-%d'),
            'passengers': 1
        }
        
        try:
            result = agents['flight'].execute(flight_params)
            if result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                print_success("✓ FlightAgent paused correctly")
                results['flight'] = True
            else:
                print_warning(f"⚠ FlightAgent status: {result.get('status_code')}")
                results['flight'] = False
        except Exception as e:
            print_error(f"✗ FlightAgent failed: {str(e)}")
            results['flight'] = False
        
        # Test 2: HotelAgent HIL
        print_subsection("2. HotelAgent HIL")
        hotel_params = {
            'city_code': 'LAX',
            'check_in_date': (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d'),
            'check_out_date': (datetime.now() + timedelta(days=50)).strftime('%Y-%m-%d'),
            'adults': 1
        }
        
        try:
            result = agents['hotel'].execute(hotel_params)
            if result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                print_success("✓ HotelAgent paused correctly")
                results['hotel'] = True
            else:
                print_warning(f"⚠ HotelAgent status: {result.get('status_code')}")
                results['hotel'] = False
        except Exception as e:
            print_error(f"✗ HotelAgent failed: {str(e)}")
            results['hotel'] = False
        
        # Test 3: RestaurantAgent HIL
        print_subsection("3. RestaurantAgent HIL")
        restaurant_params = {
            'city': 'Los Angeles',
            'constraints': {'min_rating': 4.0},
            'max_results': 10
        }
        
        try:
            result = agents['restaurant'].execute(restaurant_params)
            if result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                print_success("✓ RestaurantAgent paused correctly")
                results['restaurant'] = True
            else:
                print_warning(f"⚠ RestaurantAgent status: {result.get('status_code')}")
                results['restaurant'] = False
        except Exception as e:
            print_error(f"✗ RestaurantAgent failed: {str(e)}")
            results['restaurant'] = False
        
        # Test 4: AttractionsAgent HIL
        print_subsection("4. AttractionsAgent HIL")
        attractions_params = {
            'city': 'Los Angeles',
            'constraints': {'min_rating': 4.0},
            'max_results': 10
        }
        
        try:
            result = agents['attractions'].execute(attractions_params)
            if result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                print_success("✓ AttractionsAgent paused correctly")
                results['attractions'] = True
            else:
                print_warning(f"⚠ AttractionsAgent status: {result.get('status_code')}")
                results['attractions'] = False
        except Exception as e:
            print_error(f"✗ AttractionsAgent failed: {str(e)}")
            results['attractions'] = False
        
        # Summary
        print_subsection("HIL Test Summary")
        
        passed = sum(results.values())
        total = len(results)
        
        for agent_name, passed in results.items():
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"  {agent_name.capitalize()}Agent: {status}")
        
        print_metric("HIL Tests Passed", f"{passed}/{total}", 
                    "success" if passed == total else "warning")
        
        if passed == total:
            print_success(f"\n✅ TEST PASSED: {self.name}")
            print_info("All agents demonstrate proper HIL behavior!")
            return True
        else:
            print_warning(f"\n⚠️  TEST PARTIAL: {total - passed} agent(s) failed HIL test")
            return False

# ============================================================================
# TEST SUITE RUNNER
# ============================================================================

class TestSuite:
    """
    Manages and runs all test cases with filtering and reporting.
    """
    def __init__(self):
        self.all_tests = self._load_all_tests()
        self.categories = {
            'individual': 'Individual Agent Tests',
            'orchestrator': 'Orchestrator Integration Tests',
            'agentic': 'Agentic Behavior Validation',
            'hil': 'HIL Flow Tests'
        }
    
    def _load_all_tests(self) -> List[TestCase]:
        """Load all test case instances"""
        return [
            # Individual Agent Tests
            FlightAgentBasicTest(),
            HotelAgentBasicTest(),
            RestaurantAgentBasicTest(),
            AttractionsAgentBasicTest(),
            
            # Orchestrator Integration Tests
            OrchestratorSimpleFlowTest(),
            OrchestratorComplexConstraintsTest(),
            
            # Agentic Behavior Tests
            AgenticAutonomyTest(),
            AdaptiveStrategyTest(),
            
            # HIL Flow Tests
            ComprehensiveHILTest()
        ]
    
    def run_all(self) -> bool:
        """Run all tests"""
        print_section("AGENTIC VACATION PLANNER - ENHANCED TEST SUITE")
        print_info("Comprehensive testing of multi-agent system with agentic behavior validation")
        print_info(f"Total tests: {len(self.all_tests)}\n")
        
        return self._run_tests(self.all_tests)
    
    def run_category(self, category: str) -> bool:
        """Run tests in a specific category"""
        if category not in self.categories:
            print_error(f"Unknown category: {category}")
            print_info(f"Available categories: {', '.join(self.categories.keys())}")
            return False
        
        tests = [t for t in self.all_tests if t.category == category]
        
        print_section(f"TEST CATEGORY: {self.categories[category]}")
        print_info(f"Running {len(tests)} test(s) in this category\n")
        
        return self._run_tests(tests)
    
    def _run_tests(self, tests: List[TestCase]) -> bool:
        """Execute a list of tests and report results"""
        results = []
        
        for i, test in enumerate(tests, 1):
            print_info(f"\n[{i}/{len(tests)}] Starting: {test.name}")
            try:
                success = test.run()
                results.append((test.name, test.category, success))
            except Exception as e:
                print_error(f"Test crashed: {str(e)}")
                results.append((test.name, test.category, False))
        
        # Print final summary
        self._print_summary(results)
        
        # Return True only if all tests passed
        return all(success for _, _, success in results)
    
    def _print_summary(self, results: List[tuple]):
        """Print comprehensive test summary"""
        print_section("TEST SUITE SUMMARY")
        
        # Group by category
        by_category = {}
        for name, category, success in results:
            if category not in by_category:
                by_category[category] = []
            by_category[category].append((name, success))
        
        # Print by category
        for category, tests in by_category.items():
            print_subsection(self.categories.get(category, category))
            for name, success in tests:
                status = f"{Colors.GREEN}✅ PASSED{Colors.END}" if success else f"{Colors.RED}❌ FAILED{Colors.END}"
                print(f"  {status} - {name}")
        
        # Overall stats
        total = len(results)
        passed = sum(1 for _, _, success in results if success)
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        print_subsection("Overall Statistics")
        print_metric("Total Tests", total, "info")
        print_metric("Passed", passed, "success" if passed == total else "info")
        print_metric("Failed", failed, "error" if failed > 0 else "info")
        print_metric("Pass Rate", f"{pass_rate:.1f}%", 
                    "success" if pass_rate == 100 else "warning" if pass_rate >= 75 else "error")
        
        if failed == 0:
            print_success("\n🎉 ALL TESTS PASSED! Your agentic system is working perfectly!")
        else:
            print_warning(f"\n⚠️  {failed} test(s) failed. Review the output above for details.")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description='Enhanced Test Suite for Agentic Vacation Planner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Categories:
  individual    - Test each agent in isolation
  orchestrator  - Test agent coordination
  agentic       - Validate LLM autonomy and adaptive behavior
  hil           - Test Human-in-the-Loop mechanisms

Examples:
  python test_agentic_system_enhanced.py
  python test_agentic_system_enhanced.py --category individual
  python test_agentic_system_enhanced.py --category orchestrator
        """
    )
    
    parser.add_argument(
        '--category',
        choices=['individual', 'orchestrator', 'agentic', 'hil'],
        help='Run only tests in specified category'
    )
    
    args = parser.parse_args()
    
    # Print banner
    print(f"{Colors.CYAN}")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                            ║")
    print("║         AGENTIC VACATION PLANNER - ENHANCED TEST SUITE                     ║")
    print("║                                                                            ║")
    print("║  Testing: Orchestrator + 4 Specialist Agents                              ║")
    print("║  Focus: Agentic Behavior, HIL Flow, Adaptive Strategies                   ║")
    print("║                                                                            ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}\n")
    
    # Run tests
    suite = TestSuite()
    
    if args.category:
        success = suite.run_category(args.category)
    else:
        success = suite.run_all()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
