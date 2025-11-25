# 🌍 AI Vacation Planner

A production-ready AI-powered vacation planning system using multi-agent architecture with Human-in-the-Loop (HIL) capabilities.

## ✨ Features

- **Two-Phase HIL**: Users make critical decisions (flight/hotel), system auto-completes the rest
- **Autonomous Error Correction**: Agents self-correct API parameter errors
- **Real API Integration**: 
  - Amadeus API for flights and hotels
  - Google Places API for restaurants and attractions
- **Multi-Agent Architecture**: Specialized agents with LLM-driven decision making
- **Production-Ready**: Complete session management and state handling

## 🏗️ Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                      │
│                   Port 3000                              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              Node.js Backend (Express)                   │
│                   Port 8080                              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│           Python Agent System (Flask)                    │
│                   Port 8081                              │
│                                                          │
│  ┌──────────────────────────────────────────────┐      │
│  │         OrchestratorAgent                     │      │
│  └─────┬────────────────────────────────────────┘      │
│        │                                                 │
│  ┌─────▼──────┐  ┌──────────┐  ┌─────────────┐        │
│  │FlightAgent │  │HotelAgent│  │RestaurantAgt│        │
│  └────────────┘  └──────────┘  └─────────────┘        │
│  ┌──────────────┐  ┌────────────────┐                  │
│  │AttractionsAgt│  │ItineraryAgent  │                  │
│  └──────────────┘  └────────────────┘                  │
└──────────────────────────────────────────────────────────┘
```

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- API Keys:
  - Amadeus API (flights/hotels)
  - Google Places API (restaurants/attractions)
  - Google Gemini API (LLM)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/YOUR_USERNAME/AI_vacation_planner.git
cd AI_vacation_planner
```

2. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. **Install Python dependencies**
```bash
cd backend/agents
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

4. **Install Node.js dependencies**
```bash
cd ../  # backend directory
npm install

cd ../frontend
npm install
```

### Running the Application

**Terminal 1 - Python Agents (Port 8081):**
```bash
cd backend/agents
source venv/bin/activate
python main.py
```

**Terminal 2 - Node.js Backend (Port 8080):**
```bash
cd backend
node server.js
```

**Terminal 3 - React Frontend (Port 3000):**
```bash
cd frontend
npm run dev
```

Open http://localhost:3000 in your browser!

## 📖 How It Works

### Phase 1: Critical Decisions (HIL)
1. User submits trip request
2. **FlightAgent** searches Amadeus API → Shows 3 options → User selects
3. **HotelAgent** searches Amadeus API → Shows 3 options → User selects

### Phase 2: Automatic Completion
4. **RestaurantAgent** auto-selects top restaurants near hotel
5. **AttractionsAgent** auto-selects top attractions near hotel
6. **ItineraryAgent** generates day-by-day plan with real data

### Result: Complete Vacation Plan
✈️ Flight details  
🏨 Hotel booking  
🍽️ Restaurant recommendations  
🎭 Things to do  
📅 Day-by-day itinerary

## 🔧 Configuration

See `.env.example` for required environment variables.

## 🧪 Testing
```bash
# Test Flask endpoint
curl -X POST http://localhost:8081/api/agents/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"user_prompt": "Plan a trip to Madrid Dec 10-15, 2025"}'
```

## 📝 License

MIT

## 🙏 Acknowledgments

- Amadeus API for flight and hotel data
- Google Places API for restaurant and attraction data
- Google Gemini for LLM capabilities
