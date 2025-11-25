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

const publicPaths = ['/health'];

app.use((req, res, next) => {
  // Allow public endpoints
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

  // Simple validation: check if it's an email
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

// Initialize Gemini AI
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

function simpleFallbackParser(prompt) {
  console.log('🔧 Using fallback parser...');
  
  const lower = prompt.toLowerCase();
  
  let origin = 'JFK';
  if (lower.includes('from santander')) origin = 'SDR';
  else if (lower.includes('from madrid')) origin = 'MAD';
  else if (lower.includes('from barcelona')) origin = 'BCN';
  else if (lower.includes('from new york') || lower.includes('from nyc')) origin = 'JFK';
  else if (lower.includes('from la') || lower.includes('from los angeles')) origin = 'LAX';
  
  let destination = null;
  if (lower.includes('to madrid') || (lower.includes('madrid') && !lower.includes('from madrid'))) destination = 'MAD';
  else if (lower.includes('to barcelona') || (lower.includes('barcelona') && !lower.includes('from barcelona'))) destination = 'BCN';
  else if (lower.includes('to paris')) destination = 'CDG';
  else if (lower.includes('to london')) destination = 'LHR';
  
  // Parse DD.MM.YYYY dates
  let departure_date = '2025-12-10';
  const dateMatch = prompt.match(/(\d{1,2})\.(\d{1,2})\.(\d{4})/);
  if (dateMatch) {
    const [, day, month, year] = dateMatch;
    departure_date = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
  }
  
  let days = 5;
  const daysMatch = prompt.match(/(\d+)\s*days?/i);
  if (daysMatch) days = parseInt(daysMatch[1]);
  
  const departDate = new Date(departure_date);
  departDate.setDate(departDate.getDate() + days);
  const return_date = departDate.toISOString().split('T')[0];
  
  console.log(`📍 ${origin} → ${destination} | ${departure_date} to ${return_date}`);
  
  if (!destination) {
    return {
      success: false,
      needs_clarification: true,
      missing_fields: ['destination']
    };
  }
  
  return {
    success: true,
    origin,
    destination,
    departure_date,
    return_date,
    passengers: 2,
    budget: null,
    preferences: {}
  };
}

async function parseVacationPrompt(prompt) {
  // Always use fallback for reliability
  return simpleFallbackParser(prompt);
}

function convertToAirportCode(city) {
  const codes = {
    'santander': 'SDR', 'madrid': 'MAD', 'barcelona': 'BCN',
    'new york': 'JFK', 'nyc': 'JFK', 'paris': 'CDG',
    'london': 'LHR', 'los angeles': 'LAX', 'la': 'LAX'
  };
  return codes[city?.toLowerCase()] || city?.toUpperCase();
}

function formatCompleteVacationPlan(results, travelDetails) {
  let plan = `# 🌍 Your Complete Vacation Plan\n\n`;
  plan += `**Trip:** ${travelDetails.origin} → ${travelDetails.destination}\n`;
  plan += `**Dates:** ${travelDetails.departure_date} to ${travelDetails.return_date}\n`;
  plan += `**Travelers:** ${travelDetails.passengers} people\n\n`;
  plan += `---\n\n`;
  
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
      plan += `**${i + 1}. ${hotel.name}** ${'⭐'.repeat(Math.min(hotel.rating, 5))}\n`;
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
      plan += `- ${rest.cuisine}\n\n`;
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
        if (day.morning.location) plan += `📍 ${day.morning.location}\n\n`;
      }
      if (day.lunch?.restaurant) {
        plan += `**Lunch:** ${day.lunch.restaurant}\n`;
        if (day.lunch.cuisine) plan += `🍽️ ${day.lunch.cuisine}\n\n`;
      }
      if (day.afternoon?.activity) {
        plan += `**Afternoon:** ${day.afternoon.activity}\n`;
        if (day.afternoon.location) plan += `📍 ${day.afternoon.location}\n\n`;
      }
      if (day.dinner?.restaurant) {
        plan += `**Dinner:** ${day.dinner.restaurant}\n`;
        if (day.dinner.cuisine) plan += `🍽️ ${day.dinner.cuisine}\n\n`;
      }
    });
  } else {
    plan += `Itinerary will be generated based on preferences.\n\n`;
  }
  
  plan += `---\n\n`;
  plan += `*Powered by AI Multi-Agent System*`;
  return plan;
}

// =============================================================================
// ENDPOINTS
// =============================================================================

app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    message: 'Vacation Planner API',
    timestamp: new Date().toISOString()
  });
});

app.post('/api/plan-vacation-agents', async (req, res) => {
  try {
    const { prompt } = req.body;
    console.log('📝 User:', req.user?.email);
    console.log('📝 Prompt:', prompt);
    
    const travelDetails = await parseVacationPrompt(prompt);
    
    if (!travelDetails.success) {
      return res.json({
        success: false,
        needs_clarification: true,
        data: 'Please provide origin, destination, and travel dates.',
        message: 'Need more information'
      });
    }
    
    const origin = convertToAirportCode(travelDetails.origin);
    const destination = convertToAirportCode(travelDetails.destination);
    
    console.log(`✈️  ${origin} → ${destination}`);
    console.log(`📅 ${travelDetails.departure_date} to ${travelDetails.return_date}`);
    
    const pythonApiUrl = process.env.PYTHON_AGENT_API_URL || 'http://localhost:8081';
    const orchestratorResponse = await fetch(`${pythonApiUrl}/api/agents/orchestrate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        origin,
        destination,
        departure_date: travelDetails.departure_date,
        return_date: travelDetails.return_date,
        passengers: travelDetails.passengers || 2,
        budget: travelDetails.budget || 2000,
        preferences: { min_rating: 3, max_stops: 2, flight_class: 'economy' }
      })
    });
    
    const orchestratorData = await orchestratorResponse.json();
    
    if (!orchestratorData.success) {
      throw new Error(orchestratorData.error || 'Orchestrator failed');
    }
    
    console.log('✅ Plan generated!');
    
    res.json({
      success: true,
      data: formatCompleteVacationPlan(orchestratorData.results, {
        origin,
        destination,
        departure_date: travelDetails.departure_date,
        return_date: travelDetails.return_date,
        passengers: travelDetails.passengers || 2,
        budget: travelDetails.budget
      }),
      message: 'Vacation plan ready'
    });
    
  } catch (error) {
    console.error('❌ Error:', error);
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
  console.log(`\n🚀 Vacation Planner API`);
  console.log(`📍 http://localhost:${PORT}`);
  console.log(`🔐 Auth: Email-based\n`);
});