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
 * FORMAT COMPLETE VACATION PLAN (FALLBACK)
 * 
 * This is now a FALLBACK formatter in case the Python ItineraryAgent
 * doesn't provide formatted output.
 * 
 * Ideally, the Python ItineraryAgent creates the beautiful formatted text,
 * and this function is rarely used.
 * 
 * @param {Object} results - Results from the orchestrator
 * @param {Object} travelDetails - Basic trip details
 * @returns {string} Formatted markdown string
 */
function formatCompleteVacationPlan(results, travelDetails) {
  let plan = `# ✨ Your Dream Vacation Awaits!\n\n`;
  
  // EXCITING TRIP HEADER
  if (travelDetails) {
    plan += `## 🌍 Your Adventure\n\n`;
    
    if (travelDetails.origin && travelDetails.destination) {
      plan += `**Destination:** ${travelDetails.destination} 🎯\n`;
      plan += `**Departing from:** ${travelDetails.origin}\n`;
    }
    
    if (travelDetails.departure_date && travelDetails.return_date) {
      const departDate = new Date(travelDetails.departure_date);
      const returnDate = new Date(travelDetails.return_date);
      const tripDays = Math.ceil((returnDate - departDate) / (1000 * 60 * 60 * 24));
      
      plan += `**When:** ${departDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}\n`;
      plan += `**Duration:** ${tripDays} unforgettable days\n`;
    }
    
    if (travelDetails.passengers) {
      plan += `**Travelers:** ${travelDetails.passengers} ${travelDetails.passengers === 1 ? 'adventurer' : 'adventurers'}\n`;
    }
    
    if (travelDetails.budget) {
      plan += `**Budget:** €${travelDetails.budget}\n`;
    }
    
    plan += `\n---\n\n`;
  }
  
  // FLIGHTS SECTION
  plan += `## ✈️ Your Journey Begins\n\n`;
  const finalFlight = results.final_flight;
  if (finalFlight) {
    plan += `Get ready to soar! Your flight is all set:\n\n`;
    plan += `**${finalFlight.outbound.airline} ${finalFlight.outbound.flight}** • $${finalFlight.price} ${finalFlight.currency}\n\n`;
    
    plan += `**🛫 Outbound Flight:**\n`;
    plan += `• Departs ${finalFlight.outbound.from} → ${finalFlight.outbound.to}\n`;
    plan += `• ${new Date(finalFlight.outbound.departure).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}\n`;
    plan += `• Arrives: ${new Date(finalFlight.outbound.arrival).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}\n`;
    plan += `• Flight time: ${finalFlight.outbound.duration} • ${finalFlight.outbound.stops === 0 ? 'Direct flight!' : `${finalFlight.outbound.stops} stop(s)`}\n\n`;
    
    if (finalFlight.return) {
      plan += `**🛬 Return Flight:**\n`;
      plan += `• Departs ${finalFlight.return.from} → ${finalFlight.return.to}\n`;
      plan += `• ${new Date(finalFlight.return.departure).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}\n`;
      plan += `• Arrives: ${new Date(finalFlight.return.arrival).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}\n`;
      plan += `• Flight time: ${finalFlight.return.duration} • ${finalFlight.return.stops === 0 ? 'Direct flight!' : `${finalFlight.return.stops} stop(s)`}\n\n`;
    }
  } else {
    plan += `Your flight details will be confirmed shortly.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // HOTEL SECTION
  plan += `## 🏨 Your Home Away From Home\n\n`;
  const finalHotel = results.final_hotel;
  if (finalHotel) {
    plan += `Welcome to your perfect retreat:\n\n`;
    plan += `### ${finalHotel.name} ${'⭐'.repeat(Math.round(finalHotel.rating || 3))}\n\n`;
    plan += `**Rate:** $${finalHotel.price}/night\n\n`;
    plan += `**Your Room:**\n`;
    plan += `${finalHotel.room_type}\n\n`;
  } else {
    plan += `Your accommodation will be confirmed shortly.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // RESTAURANTS SECTION
  plan += `## 🍽️ Culinary Adventures Await\n\n`;
  plan += `We've handpicked these exceptional dining spots for you:\n\n`;
  const finalRestaurant = results.final_restaurant;
  if (finalRestaurant && finalRestaurant.recommended_restaurants) {
    finalRestaurant.recommended_restaurants.forEach((rest, i) => {
      plan += `**${i + 1}. ${rest.name}** ${'⭐'.repeat(Math.round(rest.rating || 4))}\n`;
      if (rest.cuisine) plan += `   *${rest.cuisine}*\n`;
      if (rest.price_level) {
        const priceSymbols = '€'.repeat(rest.price_level);
        plan += `   ${priceSymbols} • `;
      }
      if (rest.address) plan += `${rest.address}`;
      plan += `\n\n`;
    });
  } else {
    plan += `Restaurant recommendations will be added to your plan.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // ATTRACTIONS SECTION
  plan += `## 🎭 Discover & Explore\n\n`;
  plan += `These amazing experiences are waiting for you:\n\n`;
  const finalAttraction = results.final_attraction;
  if (finalAttraction && finalAttraction.recommended_attractions) {
    finalAttraction.recommended_attractions.forEach((attr, i) => {
      plan += `**${i + 1}. ${attr.name}** ${'⭐'.repeat(Math.round(attr.rating || 4))}\n`;
      if (attr.type) plan += `   🏷️ ${attr.type}\n`;
      if (attr.address) plan += `   📍 ${attr.address}\n`;
      plan += `\n`;
    });
  } else {
    plan += `Your personalized attraction list is being prepared.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // ITINERARY SECTION
  plan += `## 📅 Your Day-by-Day Adventure\n\n`;
  plan += `*Here's your personalized itinerary - each day crafted for maximum enjoyment!*\n\n`;
  
  const itineraryData = results.itinerary;
  if (itineraryData?.success && itineraryData.itinerary?.length > 0) {
    itineraryData.itinerary.forEach((day, idx) => {
      const dayNames = ['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth', 'Seventh'];
      const dayName = dayNames[idx] || `Day ${day.day}`;
      
      plan += `### ${dayName} Day • ${new Date(day.date).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}\n\n`;
      
      // Morning
      if (day.morning?.activity) {
        plan += `🌅 **Morning:** Start your day at ${day.morning.activity}\n`;
        if (day.morning.location) {
          plan += `   📍 *${day.morning.location}*\n`;
        }
        plan += `\n`;
      }
      
      // Lunch
      if (day.lunch?.restaurant) {
        plan += `🍴 **Lunch:** Savor the flavors at ${day.lunch.restaurant}\n`;
        if (day.lunch.cuisine) {
          plan += `   *Enjoy authentic ${day.lunch.cuisine}*\n`;
        }
        plan += `\n`;
      }
      
      // Afternoon
      if (day.afternoon?.activity) {
        plan += `☀️ **Afternoon:** Continue your adventure at ${day.afternoon.activity}\n`;
        if (day.afternoon.location) {
          plan += `   📍 *${day.afternoon.location}*\n`;
        }
        plan += `\n`;
      }
      
      // Dinner
      if (day.dinner?.restaurant) {
        plan += `🌙 **Dinner:** End your day with a delightful meal at ${day.dinner.restaurant}\n`;
        if (day.dinner.cuisine) {
          plan += `   *Experience exquisite ${day.dinner.cuisine}*\n`;
        }
        plan += `\n`;
      }
      
      plan += `\n`;
    });
  } else {
    plan += `Your customized daily itinerary will be ready soon!\n\n`;
  }
  
  plan += `---\n\n`;
  plan += `### 🎉 Ready for Adventure?\n\n`;
  plan += `Your vacation plan is all set! Get ready to create unforgettable memories.\n\n`;
  plan += `*Bon voyage! Safe travels and enjoy every moment!* ✈️🌍✨\n`;
  
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
    message: 'Vacation Planner API (Production HIL + Clarification)',
    timestamp: new Date().toISOString()
  });
});

/**
 * PLAN VACATION WITH AGENTS ENDPOINT - PRODUCTION HIL VERSION + STEP 3 CLARIFICATION
 * 
 * This endpoint now supports:
 * 1. Human-in-the-Loop (HIL) interactions
 * 2. Intelligent clarification requests (STEP 3)
 * 
 * Flow:
 * 1. User sends prompt
 * 2. Backend forwards to Python orchestrator
 * 3a. Orchestrator may request CLARIFICATION (STEP 3 NEW)
 *     → Frontend displays questions
 *     → User provides answers
 *     → Call this endpoint again with clarification_response
 * 3b. Orchestrator may PAUSE for HIL and return recommendations
 *     → Frontend displays recommendations
 *     → User makes choice
 *     → Frontend calls /api/resume with choice
 * 4. Process continues until complete
 * 
 * @route POST /api/plan-vacation-agents
 * @body {string} prompt - The raw user input
 * @body {string} clarification_response - (STEP 3) User's answers to clarification questions
 * @returns {Object} Either:
 *   - {status: "clarification_needed", questions: [...]}  (STEP 3 NEW)
 *   - {status: "awaiting_user_input", session_id, recommendations, ...}
 *   - {status: "complete", success: true, data: formatted_plan}
 *   - {status: "error", success: false, error: message}
 */
app.post('/api/plan-vacation-agents', async (req, res) => {
  try {
    const { prompt, clarification_response } = req.body;  // STEP 3: Added clarification_response
    
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
    if (clarification_response) {
      console.log('💬 Clarification response:', clarification_response);  // STEP 3
    }
    
    const pythonApiUrl = process.env.PYTHON_AGENT_API_URL || 'http://localhost:8081';
    
    console.log('🤖 Sending request to Python orchestrator...');
    
    // STEP 3: Include clarification_response if provided
    const requestBody = {
      user_prompt: prompt
    };
    
    if (clarification_response) {
      requestBody.clarification_response = clarification_response;
    }
    
    const orchestratorResponse = await fetch(`${pythonApiUrl}/api/agents/orchestrate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    });
    
    const orchestratorData = await orchestratorResponse.json();
    
    // ==========================================================================
    // STEP 3: Handle clarification needed FIRST (before HIL pause)
    // ==========================================================================
    
    // STEP 3 NEW: Case 0: Agent needs clarification from user
    if (orchestratorData.status === 'clarification_needed') {
      console.log('❓ Agent needs clarification:', orchestratorData.questions?.length, 'questions');
      
      // Forward clarification request to frontend
      return res.json({
        status: 'clarification_needed',
        questions: orchestratorData.questions || [],
        reasoning: orchestratorData.reasoning || '',
        missing_required: orchestratorData.missing_required || [],
        missing_optional: orchestratorData.missing_optional || []
      });
    }
    
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
    
    // Case 2: Orchestration complete - FIXED TO USE PYTHON'S FORMATTED TEXT
    if (orchestratorData.status === 'complete' && orchestratorData.success) {
      console.log('✅ Plan generated successfully!');
      
      // CRITICAL FIX: Use the formatted_itinerary from Python if available
      // The ItineraryAgent already created a beautiful formatted text
      let finalData = orchestratorData.data;
      
      if (!finalData || finalData.trim() === '') {
        console.log('⚠️ No formatted data from Python, using fallback formatter');
        const travelDetails = orchestratorData.travel_details || {};
        finalData = formatCompleteVacationPlan(
          orchestratorData.all_results || {}, 
          travelDetails
        );
      } else {
        console.log(`✅ Using formatted itinerary from Python (${finalData.length} chars)`);
      }
      
      return res.json({
        status: 'complete',
        success: true,
        data: finalData,
        message: 'Vacation plan ready',
        raw_results: orchestratorData.all_results,
        travel_details: orchestratorData.travel_details || {}
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
 * RESUME VACATION PLANNING ENDPOINT - PRODUCTION HIL
 * 
 * This endpoint handles user responses after an HIL pause.
 * 
 * @route POST /api/resume
 * @body {string} session_id - Session ID from the pause response
 * @body {Object} user_decision - User's decision
 * @returns {Object} Same as /api/plan-vacation-agents
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
    
    // Case 2: Orchestration complete - FIXED TO USE PYTHON'S FORMATTED TEXT
    if (resumeData.status === 'complete' && resumeData.success) {
      console.log('✅ Orchestration completed after resume!');
      
      // CRITICAL FIX: Use the formatted_itinerary from Python if available
      let finalData = resumeData.data;
      
      if (!finalData || finalData.trim() === '') {
        console.log('⚠️ No formatted data from Python, using fallback formatter');
        const travelDetails = resumeData.travel_details || {};
        finalData = formatCompleteVacationPlan(
          resumeData.all_results || {}, 
          travelDetails
        );
      } else {
        console.log(`✅ Using formatted itinerary from Python (${finalData.length} chars)`);
      }
      
      return res.json({
        status: 'complete',
        success: true,
        data: finalData,
        message: 'Vacation plan ready',
        raw_results: resumeData.all_results,
        travel_details: resumeData.travel_details || {}
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
  console.log(`\n🚀 Vacation Planner API (Production HIL + Clarification)`);
  console.log(`📍 http://localhost:${PORT}`);
  console.log(`🔐 Auth: Email-based`);
  console.log(`🤖 Agentic Mode: Enabled`);
  console.log(`⏸️  HIL Support: Production-ready pause/resume`);
  console.log(`❓ Clarification: Intelligent question system (STEP 3)\n`);
});