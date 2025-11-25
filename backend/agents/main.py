"""
Agent API Server (Flask) - PRODUCTION WITH REAL HIL
===================================================
This is a Flask web server that exposes our Python agents via REST API.

PRODUCTION HIL FLOW:
  1. User starts: POST /api/agents/orchestrate with user_prompt
  2. Agent pauses: Returns {status: "awaiting_user_input", session_id, recommendations}
  3. User chooses: POST /api/agents/resume with {session_id, user_decision}
  4. Agent continues: Resumes from stored state
  5. Repeat 2-4 until complete

Architecture:
  Frontend (Port 3000) 
      ↓
  Node.js Backend (Port 8080) 
      ↓
  **THIS SERVER** - Python Agent API (Port 8081)  ← We are here
      ↓
  MCP Servers → External APIs (Amadeus, Google Places, etc.)
"""

import os
import sys
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# STEP 1: Add current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# STEP 2: Import our agents
from agents.flight_agent import FlightAgent
from agents.hotel_agent import HotelAgent
from agents.restaurant_agent import RestaurantAgent
from agents.attractions_agent import AttractionsAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.itinerary_agent import ItineraryAgent

# STEP 3: Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path)

print(f"📁 Loading .env from: {os.path.abspath(env_path)}")
print(f"🔑 GEMINI_API_KEY found: {'Yes ✅' if os.getenv('GEMINI_API_KEY') else 'No ❌'}")

# STEP 4: Initialize Flask application
app = Flask(__name__)
CORS(app)

# STEP 5: Get API keys from environment
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    print("❌ ERROR: GEMINI_API_KEY not found in .env file")
    sys.exit(1)

# STEP 6: Initialize our agents
PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY')

flight_agent = FlightAgent(GEMINI_API_KEY)
hotel_agent = HotelAgent(GEMINI_API_KEY)
restaurant_agent = RestaurantAgent(GEMINI_API_KEY, PLACES_API_KEY)
attractions_agent = AttractionsAgent(GEMINI_API_KEY, PLACES_API_KEY)
itinerary_agent = ItineraryAgent(GEMINI_API_KEY)
orchestrator_agent = OrchestratorAgent(
    GEMINI_API_KEY, 
    flight_agent, 
    hotel_agent, 
    restaurant_agent, 
    attractions_agent, 
    itinerary_agent
)

print("✅ Agent API Server initialized successfully")

# ============================================================================
# SESSION STORAGE FOR HIL (In-Memory for now, use Redis/DB for production)
# ============================================================================

# Store active orchestrator sessions
# Key: session_id (UUID), Value: orchestrator state dict
active_sessions = {}

def create_session(orchestrator_state: dict) -> str:
    """
    Create a new session for HIL pause.
    
    Args:
        orchestrator_state: State dict from orchestrator including agent instances
        
    Returns:
        session_id: Unique identifier for this session
    """
    session_id = str(uuid.uuid4())
    active_sessions[session_id] = orchestrator_state
    print(f"[SESSION] Created session: {session_id}")
    return session_id

def get_session(session_id: str) -> dict:
    """Retrieve session state by ID."""
    return active_sessions.get(session_id)

def delete_session(session_id: str):
    """Delete session after completion."""
    if session_id in active_sessions:
        del active_sessions[session_id]
        print(f"[SESSION] Deleted session: {session_id}")

# ============================================================================
# ENDPOINTS - The API routes that clients can call
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health Check Endpoint"""
    return jsonify({
        "status": "ok",
        "service": "Agent API Server (Production HIL)",
        "agents": ["FlightAgent","HotelAgent","RestaurantAgent","AttractionsAgent","ItineraryAgent","OrchestratorAgent"],
        "active_sessions": len(active_sessions)
    })

@app.route('/api/agents/orchestrate', methods=['POST'])
def orchestrate_vacation():
    """
    Orchestrator Endpoint - PRODUCTION VERSION WITH REAL HIL
    
    Request:
    {
        "user_prompt": "Plan a trip to Madrid from Dec 10-15, 2025..."
    }
    
    Response Types:
    
    1. AWAITING USER INPUT (HIL Pause):
    {
        "status": "awaiting_user_input",
        "session_id": "uuid-here",
        "agent": "FlightAgent",
        "item_type": "flight",
        "recommendations": [...],
        "summary": "Here are 3 flight options..."
    }
    
    2. COMPLETE:
    {
        "status": "complete",
        "success": true,
        "summary": "...",
        "all_results": {...}
    }
    
    3. ERROR:
    {
        "status": "error",
        "success": false,
        "error": "..."
    }
    """
    try:
        data = request.json
        user_prompt = data.get('user_prompt')

        if not user_prompt:
            return jsonify({
                "status": "error",
                "success": False, 
                "error": "Missing 'user_prompt' key in request body."
            }), 400

        print(f"[API] Starting orchestration: {user_prompt[:60]}...")
        
        # Execute orchestrator (will pause on first HIL)
        result = orchestrator_agent.execute(user_prompt)
        
        # Check if orchestrator is pausing for HIL
        if result.get('status') == 'awaiting_user_input':
            # Create session and store orchestrator state
            session_id = create_session(result.get('session_state', {}))
            
            # Return HIL pause response to frontend
            return jsonify({
                "status": "awaiting_user_input",
                "session_id": session_id,
                "agent": result.get('agent'),
                "item_type": result.get('item_type'),
                "recommendations": result.get('recommendations', []),
                "summary": result.get('summary', ''),
                "turn": result.get('turn', 1)
            }), 200
        
        # Orchestrator completed successfully
        elif result.get('success'):
            return jsonify({
                "status": "complete",
                "success": True,
                "summary": result.get('summary', ''),
                "all_results": result.get('all_results', {})
            }), 200
        
        # Error occurred
        else:
            return jsonify({
                "status": "error",
                "success": False,
                "error": result.get('error', 'Unknown error'),
                "summary": result.get('summary', '')
            }), 500
        
    except Exception as e:
        print(f"[API] Orchestration error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/agents/resume', methods=['POST'])
def resume_orchestration():
    """
    Resume Endpoint - PRODUCTION HIL CONTINUATION
    
    Request:
    {
        "session_id": "uuid-from-pause",
        "user_decision": {
            "status": "FINAL_CHOICE" or "REFINE_SEARCH",
            "flight_id": "123" (if FINAL_CHOICE),
            "feedback": "Too expensive..." (if REFINE_SEARCH)
        }
    }
    
    Response: Same as /orchestrate - can pause again or complete
    """
    try:
        data = request.json
        session_id = data.get('session_id')
        user_decision = data.get('user_decision')
        
        if not session_id or not user_decision:
            return jsonify({
                "status": "error",
                "success": False,
                "error": "Missing 'session_id' or 'user_decision' in request body."
            }), 400
        
        # Retrieve session
        session_state = get_session(session_id)
        if not session_state:
            return jsonify({
                "status": "error",
                "success": False,
                "error": f"Invalid or expired session_id: {session_id}"
            }), 404
        
        print(f"[API] Resuming session {session_id} with decision: {user_decision.get('status')}")
        
        # Resume orchestrator with user decision
        result = orchestrator_agent.resume(session_state, user_decision)
        
        # Check result type (pause again or complete)
        if result.get('status') == 'awaiting_user_input':
            # Still need more input - update session
            active_sessions[session_id] = result.get('session_state', {})
            
            return jsonify({
                "status": "awaiting_user_input",
                "session_id": session_id,
                "agent": result.get('agent'),
                "item_type": result.get('item_type'),
                "recommendations": result.get('recommendations', []),
                "summary": result.get('summary', ''),
                "turn": result.get('turn', 1)
            }), 200
        
        # Completed successfully
        elif result.get('success'):
            # Clean up session
            delete_session(session_id)
            
            return jsonify({
                "status": "complete",
                "success": True,
                "summary": result.get('summary', ''),
                "all_results": result.get('all_results', {})
            }), 200
        
        # Error
        else:
            delete_session(session_id)
            return jsonify({
                "status": "error",
                "success": False,
                "error": result.get('error', 'Unknown error')
            }), 500
        
    except Exception as e:
        print(f"[API] Resume error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "success": False,
            "error": str(e)
        }), 500

# ============================================================================
# LEGACY ENDPOINTS (Keep for direct agent testing)
# ============================================================================

@app.route('/api/agents/flight/search', methods=['POST'])
def search_flights():
    """Direct FlightAgent endpoint (bypasses orchestrator)"""
    try:
        data = request.json
        print(f"[API] Direct flight search: {data.get('origin')} → {data.get('destination')}")
        result = flight_agent.execute(data)
        return jsonify(result)
    except Exception as e:
        print(f"[API] Error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/agents/hotel/search', methods=['POST'])
def search_hotels():
    """Direct HotelAgent endpoint (bypasses orchestrator)"""
    try:
        data = request.json
        print(f"[API] Direct hotel search: {data.get('city_code')}")
        result = hotel_agent.execute(data)
        return jsonify(result)
    except Exception as e:
        print(f"[API] Error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/agents/restaurant/search', methods=['POST'])
def search_restaurants():
    """Direct RestaurantAgent endpoint (bypasses orchestrator)"""
    try:
        data = request.json
        print(f"[API] Direct restaurant search: {data.get('city')}")
        result = restaurant_agent.execute(data)
        return jsonify(result)
    except Exception as e:
        print(f"[API] Error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/agents/attractions/search', methods=['POST'])
def search_attractions():
    """Direct AttractionsAgent endpoint (bypasses orchestrator)"""
    try:
        data = request.json
        print(f"[API] Direct attractions search: {data.get('city')}")
        result = attractions_agent.execute(data)
        return jsonify(result)
    except Exception as e:
        print(f"[API] Error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================================
# SERVER STARTUP
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('AGENT_PORT', 8081))
    
    print("\n" + "="*60)
    print("🚀 Agent API Server Starting (PRODUCTION HIL)")
    print("="*60)
    print(f"📍 Running on: http://localhost:{port}")
    print(f"🏥 Health check: http://localhost:{port}/health")
    print(f"🎯 Orchestrator: POST http://localhost:{port}/api/agents/orchestrate")
    print(f"▶️  Resume: POST http://localhost:{port}/api/agents/resume")
    print(f"✈️  Direct Flight: POST http://localhost:{port}/api/agents/flight/search")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)