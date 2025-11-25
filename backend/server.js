import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { GoogleGenerativeAI } from '@google/generative-ai';

// Load environment variables
dotenv.config();

// Initialize Express app
const app = express();
const PORT = process.env.PORT || 8080;

// Middleware
app.use(cors());
app.use(express.json());

// =============================================================================
// AUTHENTICATION MIDDLEWARE
// =============================================================================
// Simple email-based authentication for development
// Public paths don't require authentication
const publicPaths = ['/health'];

app.use((req, res, next) => {
  // Allow public endpoints without authentication
  if (publicPaths.includes(req.path)) {
    return next();
  }

  const authHeader = req.headers.authorization;
  
  if (!authHeader?.startsWith('Bearer ')) {
    console.log('❌ No auth header found');
    return res.status(401).json({
      success: false,
      error: 'Authentication required',
    });
  }

  const token = authHeader.split(' ')[1];
  console.log('🔐 Received auth:', token.substring(0, 25) + '...');

  // Simple validation: check if it's an email format
  if (token && token.includes('@') && token.includes('.')) {
    console.log('✅ User authenticated:', token);
    req.user = { email: token };
    return next();
  }

  console.log('❌ Invalid auth token');
  return res.status(401).json({
    success: false,
    error: 'Invalid authentication',
  });
});

// =============================================================================
// GEMINI AI INITIALIZATION
// =============================================================================
// Initialize Gemini AI for potential future use in this layer
// Currently, the heavy lifting is done by the Python agents
let model = null;
if (process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'your-gemini-api-key') {
  const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
  model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
  console.log('✅ Gemini AI initialized');
} else {
  console.log('⚠️  Gemini API key not set');
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * FORMAT COMPLETE VACATION PLAN
 * 
 * Takes the results from the Python orchestrator and formats them into
 * a user-friendly markdown response.
 * 
 * This function only handles PRESENTATION, not decision-making or parsing.
 * All business logic and AI decisions happen in the Python agents layer.
 * 
 * @param {Object} results - Results from the orchestrator containing flight, hotel, restaurant, attraction, and itinerary data
 * @param {Object} travelDetails - Basic trip details for the header (origin, destination, dates)
 * @returns {string} Formatted markdown string
 */
function formatCompleteVacationPlan(results, travelDetails) {
  let plan = `# 🌍 Your Complete Vacation Plan\n\n`;
  
  // Add trip header if we have the basic details
  if (travelDetails) {
    if (travelDetails.origin && travelDetails.destination) {
      plan += `**Trip:** ${travelDetails.origin} → ${travelDetails.destination}\n`;
    }
    if (travelDetails.departure_date && travelDetails.return_date) {
      plan += `**Dates:** ${travelDetails.departure_date} to ${travelDetails.return_date}\n`;
    }
    if (travelDetails.passengers) {
      plan += `**Travelers:** ${travelDetails.passengers} people\n`;
    }
    if (travelDetails.budget) {
      plan += `**Budget:** €${travelDetails.budget}\n`;
    }
    plan += `\n---\n\n`;
  }
  
  // FLIGHTS SECTION
  // Display the user's selected flight from two-phase HIL
  plan += `## ✈️ Your Flight\n\n`;
  const finalFlight = results.final_flight;
  if (finalFlight) {
    plan += `**${finalFlight.outbound.airline} ${finalFlight.outbound.flight}** - $${finalFlight.price} ${finalFlight.currency}\n\n`;
    plan += `**Outbound:**\n`;
    plan += `- ${finalFlight.outbound.from} → ${finalFlight.outbound.to}\n`;
    plan += `- Departs: ${new Date(finalFlight.outbound.departure).toLocaleString()}\n`;
    plan += `- Arrives: ${new Date(finalFlight.outbound.arrival).toLocaleString()}\n`;
    plan += `- Duration: ${finalFlight.outbound.duration} | Stops: ${finalFlight.outbound.stops}\n\n`;
    
    if (finalFlight.return) {
      plan += `**Return:**\n`;
      plan += `- ${finalFlight.return.from} → ${finalFlight.return.to}\n`;
      plan += `- Departs: ${new Date(finalFlight.return.departure).toLocaleString()}\n`;
      plan += `- Arrives: ${new Date(finalFlight.return.arrival).toLocaleString()}\n`;
      plan += `- Duration: ${finalFlight.return.duration} | Stops: ${finalFlight.return.stops}\n\n`;
    }
  } else {
    plan += `Flight information unavailable.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // HOTELS SECTION
  // Display the user's selected hotel from two-phase HIL
  plan += `## 🏨 Your Hotel\n\n`;
  const finalHotel = results.final_hotel;
  if (finalHotel) {
    plan += `**${finalHotel.name}** ${'⭐'.repeat(Math.min(finalHotel.rating || 0, 5))}\n`;
    plan += `- $${finalHotel.price}/night\n`;
    plan += `- Room: ${finalHotel.room_type}\n\n`;
  } else {
    plan += `Hotel information unavailable.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // RESTAURANTS SECTION
  // Display auto-selected restaurants from Phase 2
  plan += `## 🍽️ Recommended Restaurants\n\n`;
  const finalRestaurant = results.final_restaurant;
  if (finalRestaurant && finalRestaurant.recommended_restaurants) {
    finalRestaurant.recommended_restaurants.slice(0, 5).forEach((rest, i) => {
      plan += `**${i + 1}. ${rest.name}** ⭐ ${rest.rating || 'N/A'}\n`;
      if (rest.cuisine) plan += `- Cuisine: ${rest.cuisine}\n`;
      if (rest.address) plan += `- ${rest.address}\n`;
      plan += `\n`;
    });
  } else {
    plan += `Restaurant recommendations unavailable.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // ATTRACTIONS SECTION
  // Display auto-selected attractions from Phase 2
  plan += `## 🎭 Things to Do\n\n`;
  const finalAttraction = results.final_attraction;
  if (finalAttraction && finalAttraction.recommended_attractions) {
    finalAttraction.recommended_attractions.slice(0, 5).forEach((attr, i) => {
      plan += `**${i + 1}. ${attr.name}** ⭐ ${attr.rating || 'N/A'}\n`;
      if (attr.type) plan += `- Type: ${attr.type}\n`;
      if (attr.address) plan += `- ${attr.address}\n`;
      plan += `\n`;
    });
  } else {
    plan += `Attraction recommendations unavailable.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // ITINERARY SECTION
  // Display day-by-day plan created by the ItineraryAgent
  plan += `## 📅 Day-by-Day Itinerary\n\n`;
  const itineraryData = results.itinerary;
  if (itineraryData?.success && itineraryData.itinerary?.length > 0) {
    itineraryData.itinerary.forEach((day) => {
      plan += `### Day ${day.day} - ${day.date}\n\n`;
      
      // Morning activity
      if (day.morning?.activity) {
        plan += `**Morning:** ${day.morning.activity}\n`;
        if (day.morning.location) plan += `📍 ${day.morning.location}\n\n`;
      }
      
      // Lunch
      if (day.lunch?.restaurant) {
        plan += `**Lunch:** ${day.lunch.restaurant}\n`;
        if (day.lunch.cuisine) plan += `🍽️ ${day.lunch.cuisine}\n\n`;
      }
      
      // Afternoon activity
      if (day.afternoon?.activity) {
        plan += `**Afternoon:** ${day.afternoon.activity}\n`;
        if (day.afternoon.location) plan += `📍 ${day.afternoon.location}\n\n`;
      }
      
      // Dinner
      if (day.dinner?.restaurant) {
        plan += `**Dinner:** ${day.dinner.restaurant}\n`;
        if (day.dinner.cuisine) plan += `🍽️ ${day.dinner.cuisine}\n\n`;
      }
    });
  } else {
    plan += `Itinerary will be generated based on your preferences.\n\n`;
  }
  
  plan += `---\n\n`;
  plan += `*Powered by AI Multi-Agent System*`;
  return plan;
}

// =============================================================================
// API ENDPOINTS
// =============================================================================

/**
 * HEALTH CHECK ENDPOINT
 * Simple endpoint to verify the server is running
 */
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    message: 'Vacation Planner API (Production HIL)',
    timestamp: new Date().toISOString()
  });
});

/**
 * PLAN VACATION WITH AGENTS ENDPOINT - PRODUCTION HIL VERSION
 * 
 * This endpoint now supports Human-in-the-Loop (HIL) interactions:
 * 
 * Flow:
 * 1. User sends prompt
 * 2. Backend forwards to Python orchestrator
 * 3. Orchestrator may PAUSE and return recommendations
 * 4. Frontend displays recommendations
 * 5. User makes choice
 * 6. Frontend calls /api/resume with choice
 * 7. Process continues until complete
 * 
 * @route POST /api/plan-vacation-agents
 * @body {string} prompt - The raw user input
 * @returns {Object} Either:
 *   - {status: "awaiting_user_input", session_id, recommendations, ...}
 *   - {status: "complete", success: true, data: formatted_plan}
 *   - {status: "error", success: false, error: message}
 */
app.post('/api/plan-vacation-agents', async (req, res) => {
  try {
    const { prompt } = req.body;
    
    // Validate that we received a prompt
    if (!prompt || typeof prompt !== 'string' || prompt.trim() === '') {
      return res.status(400).json({
        success: false,
        error: 'Missing or invalid prompt',
        message: 'Please provide a vacation planning request'
      });
    }
    
    console.log('📝 User:', req.user?.email);
    console.log('📝 Prompt:', prompt);
    
    const pythonApiUrl = process.env.PYTHON_AGENT_API_URL || 'http://localhost:8081';
    
    console.log('🤖 Sending request to Python orchestrator...');
    
    const orchestratorResponse = await fetch(`${pythonApiUrl}/api/agents/orchestrate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_prompt: prompt
      })
    });
    
    const orchestratorData = await orchestratorResponse.json();
    
    // ==========================================================================
    // PRODUCTION HIL: Handle different response statuses
    // ==========================================================================
    
    // Case 1: Agent paused for Human-in-the-Loop input
    if (orchestratorData.status === 'awaiting_user_input') {
      console.log('⏸️  Agent paused for user input:', orchestratorData.agent);
      
      // Forward pause response to frontend
      return res.json({
        status: 'awaiting_user_input',
        session_id: orchestratorData.session_id,
        agent: orchestratorData.agent,
        item_type: orchestratorData.item_type,
        recommendations: orchestratorData.recommendations,
        summary: orchestratorData.summary,
        turn: orchestratorData.turn
      });
    }
    
    // Case 2: Orchestration complete
    if (orchestratorData.status === 'complete' && orchestratorData.success) {
      console.log('✅ Plan generated successfully!');
      
      const travelDetails = orchestratorData.travel_details || {};
      const formattedPlan = formatCompleteVacationPlan(
        orchestratorData.all_results || {}, 
        travelDetails
      );
      
      return res.json({
        status: 'complete',
        success: true,
        data: formattedPlan,
        message: 'Vacation plan ready',
        raw_results: orchestratorData.all_results,
        travel_details: travelDetails
      });
    }
    
    // Case 3: Error occurred
    if (orchestratorData.status === 'error' || !orchestratorData.success) {
      throw new Error(orchestratorData.error || 'Orchestrator failed to plan vacation');
    }
    
    // Case 4: Unexpected response
    console.warn('⚠️  Unexpected orchestrator response:', orchestratorData);
    throw new Error('Unexpected response from orchestrator');
    
  } catch (error) {
    console.error('❌ Error:', error);
    
    // Handle different types of errors appropriately
    if (error.message.includes('fetch')) {
      return res.status(503).json({ 
        status: 'error',
        success: false, 
        error: 'Unable to connect to AI agents service',
        message: 'Please ensure the Python agents service is running on port 8081'
      });
    }
    
    res.status(500).json({ 
      status: 'error',
      success: false, 
      error: error.message,
      message: 'Failed to generate vacation plan'
    });
  }
});

/**
 * RESUME VACATION PLANNING ENDPOINT - NEW FOR PRODUCTION HIL
 * 
 * This endpoint handles user responses after an HIL pause.
 * 
 * The user has made a choice (e.g., selected a flight) or provided
 * refinement feedback (e.g., "too expensive"), and we need to resume
 * the orchestration process.
 * 
 * @route POST /api/resume
 * @body {string} session_id - Session ID from the pause response
 * @body {Object} user_decision - User's decision
 *   - {status: "FINAL_CHOICE", flight_id: "123"} OR
 *   - {status: "REFINE_SEARCH", feedback: "Too expensive..."}
 * @returns {Object} Same as /api/plan-vacation-agents:
 *   - May pause again for next agent
 *   - Or return complete plan
 */
app.post('/api/resume', async (req, res) => {
  try {
    const { session_id, user_decision } = req.body;
    
    // Validate required fields
    if (!session_id || !user_decision) {
      return res.status(400).json({
        success: false,
        error: 'Missing session_id or user_decision',
        message: 'Both session_id and user_decision are required to resume'
      });
    }
    
    console.log('▶️  Resuming session:', session_id);
    console.log('👤 User decision:', user_decision.status);
    
    const pythonApiUrl = process.env.PYTHON_AGENT_API_URL || 'http://localhost:8081';
    
    const resumeResponse = await fetch(`${pythonApiUrl}/api/agents/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id,
        user_decision
      })
    });
    
    const resumeData = await resumeResponse.json();
    
    // ==========================================================================
    // Handle resume response (same logic as initial request)
    // ==========================================================================
    
    // Case 1: Agent paused again (e.g., moved from FlightAgent to HotelAgent)
    if (resumeData.status === 'awaiting_user_input') {
      console.log('⏸️  Agent paused again for user input:', resumeData.agent);
      
      return res.json({
        status: 'awaiting_user_input',
        session_id: resumeData.session_id || session_id, // Keep same session
        agent: resumeData.agent,
        item_type: resumeData.item_type,
        recommendations: resumeData.recommendations,
        summary: resumeData.summary,
        turn: resumeData.turn
      });
    }
    
    // Case 2: Orchestration complete
    if (resumeData.status === 'complete' && resumeData.success) {
      console.log('✅ Orchestration completed after resume!');
      
      const travelDetails = resumeData.travel_details || {};
      const formattedPlan = formatCompleteVacationPlan(
        resumeData.all_results || {}, 
        travelDetails
      );
      
      return res.json({
        status: 'complete',
        success: true,
        data: formattedPlan,
        message: 'Vacation plan ready',
        raw_results: resumeData.all_results,
        travel_details: travelDetails
      });
    }
    
    // Case 3: Error occurred
    if (resumeData.status === 'error' || !resumeData.success) {
      throw new Error(resumeData.error || 'Resume failed');
    }
    
    // Case 4: Unexpected response
    console.warn('⚠️  Unexpected resume response:', resumeData);
    throw new Error('Unexpected response from resume');
    
  } catch (error) {
    console.error('❌ Resume error:', error);
    
    if (error.message.includes('fetch')) {
      return res.status(503).json({ 
        status: 'error',
        success: false, 
        error: 'Unable to connect to AI agents service'
      });
    }
    
    res.status(500).json({ 
      status: 'error',
      success: false, 
      error: error.message,
      message: 'Failed to resume vacation planning'
    });
  }
});

// =============================================================================
// START SERVER
// =============================================================================

app.listen(PORT, () => {
  console.log(`\n🚀 Vacation Planner API (Production HIL)`);
  console.log(`📍 http://localhost:${PORT}`);
  console.log(`🔐 Auth: Email-based`);
  console.log(`🤖 Agentic Mode: Enabled`);
  console.log(`⏸️  HIL Support: Production-ready pause/resume\n`);
});