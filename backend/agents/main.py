"""
Agent API Server (Flask)
========================
This is a Flask web server that exposes our Python agents via REST API.

Architecture:
  Frontend (Port 3000) 
      ↓
  Node.js Backend (Port 8080) 
      ↓
  **THIS SERVER** - Python Agent API (Port 8081)  ← We are here
      ↓
  MCP Servers → External APIs (Amadeus, Google Places, etc.)

What this server does:
1. Listen for HTTP requests on port 8081
2. Route requests to the appropriate agent
3. Return agent results as JSON
4. Handle errors gracefully

Endpoints:
- GET  /health - Check if server is running
- POST /api/agents/flight/search - Search for flights
"""

import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# STEP 1: Add current directory to Python path
# This allows Python to find our 'agents' package
# Without this, "from agents.flight_agent import FlightAgent" would fail
sys.path.insert(0, os.path.dirname(__file__))

# STEP 2: Import our agents
from agents.flight_agent import FlightAgent
from agents.hotel_agent import HotelAgent
from agents.restaurant_agent import RestaurantAgent
from agents.attractions_agent import AttractionsAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.itinerary_agent import ItineraryAgent


# STEP 3: Load environment variables from backend/.env
# Go up one directory (..) to find .env file
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

# STEP 4: Initialize Flask application
app = Flask(__name__)

# Enable CORS (Cross-Origin Resource Sharing)
# This allows our Node.js backend to make requests to this server
# Without CORS, browsers block requests between different ports
CORS(app)

# STEP 5: Get API keys from environment
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Validate that we have the required API key
if not GEMINI_API_KEY:
    print("❌ ERROR: GEMINI_API_KEY not found in .env file")
    print("   Make sure backend/.env has your Gemini API key")
    sys.exit(1)  # Exit if no API key (can't work without it)

# STEP 6: Initialize our agents
# Load Google Places API key
PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY')

# Initialize agents
flight_agent = FlightAgent(GEMINI_API_KEY)
hotel_agent = HotelAgent(GEMINI_API_KEY)
restaurant_agent = RestaurantAgent(GEMINI_API_KEY, PLACES_API_KEY)
attractions_agent = AttractionsAgent(GEMINI_API_KEY, PLACES_API_KEY)
itinerary_agent = ItineraryAgent(GEMINI_API_KEY)
orchestrator_agent = OrchestratorAgent(GEMINI_API_KEY, flight_agent, hotel_agent, restaurant_agent, attractions_agent, itinerary_agent)
print("✅ Agent API Server initialized successfully")


# ============================================================================
# ENDPOINTS - The API routes that clients can call
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health Check Endpoint
    
    Purpose: Let other services check if this server is running
    URL: GET http://localhost:8081/health
    
    Returns:
        JSON with server status and available agents
        
    Example response:
    {
        "status": "ok",
        "service": "Agent API Server",
        "agents": ["FlightAgent"]
    }
    """
    return jsonify({
        "status": "ok",
        "service": "Agent API Server",
        "agents": ["FlightAgent","HotelAgent","RestaurantAgent","AttractionsAgent","ItineraryAgent","OrchestratorAgent"]  # List all available agents
    })
@app.route('/api/agents/hotel/search', methods=['POST'])
def search_hotels():
    """
    Hotel Search Endpoint
    
    Request body:
    {
        "city_code": "NYC",
        "check_in_date": "2025-12-15",
        "check_out_date": "2025-12-20",
        "adults": 2,
        "budget_per_night": 200,
        "preferences": {
            "min_rating": 4
        }
    }
    """
    try:
        data = request.json
        
        print(f"[API] Received hotel search request: {data.get('city_code')}")
        
        result = hotel_agent.execute(data)
        return jsonify(result)
        
    except Exception as e:
        print(f"[API] Error in hotel search: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "agent": "HotelAgent"
        }), 500
@app.route('/api/agents/restaurant/search', methods=['POST'])
def search_restaurants():
    """
    Restaurant Search Endpoint
    """
    try:
        data = request.json
        print(f"[API] Received restaurant search: {data.get('city')}")
        
        result = restaurant_agent.execute(data)
        return jsonify(result)
        
    except Exception as e:
        print(f"[API] Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "agent": "RestaurantAgent"
        }), 500
@app.route('/api/agents/attractions/search', methods=['POST'])
def search_attractions():
    try:
        data = request.json
        print(f"[API] Received attractions search: {data.get('city')}")
        result = attractions_agent.execute(data)
        return jsonify(result)
    except Exception as e:
        print(f"[API] Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "agent": "AttractionsAgent"
        }), 500        
@app.route('/api/agents/orchestrate', methods=['POST'])
def orchestrate_vacation():
    """
    Orchestrator Endpoint - Coordinates all agents
    """
    try:
        # 1. Get the JSON data from the request body
        data = request.json
        
        # --- CRITICAL FIX: Extract the 'user_prompt' string ---
        user_prompt = data.get('user_prompt') 
        # ------------------------------------------------------

        if not user_prompt:
            return jsonify({"success": False, "error": "Missing 'user_prompt' key in request body."}), 400

        # Optional: Update the logging to reflect the prompt
        print(f"[API] Orchestrating vacation plan for prompt: {user_prompt[:50]}...")
        
        # 2. Pass the extracted STRING (not the dict) to the agent
        result = orchestrator_agent.execute(user_prompt)
        
        return jsonify(result), 200 # Return with 200 status code
        
    except Exception as e:
        print(f"[API] Orchestration error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "agent": "OrchestratorAgent"
        }), 500
@app.route('/api/agents/flight/search', methods=['POST'])
def search_flights():
    """
    Flight Search Endpoint
    
    Purpose: Search for flights using the FlightAgent
    URL: POST http://localhost:8081/api/agents/flight/search
    
    Request body (JSON):
    {
        "origin": "SFO",
        "destination": "BCN",
        "departure_date": "2025-12-15",
        "return_date": "2025-12-20",
        "passengers": 2,
        "budget": 2000,
        "preferences": {
            "max_stops": 1,
            "cabin": "economy"
        }
    }
    
    Returns:
        JSON with flight search results:
        {
            "success": true,
            "flights": [...],
            "summary": "AI-generated summary",
            "agent": "FlightAgent"
        }
        
    How it works:
    1. Extract JSON data from request
    2. Pass data to FlightAgent.execute()
    3. FlightAgent does its work (parse, search, filter, summarize)
    4. Return results as JSON
    """
    try:
        # Extract JSON data from the request body
        # request.json automatically parses the JSON
        data = request.json
        
        # Log what we received (helpful for debugging)
        print(f"[API] Received flight search request: {data.get('origin')} → {data.get('destination')}")
        
        # Call the FlightAgent to do the work
        # execute() method handles everything internally
        result = flight_agent.execute(data)
        
        # Return the result as JSON
        # jsonify() converts Python dict to JSON format
        return jsonify(result)
        
    except Exception as e:
        # If anything goes wrong, return error response
        print(f"[API] Error in flight search: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "agent": "FlightAgent"
        }), 500  # 500 = Internal Server Error


# ============================================================================
# SERVER STARTUP
# ============================================================================

if __name__ == '__main__':
    # Get port from environment variable or use 8081 as default
    port = int(os.environ.get('AGENT_PORT', 8081))
    
    print("\n" + "="*60)
    print("🚀 Agent API Server Starting")
    print("="*60)
    print(f"📍 Running on: http://localhost:{port}")
    print(f"🏥 Health check: http://localhost:{port}/health")
    print(f"✈️  Flight search: POST http://localhost:{port}/api/agents/flight/search")
    print("="*60 + "\n")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=port, debug=False)