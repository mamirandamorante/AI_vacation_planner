"use client";

/**
 * VACATION PLANNER UI - FINAL VERSION WITH COMPLETE STATE RESET
 * 
 * CRITICAL FIXES:
 * 1. Added renderKey state to force complete React re-render
 * 2. Enhanced logging to track recommendation data flow
 * 3. Force new array references to trigger React updates
 * 
 * This prevents old flight/hotel data from persisting when planning a new trip
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

type PlanningState = 
  | { status: 'idle' }
  | { status: 'loading'; currentAgent?: string }
  | { status: 'clarification_needed'; questions: string[]; reasoning: string; missing_required: string[]; missing_optional: string[] }
  | { status: 'awaiting_input'; sessionId: string; agent: string; itemType: string; recommendations: any[]; summary: string }
  | { status: 'complete'; result: string }
  | { status: 'error'; message: string };

export default function Home() {
  const { data: session, status } = useSession();
  const [prompt, setPrompt] = useState("");
  const [planningState, setPlanningState] = useState<PlanningState>({ status: 'idle' });
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [refinementFeedback, setRefinementFeedback] = useState("");
  const [clarificationAnswers, setClarificationAnswers] = useState("");
  const [originalPrompt, setOriginalPrompt] = useState("");
  
  // CRITICAL FIX: Add renderKey to force complete re-render
  const [renderKey, setRenderKey] = useState(0);

  // AUTHENTICATION DISABLED - Bypass auth for demo mode
  useEffect(() => {
    setAuthToken('demo@vacation-planner.ai');
  }, []);

  const handleSubmit = async (e: React.FormEvent, clarificationResponse?: string) => {
    e.preventDefault();

    if (!prompt.trim()) {
      alert("Please describe your dream vacation");
      return;
    }

    if (!clarificationResponse) {
      setOriginalPrompt(prompt);
    }

    setPlanningState({ status: 'loading', currentAgent: 'FlightAgent' });

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";
      
      const requestBody: any = { prompt };
      if (clarificationResponse) {
        requestBody.clarification_response = clarificationResponse;
      }
      
      console.log('🚀 Sending request to backend:', requestBody);
      
      const response = await fetch(`${backendUrl}/api/plan-vacation-agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-cache, no-store, must-revalidate",
          "Pragma": "no-cache",
          "Expires": "0",
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

  const handlePlanningResponse = (data: any) => {
    console.log('🔍 Processing response with status:', data.status);
    console.log('📊 Recommendations count:', data.recommendations?.length || 0);
    console.log('🔍 FULL DATA OBJECT:', JSON.stringify(data, null, 2));
    
    if (data.recommendations?.[0]) {
      console.log('✈️ First recommendation route:', data.recommendations[0].outbound?.from, '→', data.recommendations[0].outbound?.to);
      console.log('✈️ FIRST RECOMMENDATION FULL:', JSON.stringify(data.recommendations[0], null, 2));
    }
    
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
    
    if (data.status === 'error' || (data.success === false && data.status !== 'awaiting_user_input')) {
      setPlanningState({
        status: 'error',
        message: data.message || data.error || "Planning failed. Please try again."
      });
      return;
    }

    // CRITICAL: Create new array to force React update
    if (data.status === 'awaiting_user_input') {
      console.log('⏸️ HIL pause detected for:', data.agent);
      
      const newRecommendations = [...(data.recommendations || [])];
      console.log('🔄 Setting new recommendations array with', newRecommendations.length, 'items');
      console.log('🔄 NEW RECOMMENDATIONS ARRAY:', JSON.stringify(newRecommendations, null, 2));
      
      const newState = {
        status: 'awaiting_input' as const,
        sessionId: data.session_id,
        agent: data.agent,
        itemType: data.item_type,
        recommendations: newRecommendations,
        summary: data.summary || ""
      };
      
      console.log('🔄 SETTING PLANNING STATE TO:', JSON.stringify(newState, null, 2));
      setPlanningState(newState);
      
      // Verify it was set correctly
      setTimeout(() => {
        console.log('✅ VERIFY - planningState after setState:', planningState);
      }, 100);
      
      return;
    }

    if (data.status === 'complete' && data.success) {
      console.log('✅ Plan complete!');
      setPlanningState({
        status: 'complete',
        result: data.data
      });
      return;
    }

    console.warn('⚠️ Unexpected response:', data);
    setPlanningState({
      status: 'error',
      message: "Received unexpected response from server."
    });
  };

  const handleSubmitClarification = async () => {
    if (!clarificationAnswers.trim()) {
      alert('Please provide your answers before continuing');
      return;
    }

    console.log('💬 Submitting clarification:', clarificationAnswers);
    setPlanningState({ status: 'loading', currentAgent: 'FlightAgent' });
    
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";
      
      const response = await fetch(`${backendUrl}/api/plan-vacation-agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-cache, no-store, must-revalidate",
          "Pragma": "no-cache",
          "Expires": "0",
          Authorization: authToken ? `Bearer ${authToken}` : "",
        },
        body: JSON.stringify({
          prompt: originalPrompt,
          clarification_response: clarificationAnswers
        }),
      });

      const data = await response.json();
      console.log('📦 Clarification response:', data);
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

  const simulatePhase2Progress = () => {
    setTimeout(() => {
      setPlanningState(prev => {
        if (prev.status === 'loading') {
          return { status: 'loading', currentAgent: 'AttractionsAgent' };
        }
        return prev;
      });
    }, 3000);

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
    
    const currentAgent = planningState.agent;
    let nextAgent = 'ItineraryAgent';
    
    if (currentAgent === 'FlightAgent') {
      nextAgent = 'HotelAgent';
    } else if (currentAgent === 'HotelAgent') {
      nextAgent = 'RestaurantAgent';
    } else if (currentAgent === 'RestaurantAgent') {
      nextAgent = 'AttractionsAgent';
    } else if (currentAgent === 'AttractionsAgent') {
      nextAgent = 'ItineraryAgent';
    }
    
    setPlanningState({ status: 'loading', currentAgent: nextAgent });

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

  const formatItineraryText = (text: string) => {
    if (!text) return '';
    
    const lines = text.split('\n');
    const html: string[] = [];
    
    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];
      
      if (!line.trim()) {
        html.push('<br />');
        continue;
      }
      
      if (line.startsWith('### ')) {
        line = line.replace(/### (.+)/, '<h3 class="text-xl font-bold text-[#2d2a26] mt-6 mb-3">$1</h3>');
        html.push(line);
      } else if (line.startsWith('## ')) {
        line = line.replace(/## (.+)/, '<h2 class="text-2xl font-bold text-[#2d2a26] mt-8 mb-4">$1</h2>');
        html.push(line);
      } else if (line.startsWith('# ')) {
        line = line.replace(/# (.+)/, '<h1 class="text-3xl font-bold text-[#2d2a26] mb-4">$1</h1>');
        html.push(line);
      } else if (line.trim() === '---') {
        html.push('<hr class="my-6 border-[#e8e4df]" />');
      } else if (line.trim().startsWith('•')) {
        line = line.replace(/• (.+)/, '<div class="ml-4 mb-2 flex items-start"><span class="text-[#c17d3f] mr-2">•</span><span class="text-[#2d2a26]">$1</span></div>');
        html.push(line);
      } else {
        html.push(`<p class="text-[#2d2a26] mb-2">${line}</p>`);
      }
    }
    
    let result = html.join('');
    result = result.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em class="text-[#c17d3f]">$1</em></strong>');
    result = result.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>');
    
    return result;
  };

  /**
   * CRITICAL FIX: Reset ALL state AND increment renderKey
   */
  const resetPlanner = () => {
    const timestamp = Date.now();
    console.log(`🔄 [${timestamp}] Full state reset - incrementing renderKey from`, renderKey, 'to', renderKey + 1);
    
    // Reset all state
    setPlanningState({ status: 'idle' });
    setPrompt("");
    setRefinementFeedback("");
    setClarificationAnswers("");
    setOriginalPrompt("");
    
    // CRITICAL: Increment renderKey to force complete re-render
    setRenderKey(prev => prev + 1);
    
    // Force garbage collection by clearing any cached data
    if (typeof window !== 'undefined') {
      sessionStorage.clear();
      console.log(`✅ [${timestamp}] Session storage cleared`);
    }
    
    console.log(`✅ [${timestamp}] State reset complete - ready for new trip`);
  };

  return (
    <main key={renderKey} className="min-h-screen bg-gradient-to-br from-[#f5f3f0] via-[#faf8f5] to-[#f0ede8]">
      <div className="container mx-auto px-4 py-8">
        <div className="flex flex-col items-center justify-center text-center mb-12">
          <h1 className="text-4xl font-bold text-[#2d2a26] mb-2">
            AI Vacation Planner
          </h1>
          <p className="text-[#6b6560] text-lg">Plan your perfect getaway with AI-powered recommendations</p>
        </div>

        {/* Clarification Modal */}
        {planningState.status === 'clarification_needed' && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-3xl shadow-2xl max-w-2xl w-full p-8">
              <div className="mb-6">
                <h2 className="text-2xl font-bold text-[#2d2a26] mb-2">
                  ❓ Just a Few More Details
                </h2>
                <p className="text-[#6b6560]">
                  {planningState.reasoning}
                </p>
              </div>

              <div className="bg-[#faf8f5] rounded-xl p-6 mb-6">
                <h3 className="font-semibold text-[#2d2a26] mb-3">Please provide:</h3>
                <ul className="space-y-2">
                  {planningState.questions.map((question, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-[#2d2a26]">
                      <span className="text-[#c17d3f] font-bold">{idx + 1}.</span>
                      <span>{question}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="mb-6">
                <label className="block text-sm font-medium text-[#2d2a26] mb-2">
                  Your Answers:
                </label>
                <textarea
                  value={clarificationAnswers}
                  onChange={(e) => setClarificationAnswers(e.target.value)}
                  placeholder="Please provide your answers here...&#10;&#10;Example: 'From Santander, December 10-16, 2025, no dietary restrictions'"
                  className="w-full px-4 py-3 border-2 border-[#e8e4df] rounded-xl focus:outline-none focus:border-[#c4bdb5] text-[#2d2a26] placeholder-[#b0aaa4] min-h-[120px] resize-none bg-white"
                />
              </div>

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

        {/* Loading State */}
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
                  <p className="text-[#6b6560]">This may take a moment...</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* HIL Selection UI - CRITICAL: Use unique keys */}
        {planningState.status === 'awaiting_input' && (
          <div key={`hil-${renderKey}`} className="max-w-4xl mx-auto mb-8">
            <div className="bg-white rounded-3xl shadow-lg border border-[#e8e4df] p-8">
              {/* DEBUG INFO */}
              <div style={{display: 'none'}}>
                {console.log('🎨 RENDERING HIL UI with', planningState.recommendations.length, 'recommendations')}
                {planningState.recommendations.map((rec, i) => 
                  console.log(`🎨 Rec ${i}:`, rec.outbound?.from, '→', rec.outbound?.to, '$'+rec.price)
                )}
              </div>
              
              <h2 className="text-2xl font-bold text-[#2d2a26] mb-2">
                {planningState.itemType === 'flight' ? '✈️ Select Your Flight' : '🏨 Choose Your Hotel'}
              </h2>
              <p className="text-[#6b6560] mb-6">{planningState.summary}</p>
              
              <div className="space-y-4 mb-6">
                {planningState.recommendations.map((rec: any, idx: number) => (
                  <div 
                    key={`${rec.id}-${renderKey}-${idx}`}
                    onClick={() => handleSelectRecommendation(rec.id)}
                    className="border-2 border-[#e8e4df] rounded-xl p-5 hover:border-[#c17d3f] hover:shadow-md transition-all duration-200 cursor-pointer bg-[#fdfcfb]"
                  >
                    {planningState.itemType === 'flight' ? (
                      <div>
                        <div className="flex justify-between items-start mb-3">
                          <div>
                            <p className="font-semibold text-lg text-[#2d2a26]">{rec.outbound.from} → {rec.outbound.to}</p>
                            <p className="text-sm text-[#6b6560]">{rec.outbound.airline} • {rec.outbound.stops === 0 ? 'Direct' : `${rec.outbound.stops} stop(s)`}</p>
                          </div>
                          <p className="text-2xl font-bold text-[#c17d3f]">${rec.price}</p>
                        </div>
                        <div className="text-sm text-[#6b6560]">
                          <p>Departure: {new Date(rec.outbound.departure).toLocaleString()}</p>
                          <p>Duration: {rec.outbound.duration}</p>
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className="flex justify-between items-start mb-2">
                          <h3 className="font-semibold text-lg text-[#2d2a26]">{rec.name}</h3>
                          <p className="text-xl font-bold text-[#c17d3f]">${rec.price}/night</p>
                        </div>
                        <p className="text-sm text-[#6b6560] mb-2">Rating: {'⭐'.repeat(Math.round(rec.rating || 3))}</p>
                        <p className="text-sm text-[#2d2a26]">{rec.room_type}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="border-t border-[#e8e4df] pt-6">
                <p className="text-sm text-[#6b6560] mb-3">Not satisfied? Provide feedback to refine the search:</p>
                <div className="flex gap-3">
                  <input
                    type="text"
                    value={refinementFeedback}
                    onChange={(e) => setRefinementFeedback(e.target.value)}
                    placeholder="E.g., 'Too expensive' or 'I want direct flights'"
                    className="flex-1 px-4 py-2 border-2 border-[#e8e4df] rounded-xl focus:outline-none focus:border-[#c4bdb5] text-[#2d2a26]"
                  />
                  <button
                    onClick={handleRefine}
                    disabled={!refinementFeedback.trim()}
                    className="px-6 py-2 bg-[#c17d3f] text-white rounded-xl hover:bg-[#a86b32] disabled:bg-[#d4cfc8] disabled:cursor-not-allowed transition-all duration-200 font-medium"
                  >
                    Refine
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Input Form */}
        <div className="max-w-3xl mx-auto">
          {planningState.status === 'idle' && (
            <form onSubmit={handleSubmit} className="bg-white rounded-3xl shadow-lg border border-[#e8e4df] p-8">
              <label className="block text-sm font-medium text-[#2d2a26] mb-3">
                Describe Your Dream Vacation ✈️
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

        {/* Results Display */}
        {planningState.status === 'complete' && (
          <div className="max-w-5xl mx-auto">
            <div className="bg-white rounded-3xl shadow-lg border border-[#e8e4df] p-10">
              <div 
                className="prose prose-lg max-w-none mb-8"
                dangerouslySetInnerHTML={{ __html: formatItineraryText(planningState.result) }}
              />
              
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
