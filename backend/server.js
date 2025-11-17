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
  model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
  console.log('✅ Gemini AI initialized');
} else {
  console.log('⚠️  Gemini API key not set - using mock responses');
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

// Function to parse natural language prompt using Gemini
async function parseVacationPrompt(prompt) {
  console.log('🧠 Parsing prompt with Gemini AI...');
  
  if (!model) {
    console.log('⚠️  Gemini not available, using defaults');
    return {
      success: true,
      origin: 'JFK',
      destination: 'LAX',
      departure_date: '2025-12-01',
      return_date: '2025-12-08',
      passengers: 2,
      budget: 2000,
      preferences: {}
    };
  }
  
  const parsePrompt = `You are a travel planning assistant. Extract structured information from the user's travel request.

User request: "${prompt}"

Extract the following information and respond ONLY with a JSON object (no markdown, no explanation):

{
  "has_sufficient_info": true/false (false if critical info like origin or destination is missing),
  "missing_fields": ["origin", "destination", "dates"] (only if has_sufficient_info is false),
  "origin": "airport code or city (e.g., JFK, NYC, London) or null if not mentioned",
  "destination": "airport code or city (e.g., LAX, Paris, Tokyo) or null if not mentioned",
  "departure_date": "YYYY-MM-DD format or null if not mentioned",
  "return_date": "YYYY-MM-DD format or null for one-way or not mentioned",
  "passengers": number (default 2 if not mentioned),
  "budget": number in USD or null if not mentioned,
  "preferences": {
    "hotel_rating": number 1-5 or null,
    "flight_class": "economy/business/first" or null,
    "max_stops": number or null
  }
}

Rules:
- Set has_sufficient_info to FALSE if origin OR destination is missing/unclear
- Use null for any field that wasn't mentioned
- Use IATA codes when possible (NYC->JFK, LA->LAX, Madrid->MAD, etc.)
- If dates not mentioned, set to null
- Always return valid JSON

Respond ONLY with the JSON object, nothing else.`;

  try {
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
    
  } catch (error) {
    console.error('❌ Error parsing prompt:', error);
    return {
      success: false,
      needs_clarification: true,
      missing_fields: ['origin', 'destination', 'dates'],
      error: error.message
    };
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

// Helper function to format agent results for display
function formatVacationPlan(flightData, hotelData, travelDetails) {
  let plan = `# Your Complete Vacation Plan\n\n`;
  plan += `**Trip:** ${travelDetails.origin} → ${travelDetails.destination}\n`;
  plan += `**Dates:** ${travelDetails.departure_date}`;
  if (travelDetails.return_date) {
    plan += ` to ${travelDetails.return_date}`;
  }
  plan += `\n`;
  plan += `**Travelers:** ${travelDetails.passengers} ${travelDetails.passengers === 1 ? 'person' : 'people'}\n`;
  if (travelDetails.budget) {
    plan += `**Budget:** $${travelDetails.budget}\n`;
  }
  plan += `\n*Powered by AI Agents using Real-Time Data*\n\n`;
  plan += `---\n\n`;
  
  // FLIGHTS SECTION
  plan += `## ✈️ Flights\n\n`;
  
  if (flightData && flightData.success && flightData.flights && flightData.flights.length > 0) {
    plan += `${flightData.summary}\n\n`;
    plan += `### Flight Options:\n\n`;
    
    flightData.flights.slice(0, 3).forEach((flight, index) => {
      plan += `**Option ${index + 1}** - $${flight.price} ${flight.currency}\n`;
      plan += `- Outbound: ${flight.outbound.airline} ${flight.outbound.flight}\n`;
      plan += `  ${flight.outbound.from} → ${flight.outbound.to}\n`;
      plan += `  Departure: ${flight.outbound.departure}\n`;
      plan += `  Arrival: ${flight.outbound.arrival}\n`;
      plan += `  Stops: ${flight.outbound.stops}\n`;
      
      if (flight.return) {
        plan += `- Return: ${flight.return.airline} ${flight.return.flight}\n`;
        plan += `  ${flight.return.from} → ${flight.return.to}\n`;
        plan += `  Departure: ${flight.return.departure}\n`;
        plan += `  Arrival: ${flight.return.arrival}\n`;
        plan += `  Stops: ${flight.return.stops}\n`;
      }
      plan += `\n`;
    });
  } else {
    plan += `No flights found for this route. This might be because:\n`;
    plan += `- The route is not available in the Amadeus test database\n`;
    plan += `- The dates are too far in the future\n`;
    plan += `- There are no direct connections\n\n`;
  }
  
  plan += `\n---\n\n`;
  
  // HOTELS SECTION
  plan += `## 🏨 Hotels\n\n`;
  
  if (hotelData && hotelData.success && hotelData.hotels && hotelData.hotels.length > 0) {
    plan += `${hotelData.summary}\n\n`;
    plan += `### Hotel Recommendations:\n\n`;
    
    hotelData.hotels.slice(0, 3).forEach((hotel, index) => {
      plan += `**${index + 1}. ${hotel.name}**`;
      if (hotel.rating > 0) {
        plan += ` - ${'⭐'.repeat(hotel.rating)}`;
      }
      plan += `\n`;
      plan += `- Price: $${hotel.price} ${hotel.currency} per night\n`;
      plan += `- Room Type: ${hotel.room_type}\n`;
      plan += `\n`;
    });
  } else {
    plan += `Hotel recommendations will be added soon!\n\n`;
  }
  
  plan += `\n---\n\n`;
  plan += `## 📋 Next Steps\n\n`;
  plan += `1. Review the flight and hotel options above\n`;
  plan += `2. Book your preferred flight\n`;
  plan += `3. Reserve your hotel\n`;
  plan += `4. Start planning your activities!\n\n`;
  plan += `---\n\n`;
  plan += `*Generated by AI Agents powered by Google Gemini and Amadeus Travel APIs*`;
  
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

// NEW ENDPOINT: Plan vacation using Python agents with intelligent parsing
app.post('/api/plan-vacation-agents', async (req, res) => {
  try {
    const { prompt } = req.body;
    
    console.log('📝 Received vacation planning request:', prompt);
    
    // STEP 1: Parse the prompt with Gemini to extract travel details
    const travelDetails = await parseVacationPrompt(prompt);
    
    // Check if we need more information from the user
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
    
    // Convert city names to airport codes if needed
    const origin = convertToAirportCode(travelDetails.origin);
    const destination = convertToAirportCode(travelDetails.destination);
    
    // Set default dates if not provided (2 weeks from now)
    const today = new Date();
    const twoWeeksFromNow = new Date(today);
    twoWeeksFromNow.setDate(today.getDate() + 14);
    const oneWeekLater = new Date(twoWeeksFromNow);
    oneWeekLater.setDate(twoWeeksFromNow.getDate() + 7);
    
    const departure_date = travelDetails.departure_date || twoWeeksFromNow.toISOString().split('T')[0];
    const return_date = travelDetails.return_date || oneWeekLater.toISOString().split('T')[0];
    
    console.log(`✈️  Planning trip: ${origin} → ${destination}`);
    console.log(`📅 Dates: ${departure_date} to ${return_date}`);
    console.log(`👥 Passengers: ${travelDetails.passengers}`);
    
    // STEP 2: Call Flight Agent with parsed details
    console.log('✈️  Calling Flight Agent...');
    const flightResponse = await fetch('http://localhost:8081/api/agents/flight/search', {
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
          max_stops: travelDetails.preferences?.max_stops || 2,
          cabin: travelDetails.preferences?.flight_class || 'economy'
        }
      })
    });
    
    const flightData = await flightResponse.json();
    
    if (!flightData.success) {
      console.log('⚠️  Flight agent returned error:', flightData.error);
    } else {
      console.log(`✅ Flight Agent returned ${flightData.flights.length} flights`);
    }
    
    // STEP 3: Call Hotel Agent with parsed details
    console.log('🏨 Calling Hotel Agent...');
    
    const hotelResponse = await fetch('http://localhost:8081/api/agents/hotel/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        city_code: destination,
        check_in_date: departure_date,
        check_out_date: return_date,
        adults: travelDetails.passengers || 2,
        budget_per_night: travelDetails.budget ? Math.floor(travelDetails.budget / 5) : 300,
        preferences: {
          min_rating: travelDetails.preferences?.hotel_rating || 3
        }
      })
    });
    
    const hotelData = await hotelResponse.json();
    
    if (!hotelData.success) {
      console.log('⚠️  Hotel agent returned error, continuing without hotels');
    } else {
      console.log(`✅ Hotel Agent returned ${hotelData.hotels.length} hotels`);
    }
    
    // STEP 4: Format combined response for frontend
    const response = {
      success: true,
      data: formatVacationPlan(flightData, hotelData, {
        origin: origin,
        destination: destination,
        departure_date: departure_date,
        return_date: return_date,
        passengers: travelDetails.passengers || 2,
        budget: travelDetails.budget
      }),
      message: 'Vacation plan generated using AI agents',
      parsed_details: travelDetails
    };
    
    res.json(response);
    
  } catch (error) {
    console.error('❌ Error planning vacation with agents:', error);
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