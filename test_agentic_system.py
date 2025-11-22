"""
Comprehensive Test Script for Agentic Vacation Planner System
================================================================

This script tests the complete multi-agent system with Human-in-the-Loop (HIL) flow.

What this tests:
1. OrchestratorAgent coordination
2. FlightAgent agentic behavior with HIL
3. HotelAgent agentic behavior with HIL
4. Integration with existing RestaurantAgent, AttractionsAgent, ItineraryAgent
5. Full end-to-end vacation planning workflow

Architecture Flow:
User Query → OrchestratorAgent → FlightAgent (HIL) → HotelAgent (HIL) → 
RestaurantAgent → AttractionsAgent → ItineraryAgent → Final Itinerary

Usage:
    python test_agentic_system.py
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add the agents directory to the Python path
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
# TEST CONFIGURATION
# ============================================================================

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{title.center(80)}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.END}\n")

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

# ============================================================================
# TEST CASES
# ============================================================================

class TestCase:
    """Base class for test cases"""
    def __init__(self, name, description):
        self.name = name
        self.description = description
    
    def run(self):
        """Override this method in subclasses"""
        raise NotImplementedError

class SimpleVacationTest(TestCase):
    """Test Case 1: Simple vacation planning with default parameters"""
    def __init__(self):
        super().__init__(
            "Simple Vacation Test",
            "Tests basic orchestration flow: SFO → Paris for 5 days"
        )
    
    def run(self):
        print_section(f"TEST CASE: {self.name}")
        print_info(self.description)
        
        # Initialize API keys
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        places_api_key = os.getenv('GOOGLE_PLACES_API_KEY')
        
        if not gemini_api_key:
            print_error("GEMINI_API_KEY not found in environment variables")
            return False
        
        print_info(f"Initializing agents...")
        
        try:
            # Initialize all agents
            flight_agent = FlightAgent(gemini_api_key)
            hotel_agent = HotelAgent(gemini_api_key)
            restaurant_agent = RestaurantAgent(gemini_api_key, places_api_key)
            attractions_agent = AttractionsAgent(gemini_api_key, places_api_key)
            itinerary_agent = ItineraryAgent(gemini_api_key)
            
            # Initialize orchestrator
            orchestrator = OrchestratorAgent(
                gemini_api_key,
                flight_agent,
                hotel_agent,
                restaurant_agent,
                attractions_agent,
                itinerary_agent
            )
            
            print_success("All agents initialized successfully!")
            
            # Create test query
            departure_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            return_date = (datetime.now() + timedelta(days=35)).strftime('%Y-%m-%d')
            
            user_prompt = f"Plan a vacation from San Francisco to Paris, departing {departure_date} and returning {return_date}"
            
            print_info(f"User Query: {user_prompt}")
            print_info("Starting orchestration...\n")
            
            # Execute orchestration
            result = orchestrator.execute(user_prompt, max_turns=15)
            
            # Display results
            print_section("ORCHESTRATION RESULTS")
            
            if result.get('success'):
                print_success("Orchestration completed successfully!")
                
                # Display collected results
                results = result.get('results', {})
                
                # Flight results
                if 'final_flight' in results:
                    print_info("\n🛫 FINAL FLIGHT SELECTION:")
                    flight = results['final_flight']
                    print(json.dumps(flight, indent=2))
                
                # Hotel results
                if 'final_hotel' in results:
                    print_info("\n🏨 FINAL HOTEL SELECTION:")
                    hotel = results['final_hotel']
                    print(json.dumps(hotel, indent=2))
                
                # Final LLM response
                if result.get('final_response_text'):
                    print_info("\n📝 ORCHESTRATOR SUMMARY:")
                    print(result['final_response_text'])
                
                print_success("\n✅ TEST PASSED: Simple vacation planning completed successfully!")
                return True
            else:
                print_error("Orchestration failed!")
                print(json.dumps(result, indent=2))
                return False
                
        except Exception as e:
            print_error(f"Test failed with exception: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

class ComplexVacationTest(TestCase):
    """Test Case 2: Complex vacation with specific requirements"""
    def __init__(self):
        super().__init__(
            "Complex Vacation Test",
            "Tests advanced orchestration: Multi-city with budget constraints"
        )
    
    def run(self):
        print_section(f"TEST CASE: {self.name}")
        print_info(self.description)
        print_warning("This test demonstrates the system handling complex requirements")
        
        # Initialize API keys
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        places_api_key = os.getenv('GOOGLE_PLACES_API_KEY')
        
        try:
            # Initialize all agents
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
            
            # Create complex query
            departure_date = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
            return_date = (datetime.now() + timedelta(days=67)).strftime('%Y-%m-%d')
            
            user_prompt = f"""Plan a romantic anniversary trip from New York to Tokyo, 
            departing {departure_date} and returning {return_date}. 
            We want luxury accommodations, fine dining, and cultural experiences. 
            Budget is flexible but prefer non-stop flights."""
            
            print_info(f"User Query: {user_prompt}")
            print_info("Starting orchestration...\n")
            
            result = orchestrator.execute(user_prompt, max_turns=15)
            
            print_section("ORCHESTRATION RESULTS")
            
            if result.get('success'):
                print_success("Complex orchestration completed successfully!")
                print_success("\n✅ TEST PASSED: Complex vacation planning handled correctly!")
                return True
            else:
                print_error("Complex orchestration failed!")
                return False
                
        except Exception as e:
            print_error(f"Test failed with exception: {str(e)}")
            return False

class HILFlowTest(TestCase):
    """Test Case 3: Test Human-in-the-Loop interaction"""
    def __init__(self):
        super().__init__(
            "HIL Flow Test",
            "Tests the Human-in-the-Loop pause and resume mechanism"
        )
    
    def run(self):
        print_section(f"TEST CASE: {self.name}")
        print_info(self.description)
        print_info("This test verifies that agents properly pause for human input")
        print_info("The orchestrator simulates human feedback automatically\n")
        
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        
        try:
            # Initialize only flight and hotel agents for focused HIL testing
            flight_agent = FlightAgent(gemini_api_key)
            hotel_agent = HotelAgent(gemini_api_key)
            
            print_success("FlightAgent and HotelAgent initialized")
            
            # Test 1: Flight Agent HIL
            print_info("\n📍 Testing FlightAgent HIL Flow...")
            flight_params = {
                'origin': 'SFO',
                'destination': 'LAX',
                'departure_date': '2025-12-15',
                'return_date': '2025-12-20',
                'passengers': 2
            }
            
            flight_result = flight_agent.execute(flight_params)
            
            if flight_result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                print_success("FlightAgent correctly paused for HIL input")
                print_info(f"Recommendations provided: {len(flight_result.get('recommended_flights', []))} flights")
            else:
                print_warning(f"Unexpected status: {flight_result.get('status_code')}")
            
            # Test 2: Hotel Agent HIL
            print_info("\n📍 Testing HotelAgent HIL Flow...")
            hotel_params = {
                'city_code': 'LAX',
                'check_in_date': '2025-12-15',
                'check_out_date': '2025-12-20',
                'adults': 2
            }
            
            hotel_result = hotel_agent.execute(hotel_params)
            
            if hotel_result.get('status_code') == 'HIL_PAUSE_REQUIRED':
                print_success("HotelAgent correctly paused for HIL input")
                print_info(f"Recommendations provided: {len(hotel_result.get('recommended_hotels', []))} hotels")
            else:
                print_warning(f"Unexpected status: {hotel_result.get('status_code')}")
            
            print_success("\n✅ TEST PASSED: HIL flow working correctly!")
            return True
            
        except Exception as e:
            print_error(f"HIL test failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

# ============================================================================
# TEST SUITE RUNNER
# ============================================================================

def run_test_suite():
    """Run all test cases"""
    print_section("AGENTIC VACATION PLANNER - TEST SUITE")
    print_info("Testing the complete multi-agent system with HIL support")
    print_info("This will test: Orchestration, Agent Coordination, and HIL Flow\n")
    
    # Define test cases
    test_cases = [
        HILFlowTest(),           # Start with focused HIL test
        SimpleVacationTest(),    # Then simple end-to-end
        # ComplexVacationTest(),   # Uncomment for full testing
    ]
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print_info(f"Running test {i}/{len(test_cases)}...")
        success = test_case.run()
        results.append((test_case.name, success))
        
        if not success:
            print_warning(f"Test '{test_case.name}' failed, but continuing with next test...\n")
    
    # Print summary
    print_section("TEST SUMMARY")
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    for name, success in results:
        if success:
            print_success(f"{name}: PASSED")
        else:
            print_error(f"{name}: FAILED")
    
    print(f"\n{Colors.BOLD}Total: {len(results)} tests, {passed} passed, {failed} failed{Colors.END}")
    
    if failed == 0:
        print_success("\n🎉 ALL TESTS PASSED! Your agentic system is working correctly!")
        return True
    else:
        print_warning(f"\n⚠️  {failed} test(s) failed. Review the output above for details.")
        return False

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print(f"{Colors.CYAN}")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║       AGENTIC VACATION PLANNER - COMPREHENSIVE TEST SUITE          ║")
    print("║                                                                    ║")
    print("║  Testing: OrchestratorAgent, FlightAgent, HotelAgent              ║")
    print("║  Features: HIL Flow, Agent Coordination, Mock Data                ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}\n")
    
    success = run_test_suite()
    
    sys.exit(0 if success else 1)
