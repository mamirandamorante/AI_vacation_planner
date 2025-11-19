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

// Initialize Gemini AI
let model = null;
if (process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'your-gemini-api-key') {
  const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
  model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" }); // More stable than 2.5
  console.log('✅ Gemini AI initialized');
} else {
  console.log('⚠️  Gemini API key not set - using mock responses');
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

// Simple fallback parser when Gemini is unavailable
function simpleFallbackParser(prompt) {
  console.log('🔧 Using simple fallback parser...');
  
  const lower = prompt.toLowerCase();
  
  // Extract origin
  let origin = 'JFK';
  if (lower.includes('from new york') || lower.includes('from nyc')) origin = 'JFK';
  else if (lower.includes('from los angeles') || lower.includes('from la')) origin = 'LAX';
  else if (lower.includes('from san francisco')) origin = 'SFO';
  else if (lower.includes('from boston')) origin = 'BOS';
  
  // Extract destination
  let destination = null;
  if (lower.includes('to madrid') || lower.includes('madrid')) destination = 'MAD';
  else if (lower.includes('to barcelona') || lower.includes('barcelona')) destination = 'BCN';
  else if (lower.includes('to paris') || lower.includes('paris')) destination = 'CDG';
  else if (lower.includes('to london') || lower.includes('london')) destination = 'LHR';
  else if (lower.includes('to los angeles') || lower.includes('to la')) destination = 'LAX';
  
  // Extract dates
  let departure_date = '2025-12-01';
  if (lower.includes('december')) departure_date = '2025-12-01';
  else if (lower.includes('january')) departure_date = '2026-01-15';
  
  // Extract duration
  let days = 7;
  const daysMatch = prompt.match(/(\d+)\s*days?/i);
  if (daysMatch) days = parseInt(daysMatch[1]);
  
  const departDate = new Date(departure_date);
  departDate.setDate(departDate.getDate() + days);
  const return_date = departDate.toISOString().split('T')[0];
  
  if (!destination) {
    return {
      success: false,
      needs_clarification: true,
      missing_fields: ['destination'],
      parsed_data: {}
    };
  }
  
  return {
    success: true,
    has_sufficient_info: true,
    origin,
    destination,
    departure_date,
    return_date,
    passengers: 2,
    budget: null,
    preferences: {}
  };
}

// Function to parse natural language prompt using Gemini
async function parseVacationPrompt(prompt) {
  console.log('🧠 Parsing prompt with Gemini AI...');
  
  if (!model) {
    console.log('⚠️  Gemini not available, using fallback');
    return simpleFallbackParser(prompt);
  }
  
  const parsePrompt = `You are a travel planning assistant. Extract structured information from the user's travel request.

User request: "${prompt}"

Extract the following information and respond ONLY with a JSON object (no markdown, no explanation):

{
  "has_sufficient_info": true/false,
  "missing_fields": [],
  "origin": "airport code or null",
  "destination": "airport code or null",
  "departure_date": "YYYY-MM-DD or null",
  "return_date": "YYYY-MM-DD or null",
  "passengers": number,
  "budget": number or null,
  "preferences": {
    "hotel_rating": number or null,
    "flight_class": "economy/business/first" or null,
    "max_stops": number or null
  }
}

EXTRACTION RULES:
- "New York", "NYC", "from New York" → origin: "JFK"
- "Madrid", "to Madrid" → destination: "MAD"
- "Los Angeles", "LA" → "LAX"
- "Barcelona" → "BCN"
- "Paris" → "CDG"
- "London" → "LHR"
- "December" with no specific date → use December 1st of current year
- "5 days" means trip duration - calculate return_date as departure + 5 days
- If origin AND destination are clearly mentioned → has_sufficient_info: true
- If dates are vague (like "December"), make reasonable assumptions
- Default passengers: 2 if not mentioned

IMPORTANT: 
- Be lenient - if you can identify origin and destination, set has_sufficient_info: true
- Make reasonable date assumptions rather than marking as missing
- Only set has_sufficient_info: false if origin OR destination is truly unclear

Current date: ${new Date().toISOString().split('T')[0]}

Respond ONLY with valid JSON, no markdown formatting.`;

  try {
    // Retry up to 3 times
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        console.log(`Attempt ${attempt}/3...`);
        const result = await model.generateContent(parsePrompt);
        const response = await result.response;
        let text = response.text();
        
        // Clean up the response
        text = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
        
        // Parse JSON
        const parsed = JSON.parse(text);
        
        console.log('✅ Parsed travel details:', parsed);
        
        // Check if we have sufficient information
        if (parsed.has_sufficient_info === false || !parsed.origin || !parsed.destination) {
          console.log('⚠️  Missing critical information');
          return {
            success: false,
            needs_clarification: true,
            missing_fields: parsed.missing_fields || [],
            parsed_data: parsed
          };
        }
        
        return {
          success: true,
          ...parsed
        };
        
      } catch (err) {
        if (attempt < 3) {
          console.log(`⚠️  Attempt ${attempt} failed, retrying...`);
          await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second
        } else {
          throw err; // Last attempt failed
        }
      }
    }
    
  } catch (error) {
    console.error('❌ All Gemini attempts failed');
    console.error('Gemini error:', error);
    return simpleFallbackParser(prompt);
  }
}

// Helper function to convert city names to airport codes
function convertToAirportCode(city) {
  const cityToCode = {
    // US Cities
    'new york': 'JFK',
    'nyc': 'JFK',
    'los angeles': 'LAX',
    'la': 'LAX',
    'chicago': 'ORD',
    'san francisco': 'SFO',
    'miami': 'MIA',
    'boston': 'BOS',
    'seattle': 'SEA',
    'las vegas': 'LAS',
    // European Cities
    'london': 'LHR',
    'paris': 'CDG',
    'madrid': 'MAD',
    'barcelona': 'BCN',
    'rome': 'FCO',
    'amsterdam': 'AMS',
    'berlin': 'BER',
    // Asian Cities
    'tokyo': 'NRT',
    'singapore': 'SIN',
    'hong kong': 'HKG',
    'dubai': 'DXB',
    'bangkok': 'BKK'
  };
  
  const lower = city.toLowerCase();
  return cityToCode[lower] || city.toUpperCase();
}

// Format complete vacation plan with all agents' results
function formatCompleteVacationPlan(results, travelDetails) {
  let plan = `# 🌍 Your Complete Vacation Plan\n\n`;
  plan += `**Trip:** ${travelDetails.origin} → ${travelDetails.destination}\n`;
  plan += `**Dates:** ${travelDetails.departure_date} to ${travelDetails.return_date}\n`;
  plan += `**Travelers:** ${travelDetails.passengers} ${travelDetails.passengers === 1 ? 'person' : 'people'}\n`;
  if (travelDetails.budget) {
    plan += `**Budget:** $${travelDetails.budget}\n`;
  }
  plan += `\n---\n\n`;
  
  // FLIGHTS
  plan += `## ✈️ Flights\n\n`;
  const flightData = results.flights;
  if (flightData?.success && flightData.flights?.length > 0) {
    plan += `${flightData.summary}\n\n`;
    flightData.flights.slice(0, 3).forEach((flight, i) => {
      plan += `**Option ${i + 1}** - $${flight.price} ${flight.currency}\n`;
      plan += `- ${flight.outbound.airline}: ${flight.outbound.from} → ${flight.outbound.to}\n`;
      plan += `  Departs: ${flight.outbound.departure} | Stops: ${flight.outbound.stops}\n\n`;
    });
  } else {
    plan += `Flight information unavailable.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // HOTELS
  plan += `## 🏨 Hotels\n\n`;
  const hotelData = results.hotels;
  if (hotelData?.success && hotelData.hotels?.length > 0) {
    hotelData.hotels.slice(0, 3).forEach((hotel, i) => {
      plan += `**${i + 1}. ${hotel.name}** ${'⭐'.repeat(hotel.rating)}\n`;
      plan += `- $${hotel.price}/night | ${hotel.room_type}\n\n`;
    });
  } else {
    plan += `Hotel recommendations unavailable.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // RESTAURANTS
  plan += `## 🍽️ Restaurants\n\n`;
  const restaurantData = results.restaurants;
  if (restaurantData?.success && restaurantData.restaurants?.length > 0) {
    restaurantData.restaurants.slice(0, 5).forEach((rest, i) => {
      plan += `**${i + 1}. ${rest.name}** ⭐ ${rest.rating}\n`;
      plan += `- ${rest.cuisine} | ${'$'.repeat(rest.price)}\n\n`;
    });
  } else {
    plan += `Restaurant recommendations unavailable.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // ATTRACTIONS
  plan += `## 🎭 Things to Do\n\n`;
  const attractionData = results.attractions;
  if (attractionData?.success && attractionData.attractions?.length > 0) {
    attractionData.attractions.slice(0, 5).forEach((attr, i) => {
      plan += `**${i + 1}. ${attr.name}** ⭐ ${attr.rating}\n`;
      plan += `- ${attr.type} | ${attr.price}\n\n`;
    });
  } else {
    plan += `Attraction recommendations unavailable.\n\n`;
  }
  
  plan += `---\n\n`;
  
  // ITINERARY
  plan += `## 📅 Day-by-Day Itinerary\n\n`;
  const itineraryData = results.itinerary;
  if (itineraryData?.success && itineraryData.itinerary?.length > 0) {
    itineraryData.itinerary.forEach((day) => {
      plan += `### Day ${day.day} - ${day.date}\n\n`;
      
      if (day.morning?.activity) {
        plan += `**Morning:** ${day.morning.activity}\n`;
        if (day.morning.location) plan += `📍 ${day.morning.location}\n`;
        plan += `\n`;
      }
      
      if (day.lunch?.restaurant) {
        plan += `**Lunch:** ${day.lunch.restaurant}\n`;
        if (day.lunch.cuisine) plan += `🍽️ ${day.lunch.cuisine}\n`;
        plan += `\n`;
      }
      
      if (day.afternoon?.activity) {
        plan += `**Afternoon:** ${day.afternoon.activity}\n`;
        if (day.afternoon.location) plan += `📍 ${day.afternoon.location}\n`;
        plan += `\n`;
      }
      
      if (day.dinner?.restaurant) {
        plan += `**Dinner:** ${day.dinner.restaurant}\n`;
        if (day.dinner.cuisine) plan += `🍽️ ${day.dinner.cuisine}\n`;
        plan += `\n`;
      }
      
      plan += `\n`;
    });
  } else {
    plan += `Itinerary will be generated based on your preferences.\n\n`;
  }
  
  plan += `---\n\n`;
  plan += `*Complete vacation plan powered by AI Multi-Agent System*`;
  
  return plan;
}

// =============================================================================
// ENDPOINTS
// =============================================================================

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    message: 'Vacation Planner API is running!',
    timestamp: new Date().toISOString()
  });
});

// Original endpoint (uses just Gemini)
app.post('/api/plan-vacation', async (req, res) => {
  try {
    const { prompt } = req.body;
    
    if (!prompt) {
      return res.status(400).json({ 
        success: false, 
        error: 'Prompt is required' 
      });
    }
    
    console.log('📝 Received planning request:', prompt);
    
    if (model) {
      const result = await model.generateContent(prompt);
      const response = await result.response;
      const text = response.text();
      
      res.json({ 
        success: true, 
        data: text,
        message: 'Vacation plan generated successfully'
      });
    } else {
      res.json({ 
        success: true, 
        data: `Mock vacation plan for: ${prompt}\n\nThis is a test response. Configure your Gemini API key to get real AI-powered results!`,
        message: 'Mock response (configure Gemini API key for real results)'
      });
    }
    
  } catch (error) {
    console.error('❌ Error planning vacation:', error);
    res.status(500).json({ 
      success: false, 
      error: error.message 
    });
  }
});

// NEW ENDPOINT: Plan vacation using Orchestrator Agent
app.post('/api/plan-vacation-agents', async (req, res) => {
  try {
    const { prompt } = req.body;
    
    console.log('📝 Received vacation planning request:', prompt);
    
    // STEP 1: Parse the prompt with Gemini
    const travelDetails = await parseVacationPrompt(prompt);
    
    // Check if we need more information
    if (!travelDetails.success && travelDetails.needs_clarification) {
      console.log('⚠️  Insufficient information, asking user for clarification');
      
      let clarificationMessage = `I'd love to help you plan your trip! However, I need a bit more information:\n\n`;
      
      if (!travelDetails.parsed_data?.origin) {
        clarificationMessage += `- **Where are you traveling FROM?** (e.g., "from New York", "departing from San Francisco")\n`;
      }
      if (!travelDetails.parsed_data?.destination) {
        clarificationMessage += `- **Where do you want to GO?** (e.g., "to Madrid", "visit Paris")\n`;
      }
      if (!travelDetails.parsed_data?.departure_date) {
        clarificationMessage += `- **When do you want to travel?** (e.g., "in December", "leaving January 15")\n`;
      }
      
      clarificationMessage += `\nPlease provide these details and I'll create your perfect vacation plan! 🌍✈️`;
      
      return res.json({
        success: false,
        needs_clarification: true,
        data: clarificationMessage,
        message: 'Need more information from user'
      });
    }
    
    // Convert city names to airport codes
    const origin = convertToAirportCode(travelDetails.origin);
    const destination = convertToAirportCode(travelDetails.destination);
    
    // Set default dates if not provided
    const today = new Date();
    const twoWeeksFromNow = new Date(today);
    twoWeeksFromNow.setDate(today.getDate() + 14);
    const oneWeekLater = new Date(twoWeeksFromNow);
    oneWeekLater.setDate(twoWeeksFromNow.getDate() + 7);
    
    const departure_date = travelDetails.departure_date || twoWeeksFromNow.toISOString().split('T')[0];
    const return_date = travelDetails.return_date || oneWeekLater.toISOString().split('T')[0];
    
    console.log(`✈️  Planning trip: ${origin} → ${destination}`);
    console.log(`📅 Dates: ${departure_date} to ${return_date}`);
    
    // STEP 2: Call Orchestrator Agent (it handles everything!)
    console.log('🧠 Calling Orchestrator Agent...');
    const pythonApiUrl = process.env.PYTHON_AGENT_API_URL || 'http://localhost:8081';
    const orchestratorResponse = await fetch(`${pythonApiUrl}/api/agents/orchestrate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        origin: origin,
        destination: destination,
        departure_date: departure_date,
        return_date: return_date,
        passengers: travelDetails.passengers || 2,
        budget: travelDetails.budget || 2000,
        preferences: {
          min_rating: travelDetails.preferences?.hotel_rating || 3,
          max_stops: travelDetails.preferences?.max_stops || 2,
          flight_class: travelDetails.preferences?.flight_class || 'economy'
        }
      })
    });
    
    const orchestratorData = await orchestratorResponse.json();
    
    if (!orchestratorData.success) {
      throw new Error(`Orchestrator error: ${orchestratorData.error}`);
    }
    
    console.log('✅ Orchestrator completed successfully!');
    
    // STEP 3: Format the complete vacation plan
    const response = {
      success: true,
      data: formatCompleteVacationPlan(orchestratorData.results, {
        origin: origin,
        destination: destination,
        departure_date: departure_date,
        return_date: return_date,
        passengers: travelDetails.passengers || 2,
        budget: travelDetails.budget
      }),
      message: 'Complete vacation plan generated by Orchestrator Agent'
    };
    
    res.json(response);
    
  } catch (error) {
    console.error('❌ Error planning vacation:', error);
    res.status(500).json({ 
      success: false, 
      error: error.message 
    });
  }
});

// =============================================================================
// START SERVER
// =============================================================================

app.listen(PORT, () => {
  console.log(`\n🚀 Vacation Planner API Server`);
  console.log(`📍 Running on: http://localhost:${PORT}`);
  console.log(`🏥 Health check: http://localhost:${PORT}/health`);
  console.log(`\n✨ Ready to plan vacations!\n`);
});