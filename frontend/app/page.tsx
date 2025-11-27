"use client";

/**
 * VACATION PLANNER UI - WITH STEP 3 CLARIFICATION SUPPORT
 * 
 * FEATURES:
 * - Step 3: Intelligent clarification system for incomplete prompts
 * - HIL support for flight/hotel selection
 * - Progressive loading messages
 * - Beautiful itinerary formatting
 * - Authentication disabled for demo mode
 * 
 * STEP 3 ADDITIONS:
 * - Detects clarification_needed status
 * - Displays clarification questions in a modal
 * - Resubmits with user's clarification answers
 * - Seamless flow: Clarification → HIL → Complete
 */

import { useEffect, useState } from "react";
import { useSession, signIn, signOut } from "next-auth/react";

// Type definitions for HIL responses
type FlightRecommendation = {
  id: string;
  price: number;
  currency: string;
  outbound: {
    airline: string;
    flight: string;
    from: string;
    to: string;
    departure: string;
    arrival: string;
    duration: string;
    stops: number;
  };
  return?: {
    airline: string;
    flight: string;
    from: string;
    to: string;
    departure: string;
    arrival: string;
    duration: string;
    stops: number;
  };
};

// STEP 3: Updated PlanningState to include clarification_needed
type PlanningState = 
  | { status: 'idle' }
  | { status: 'loading'; currentAgent?: string }
  | { status: 'clarification_needed'; questions: string[]; reasoning: string; missing_required: string[]; missing_optional: string[] }  // STEP 3: NEW
  | { status: 'awaiting_input'; sessionId: string; agent: string; itemType: string; recommendations: any[]; summary: string }
  | { status: 'complete'; result: string }
  | { status: 'error'; message: string };

export default function Home() {
  const { data: session, status } = useSession();
  const [prompt, setPrompt] = useState("");
  const [planningState, setPlanningState] = useState<PlanningState>({ status: 'idle' });
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [refinementFeedback, setRefinementFeedback] = useState("");
  
  // STEP 3: New state for clarification
  const [clarificationAnswers, setClarificationAnswers] = useState("");
  const [originalPrompt, setOriginalPrompt] = useState("");

  // AUTHENTICATION DISABLED - Bypass auth for demo mode
  useEffect(() => {
    setAuthToken('demo@vacation-planner.ai');
  }, []);

  // STEP 3: Updated handleSubmit to support clarification_response
  const handleSubmit = async (e: React.FormEvent, clarificationResponse?: string) => {
    e.preventDefault();

    if (!prompt.trim()) {
      alert("Please describe your dream vacation");
      return;
    }

    // Store original prompt for clarification resubmission
    if (!clarificationResponse) {
      setOriginalPrompt(prompt);
    }

    // Start with FlightAgent (or clarification if needed)
    setPlanningState({ status: 'loading', currentAgent: 'FlightAgent' });

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";
      
      // STEP 3: Build request body with optional clarification_response
      const requestBody: any = { prompt };
      if (clarificationResponse) {
        requestBody.clarification_response = clarificationResponse;
      }
      
      const response = await fetch(`${backendUrl}/api/plan-vacation-agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: authToken ? `Bearer ${authToken}` : "",
        },
        body: JSON.stringify(requestBody),
      });

      const data = await response.json();
      console.log('📦 Backend response:', data);
      handlePlanningResponse(data);

    } catch (error) {
      console.error("Request error:", error);
      setPlanningState({
        status: 'error',
        message: "Unable to connect to the server. Please check that all services are running."
      });
    }
  };

  // STEP 3: Updated to handle clarification_needed
  const handlePlanningResponse = (data: any) => {
    console.log('🔍 Processing response with status:', data.status);
    
    // STEP 3: Handle clarification needed FIRST (before other checks)
    if (data.status === 'clarification_needed') {
      console.log('❓ Clarification needed:', data.questions?.length, 'questions');
      setPlanningState({
        status: 'clarification_needed',
        questions: data.questions || [],
        reasoning: data.reasoning || '',
        missing_required: data.missing_required || [],
        missing_optional: data.missing_optional || []
      });
      return;
    }
    
    // Handle error responses
    if (data.status === 'error' || (data.success === false && data.status !== 'awaiting_user_input')) {
      setPlanningState({
        status: 'error',
        message: data.message || data.error || "Planning failed. Please try again."
      });
      return;
    }

    // Handle HIL pause
    if (data.status === 'awaiting_user_input') {
      console.log('⏸️ HIL pause detected for:', data.agent);
      setPlanningState({
        status: 'awaiting_input',
        sessionId: data.session_id,
        agent: data.agent,
        itemType: data.item_type,
        recommendations: data.recommendations || [],
        summary: data.summary || ""
      });
      return;
    }

    // Handle completion
    if (data.status === 'complete' && data.success) {
      console.log('✅ Plan complete!');
      setPlanningState({
        status: 'complete',
        result: data.data
      });
      return;
    }

    // Unexpected response
    console.warn('⚠️ Unexpected response:', data);
    setPlanningState({
      status: 'error',
      message: "Received unexpected response from server."
    });
  };

  // STEP 3: New function to handle clarification submission
  const handleSubmitClarification = async () => {
    if (!clarificationAnswers.trim()) {
      alert('Please provide your answers before continuing');
      return;
    }

    console.log('💬 Submitting clarification:', clarificationAnswers);
    
    // Clear clarification UI and show loading
    setPlanningState({ status: 'loading', currentAgent: 'FlightAgent' });
    
    // Resubmit with original prompt + clarification
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";
      
      const response = await fetch(`${backendUrl}/api/plan-vacation-agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: authToken ? `Bearer ${authToken}` : "",
        },
        body: JSON.stringify({
          prompt: originalPrompt,
          clarification_response: clarificationAnswers
        }),
      });

      const data = await response.json();
      console.log('📦 Clarification response:', data);
      
      // Clear clarification answers
      setClarificationAnswers("");
      
      handlePlanningResponse(data);

    } catch (error) {
      console.error("Clarification error:", error);
      setPlanningState({
        status: 'error',
        message: "Failed to process your clarification."
      });
    }
  };

  /**
   * NEW: Simulate Phase 2 progress (Restaurant → Attractions → Itinerary)
   * This cycles through loading messages while backend processes Phase 2
   */
  const simulatePhase2Progress = () => {
    // After 3 seconds, show AttractionsAgent message
    setTimeout(() => {
      setPlanningState(prev => {
        if (prev.status === 'loading') {
          return { status: 'loading', currentAgent: 'AttractionsAgent' };
        }
        return prev;
      });
    }, 3000);

    // After 6 seconds, show ItineraryAgent message
    setTimeout(() => {
      setPlanningState(prev => {
        if (prev.status === 'loading') {
          return { status: 'loading', currentAgent: 'ItineraryAgent' };
        }
        return prev;
      });
    }, 6000);
  };

  const handleSelectRecommendation = async (selectedId: string) => {
    if (planningState.status !== 'awaiting_input') return;

    console.log('✅ User selected:', selectedId);
    
    // Determine next agent based on current agent
    const currentAgent = planningState.agent;
    let nextAgent = 'ItineraryAgent'; // default
    
    if (currentAgent === 'FlightAgent') {
      nextAgent = 'HotelAgent';
    } else if (currentAgent === 'HotelAgent') {
      // After hotel selection, Phase 2 begins (Restaurant, Attractions, Itinerary)
      nextAgent = 'RestaurantAgent';
    } else if (currentAgent === 'RestaurantAgent') {
      nextAgent = 'AttractionsAgent';
    } else if (currentAgent === 'AttractionsAgent') {
      nextAgent = 'ItineraryAgent';
    }
    
    setPlanningState({ status: 'loading', currentAgent: nextAgent });

    // NEW: If we're past HotelAgent, simulate progressive Phase 2 loading
    const isPhase2 = currentAgent === 'HotelAgent';
    if (isPhase2) {
      simulatePhase2Progress();
    }

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";
      
      const response = await fetch(`${backendUrl}/api/resume`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: authToken ? `Bearer ${authToken}` : "",
        },
        body: JSON.stringify({
          session_id: planningState.sessionId,
          user_decision: {
            status: "FINAL_CHOICE",
            selected_id: selectedId
          }
        }),
      });

      const data = await response.json();
      console.log('📦 Resume response:', data);
      handlePlanningResponse(data);

    } catch (error) {
      console.error("Resume error:", error);
      setPlanningState({
        status: 'error',
        message: "Failed to process your selection."
      });
    }
  };

  const handleRefine = async () => {
    if (planningState.status !== 'awaiting_input' || !refinementFeedback.trim()) return;

    console.log('🔄 Refining with feedback:', refinementFeedback);
    
    // Stay with same agent during refinement
    const currentAgent = planningState.agent;
    setPlanningState({ status: 'loading', currentAgent: currentAgent });

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";
      
      const response = await fetch(`${backendUrl}/api/resume`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: authToken ? `Bearer ${authToken}` : "",
        },
        body: JSON.stringify({
          session_id: planningState.sessionId,
          user_decision: {
            status: "REFINE_SEARCH",
            feedback: refinementFeedback
          }
        }),
      });

      const data = await response.json();
      console.log('📦 Refine response:', data);
      setRefinementFeedback("");
      handlePlanningResponse(data);

    } catch (error) {
      console.error("Refine error:", error);
      setPlanningState({
        status: 'error',
        message: "Failed to refine search."
      });
    }
  };

  /**
   * Get intelligent loading message based on current agent
   */
  const getLoadingMessage = () => {
    if (planningState.status !== 'loading') return "Planning your vacation...";
    
    switch (planningState.currentAgent) {
      case 'FlightAgent':
        return "🔍 Searching for the best flight options...";
      case 'HotelAgent':
        return "🏨 Finding perfect hotels for your stay...";
      case 'RestaurantAgent':
        return "🍽️ Discovering amazing restaurants...";
      case 'AttractionsAgent':
        return "🎭 Finding exciting attractions and activities...";
      case 'ItineraryAgent':
        return "📅 Creating your personalized day-by-day itinerary...";
      default:
        return "✨ Planning your perfect vacation...";
    }
  };

  /**
   * Convert markdown-style text to rich HTML
   */
  const formatItineraryText = (text: string) => {
    if (!text) return '';
    
    // Split into lines
    const lines = text.split('\n');
    const html: string[] = [];
    
    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];
      
      // Skip empty lines
      if (!line.trim()) {
        html.push('<br />');
        continue;
      }
      
      // Headers
      if (line.startsWith('### ')) {
        line = line.replace(/### (.+)/, '<h3 class="text-xl font-bold text-[#2d2a26] mt-6 mb-3">$1</h3>');
        html.push(line);
      } else if (line.startsWith('## ')) {
        line = line.replace(/## (.+)/, '<h2 class="text-2xl font-bold text-[#2d2a26] mt-8 mb-4">$1</h2>');
        html.push(line);
      } else if (line.startsWith('# ')) {
        line = line.replace(/# (.+)/, '<h1 class="text-3xl font-bold text-[#2d2a26] mb-4">$1</h1>');
        html.push(line);
      }
      // Horizontal rule
      else if (line.trim() === '---') {
        html.push('<hr class="my-6 border-[#e8e4df]" />');
      }
      // Bullet points
      else if (line.trim().startsWith('•')) {
        line = line.replace(/• (.+)/, '<div class="ml-4 mb-2 flex items-start"><span class="text-[#c17d3f] mr-2">•</span><span class="text-[#2d2a26]">$1</span></div>');
        html.push(line);
      }
      // Regular paragraphs
      else {
        html.push(`<p class="text-[#2d2a26] mb-2">${line}</p>`);
      }
    }
    
    let result = html.join('');
    
    // Format bold and italic (***text*** → bold + italic)
    result = result.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em class="text-[#c17d3f]">$1</em></strong>');
    
    // Format bold (**text**)
    result = result.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>');
    
    return result;
  };

  const resetPlanner = () => {
    setPlanningState({ status: 'idle' });
    setPrompt("");
    setRefinementFeedback("");
    setClarificationAnswers("");
    setOriginalPrompt("");
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-[#f5f3f0] via-[#faf8f5] to-[#f0ede8]">
      {/* Header */}
      <div className="container mx-auto px-4 py-8">
        <div className="flex flex-col items-center justify-center text-center mb-12">
          <h1 className="text-4xl font-bold text-[#2d2a26] mb-2">
            AI Vacation Planner
          </h1>
          <p className="text-[#6b6560] text-lg">Plan your perfect getaway with AI-powered recommendations</p>
        </div>

        {/* STEP 3: Clarification Modal */}
        {planningState.status === 'clarification_needed' && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-3xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="p-8">
                <div className="text-center mb-6">
                  <span className="text-6xl mb-4 block">🤔</span>
                  <h2 className="text-3xl font-bold text-[#2d2a26] mb-2">
                    We need a bit more information
                  </h2>
                  <p className="text-[#6b6560] text-lg">
                    To plan the perfect vacation, please answer these questions:
                  </p>
                </div>

                {/* Display reasoning if provided */}
                {planningState.reasoning && (
                  <div className="bg-[#faf8f5] border-l-4 border-[#c17d3f] p-4 mb-6 rounded-lg">
                    <p className="text-[#2d2a26] text-sm">
                      <strong>Why we're asking:</strong> {planningState.reasoning}
                    </p>
                  </div>
                )}

                {/* Questions List */}
                <div className="mb-6 space-y-4">
                  {planningState.questions.map((question, index) => (
                    <div key={index} className="bg-[#fdfcfb] border-2 border-[#e8e4df] rounded-xl p-4">
                      <p className="text-[#2d2a26]">
                        <strong className="text-[#c17d3f]">Q{index + 1}:</strong> {question}
                      </p>
                    </div>
                  ))}
                </div>

                {/* Answer Input */}
                <div className="mb-6">
                  <label className="block text-sm font-semibold text-[#2d2a26] mb-2">
                    Your answers:
                  </label>
                  <textarea
                    value={clarificationAnswers}
                    onChange={(e) => setClarificationAnswers(e.target.value)}
                    placeholder="Please provide your answers here...&#10;&#10;Example: 'From Santander, December 10-16, 2025, no dietary restrictions'"
                    className="w-full px-4 py-3 border-2 border-[#e8e4df] rounded-xl focus:outline-none focus:border-[#c4bdb5] text-[#2d2a26] placeholder-[#b0aaa4] min-h-[120px] resize-none bg-white"
                  />
                </div>

                {/* Action Buttons */}
                <div className="flex gap-3">
                  <button
                    onClick={resetPlanner}
                    className="flex-1 px-6 py-3 border-2 border-[#e8e4df] text-[#2d2a26] rounded-xl hover:bg-[#faf8f5] transition-all duration-200 font-medium"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSubmitClarification}
                    disabled={!clarificationAnswers.trim()}
                    className="flex-1 px-6 py-3 bg-gradient-to-r from-[#c17d3f] to-[#a86b32] text-white rounded-xl hover:from-[#d18d4f] hover:to-[#b87b42] disabled:from-[#d4cfc8] disabled:to-[#d4cfc8] disabled:cursor-not-allowed transition-all duration-200 font-medium shadow-md"
                  >
                    Continue Planning →
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Error State */}
        {planningState.status === 'error' && (
          <div className="max-w-3xl mx-auto mb-8">
            <div className="bg-red-50 border-2 border-red-200 rounded-2xl p-6">
              <div className="flex items-start gap-3">
                <span className="text-2xl">⚠️</span>
                <div className="flex-1">
                  <h3 className="font-semibold text-red-900 mb-1">Oops! Something went wrong</h3>
                  <p className="text-red-700">{planningState.message}</p>
                  <button
                    onClick={resetPlanner}
                    className="mt-4 px-5 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-all duration-200 font-medium"
                  >
                    Try Again
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Intelligent Loading State with Agent-Specific Messages */}
        {planningState.status === 'loading' && (
          <div className="max-w-3xl mx-auto mb-8">
            <div className="bg-white rounded-3xl shadow-lg border border-[#e8e4df] p-12">
              <div className="flex flex-col items-center justify-center space-y-6">
                <svg className="animate-spin h-16 w-16 text-[#c17d3f]" viewBox="0 0 24 24">
                  <circle 
                    className="opacity-25" 
                    cx="12" 
                    cy="12" 
                    r="10" 
                    stroke="currentColor" 
                    strokeWidth="4" 
                    fill="none" 
                  />
                  <path 
                    className="opacity-75" 
                    fill="currentColor" 
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" 
                  />
                </svg>
                <div className="text-center">
                  <p className="text-2xl font-semibold text-[#2d2a26] mb-2">
                    {getLoadingMessage()}
                  </p>
                  <p className="text-sm text-[#6b6560]">
                    This may take a few moments as our AI agents work their magic...
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* HIL Selection Interface */}
        {planningState.status === 'awaiting_input' && (
          <div className="max-w-5xl mx-auto mb-8">
            <div className="bg-white rounded-3xl shadow-lg border border-[#e8e4df] p-8">
              <h2 className="text-3xl font-bold text-[#2d2a26] mb-3">
                {planningState.itemType === 'flight' && '✈️ Choose Your Flight'}
                {planningState.itemType === 'hotel' && '🏨 Select Your Hotel'}
                {planningState.itemType === 'restaurant' && '🍽️ Pick Your Restaurants'}
                {planningState.itemType === 'attraction' && '🎭 Choose Your Activities'}
              </h2>
              <p className="text-[#6b6560] mb-8 text-lg">{planningState.summary}</p>

              {/* Recommendations Grid */}
              <div className="grid gap-5 mb-8">
                {planningState.recommendations.map((item: any) => (
                  <div
                    key={item.id}
                    className="border-2 border-[#e8e4df] rounded-2xl p-6 hover:border-[#c4bdb5] hover:shadow-xl transition-all duration-300 cursor-pointer bg-[#fdfcfb]"
                    onClick={() => handleSelectRecommendation(item.id)}
                  >
                    {/* Flight Card */}
                    {planningState.itemType === 'flight' && (
                      <div>
                        <div className="flex justify-between items-start mb-4">
                          <div>
                            <p className="font-bold text-xl text-[#2d2a26]">
                              {item.outbound.airline} {item.outbound.flight}
                            </p>
                            <p className="text-[#6b6560] mt-1">
                              {item.outbound.from} → {item.outbound.to}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-2xl font-bold text-[#c17d3f]">
                              ${item.price}
                            </p>
                            <p className="text-xs text-[#8b857f]">{item.currency}</p>
                          </div>
                        </div>
                        <div className="text-sm text-[#6b6560] space-y-1">
                          <p>✈️ Departure: {new Date(item.outbound.departure).toLocaleString()}</p>
                          <p>⏱️ Duration: {item.outbound.duration} | Stops: {item.outbound.stops}</p>
                        </div>
                        {item.return && (
                          <div className="mt-3 pt-3 border-t border-[#e8e4df] text-sm text-[#6b6560]">
                            <p>🔄 Return: {new Date(item.return.departure).toLocaleString()}</p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Hotel Card */}
                    {planningState.itemType === 'hotel' && (
                      <div>
                        <div className="flex justify-between items-start mb-2">
                          <div className="flex-1">
                            <p className="font-bold text-xl text-[#2d2a26]">{item.name}</p>
                            <p className="text-[#6b6560] text-sm mt-1">
                              {'⭐'.repeat(Math.round(item.rating || 3))} {item.rating}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-2xl font-bold text-[#c17d3f]">
                              ${item.price}
                            </p>
                            <p className="text-xs text-[#8b857f]">/night</p>
                          </div>
                        </div>
                        <p className="text-sm text-[#6b6560] mt-2">{item.room_type}</p>
                      </div>
                    )}

                    {/* Generic Card for other types */}
                    {planningState.itemType !== 'flight' && planningState.itemType !== 'hotel' && (
                      <div>
                        <p className="font-bold text-xl text-[#2d2a26]">{item.name || item.id}</p>
                        <p className="text-sm text-[#6b6560] mt-2">{JSON.stringify(item)}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Refinement Section */}
              <div className="border-t border-[#e8e4df] pt-6">
                <p className="text-sm font-semibold text-[#2d2a26] mb-3">
                  Want something different?
                </p>
                <div className="flex gap-3">
                  <input
                    type="text"
                    value={refinementFeedback}
                    onChange={(e) => setRefinementFeedback(e.target.value)}
                    placeholder="e.g., 'Show me cheaper options' or 'I prefer morning flights'"
                    className="flex-1 px-4 py-3 border-2 border-[#e8e4df] rounded-xl focus:outline-none focus:border-[#c4bdb5] bg-white text-[#2d2a26] placeholder-[#b0aaa4]"
                  />
                  <button
                    onClick={handleRefine}
                    disabled={!refinementFeedback.trim()}
                    className="px-6 py-3 bg-[#2d2a26] text-white rounded-xl hover:bg-[#3d3a36] disabled:bg-[#d4cfc8] disabled:cursor-not-allowed transition-all duration-200 font-medium shadow-md"
                  >
                    Refine
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Main Planning Interface */}
        <div className="max-w-3xl mx-auto">
          {planningState.status === 'idle' && (
            <form onSubmit={(e) => handleSubmit(e)} className="bg-white rounded-3xl shadow-lg border border-[#e8e4df] p-8">
              <label className="block text-lg font-semibold text-[#2d2a26] mb-4">
                Where would you like to go? ✈️
              </label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Tell us about your dream vacation... &#10;&#10;Example: 'Plan a 5-day family trip to Madrid from Santander, departing December 10th, 2025. Budget is 2000 euros for 2 adults.'"
                className="w-full px-5 py-4 border-2 border-[#e8e4df] rounded-2xl focus:outline-none focus:border-[#c4bdb5] text-[#2d2a26] placeholder-[#b0aaa4] min-h-[180px] resize-none bg-[#fdfcfb]"
                disabled={planningState.status === 'loading'}
              />
              <button
                type="submit"
                disabled={planningState.status === 'loading'}
                className="w-full mt-6 px-6 py-4 bg-gradient-to-r from-[#c17d3f] to-[#a86b32] text-white rounded-2xl hover:from-[#d18d4f] hover:to-[#b87b42] disabled:from-[#d4cfc8] disabled:to-[#d4cfc8] disabled:cursor-not-allowed transition-all duration-300 font-semibold text-lg shadow-lg"
              >
                ✨ Plan My Dream Vacation
              </button>
            </form>
          )}
        </div>

        {/* Results Display - Rich HTML formatting with button at the end */}
        {planningState.status === 'complete' && (
          <div className="max-w-5xl mx-auto">
            <div className="bg-white rounded-3xl shadow-lg border border-[#e8e4df] p-10">
              {/* Rich HTML formatting of itinerary */}
              <div 
                className="prose prose-lg max-w-none mb-8"
                dangerouslySetInnerHTML={{ __html: formatItineraryText(planningState.result) }}
              />
              
              {/* Button at the END with matching style */}
              <div className="flex justify-center pt-6 border-t border-[#e8e4df]">
                <button
                  onClick={resetPlanner}
                  className="px-8 py-4 bg-gradient-to-r from-[#c17d3f] to-[#a86b32] text-white rounded-2xl hover:from-[#d18d4f] hover:to-[#b87b42] transition-all duration-300 font-semibold text-lg shadow-lg"
                >
                  ✨ Plan Another Trip
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}