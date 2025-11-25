"use client";

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
  | { status: 'loading' }
  | { status: 'awaiting_input'; sessionId: string; agent: string; itemType: string; recommendations: any[]; summary: string }
  | { status: 'complete'; result: string }
  | { status: 'error'; message: string };

export default function Home() {
  const { data: session, status } = useSession();
  const [prompt, setPrompt] = useState("");
  const [planningState, setPlanningState] = useState<PlanningState>({ status: 'idle' });
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [refinementFeedback, setRefinementFeedback] = useState("");

  /**
   * When the session changes, ask NextAuth for the JWT token.
   */
  useEffect(() => {
    if (status === "authenticated" && session?.user?.email) {
      setAuthToken(session.user.email);
      console.log('🔐 Auth token set:', session.user.email);
    } else {
      setAuthToken(null);
    }
  }, [status, session]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!prompt.trim()) {
      alert("Please enter a vacation request");
      return;
    }

    if (!session) {
      alert("Please sign in to plan a vacation.");
      return;
    }

    setPlanningState({ status: 'loading' });

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";
      const response = await fetch(`${backendUrl}/api/plan-vacation-agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: authToken ? `Bearer ${authToken}` : "",
        },
        body: JSON.stringify({ prompt }),
      });

      const data = await response.json();
      handlePlanningResponse(data);

    } catch (error) {
      console.error("Request error:", error);
      setPlanningState({
        status: 'error',
        message: "Unable to connect to the server. Please make sure all services are running."
      });
    }
  };

  const handlePlanningResponse = (data: any) => {
    console.log('📥 Response:', data);

    // Case 1: Agent paused for user input
    if (data.status === 'awaiting_user_input') {
      console.log('⏸️ Agent paused, showing recommendations');
      setPlanningState({
        status: 'awaiting_input',
        sessionId: data.session_id,
        agent: data.agent,
        itemType: data.item_type,
        recommendations: data.recommendations || [],
        summary: data.summary || ''
      });
    }
    // Case 2: Planning complete
    else if (data.status === 'complete' && data.success) {
      console.log('✅ Planning complete');
      setPlanningState({
        status: 'complete',
        result: data.data || 'Your vacation plan is ready!'
      });
    }
    // Case 3: Error
    else {
      console.error('❌ Error response:', data);
      setPlanningState({
        status: 'error',
        message: data.error || data.message || 'Something went wrong. Please try again.'
      });
    }
  };

  const handleSelectRecommendation = async (itemId: string) => {
    if (planningState.status !== 'awaiting_input') return;

    console.log('👤 User selected:', itemId);
    setPlanningState({ status: 'loading' });

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
            status: 'FINAL_CHOICE',
            [`${planningState.itemType}_id`]: itemId
          }
        }),
      });

      const data = await response.json();
      handlePlanningResponse(data);

    } catch (error) {
      console.error("Resume error:", error);
      setPlanningState({
        status: 'error',
        message: "Failed to resume planning. Please try again."
      });
    }
  };

  const handleRefineSearch = async () => {
    if (planningState.status !== 'awaiting_input' || !refinementFeedback.trim()) {
      alert("Please enter refinement feedback");
      return;
    }

    console.log('👤 User refinement:', refinementFeedback);
    setPlanningState({ status: 'loading' });

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
            status: 'REFINE_SEARCH',
            feedback: refinementFeedback
          }
        }),
      });

      const data = await response.json();
      setRefinementFeedback(""); // Clear feedback
      handlePlanningResponse(data);

    } catch (error) {
      console.error("Refine error:", error);
      setPlanningState({
        status: 'error',
        message: "Failed to refine search. Please try again."
      });
    }
  };

  const isAuthenticated = status === "authenticated";

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-indigo-900 mb-4">
            ✈️ AI Vacation Planner
          </h1>
          <p className="text-lg text-gray-700">
            Tell me where you want to go, and I&apos;ll plan your perfect trip!
          </p>

          {/* Auth buttons */}
          <div className="mt-6 flex justify-center gap-4">
            {!isAuthenticated ? (
              <>
                <button
                  onClick={() => signIn("google")}
                  className="bg-white border border-indigo-200 text-indigo-700 font-semibold py-2 px-4 rounded-lg hover:shadow transition"
                >
                  Sign in with Google
                </button>
                <button
                  onClick={() => signIn("email")}
                  className="bg-indigo-600 text-white font-semibold py-2 px-4 rounded-lg hover:bg-indigo-700 transition"
                >
                  Sign in with Email
                </button>
              </>
            ) : (
              <div className="flex items-center gap-3">
                <span className="text-gray-700">
                  Signed in as {session.user?.email || "your account"}
                </span>
                <button
                  onClick={() => signOut()}
                  className="bg-red-500 text-white font-semibold py-2 px-4 rounded-lg hover:bg-red-600 transition"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Input Form - Only show when idle */}
        {planningState.status === 'idle' && (
          <div className="bg-white rounded-2xl shadow-xl p-8 mb-8">
            {!isAuthenticated ? (
              <p className="text-center text-gray-600">
                Please sign in to start planning your trip.
              </p>
            ) : (
              <form onSubmit={handleSubmit}>
                <label
                  htmlFor="prompt"
                  className="block text-sm font-semibold text-gray-700 mb-3"
                >
                  Describe your dream vacation:
                </label>
                <textarea
                  id="prompt"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Example: Plan a family vacation from Santander to Madrid from December 10-15, 2025. Budget: 2000 euros."
                  className="w-full h-32 px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition text-gray-900 resize-none"
                />

                <button
                  type="submit"
                  className="mt-4 w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-4 px-6 rounded-lg transition-all transform hover:scale-[1.02] shadow-lg"
                >
                  🚀 Plan My Vacation
                </button>
              </form>
            )}
          </div>
        )}

        {/* Loading State */}
        {planningState.status === 'loading' && (
          <div className="bg-white rounded-2xl shadow-xl p-8 mb-8">
            <div className="flex items-center justify-center">
              <svg className="animate-spin h-8 w-8 text-indigo-600 mr-3" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="text-lg text-gray-700">Planning your vacation...</span>
            </div>
          </div>
        )}

        {/* Awaiting User Input - Show Recommendations */}
        {planningState.status === 'awaiting_input' && (
          <div className="bg-white rounded-2xl shadow-xl p-8 mb-8">
            <h2 className="text-2xl font-bold text-indigo-900 mb-2">
              {planningState.itemType === 'flight' && '✈️ Flight Options'}
              {planningState.itemType === 'hotel' && '🏨 Hotel Options'}
              {planningState.itemType === 'restaurant' && '🍽️ Restaurant Options'}
              {planningState.itemType === 'attraction' && '🎭 Attraction Options'}
            </h2>
            <p className="text-gray-600 mb-6">{planningState.summary}</p>

            {/* Recommendations Grid */}
            <div className="grid gap-4 mb-6">
              {planningState.recommendations.map((item: any) => (
                <div
                  key={item.id}
                  className="border-2 border-gray-200 rounded-lg p-4 hover:border-indigo-500 hover:shadow-lg transition cursor-pointer"
                  onClick={() => handleSelectRecommendation(item.id)}
                >
                  {/* Flight Card */}
                  {planningState.itemType === 'flight' && (
                    <div>
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <p className="font-bold text-lg text-gray-900">
                            {item.outbound.airline} {item.outbound.flight}
                          </p>
                          <p className="text-sm text-gray-600">
                            {item.outbound.from} → {item.outbound.to}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-2xl font-bold text-indigo-600">
                            ${item.price}
                          </p>
                          <p className="text-xs text-gray-500">{item.currency}</p>
                        </div>
                      </div>
                      <div className="text-sm text-gray-600">
                        <p>Departure: {new Date(item.outbound.departure).toLocaleString()}</p>
                        <p>Duration: {item.outbound.duration} | Stops: {item.outbound.stops}</p>
                      </div>
                      {item.return && (
                        <div className="mt-2 pt-2 border-t text-sm text-gray-600">
                          <p>Return: {new Date(item.return.departure).toLocaleString()}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Generic Card for other types */}
                  {planningState.itemType !== 'flight' && (
                    <div>
                      <p className="font-bold text-lg text-gray-900">{item.name || item.id}</p>
                      <p className="text-sm text-gray-600">{JSON.stringify(item)}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Refinement Section */}
            <div className="border-t pt-6">
              <p className="text-sm font-semibold text-gray-700 mb-2">
                Not satisfied? Tell me what you'd like to change:
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={refinementFeedback}
                  onChange={(e) => setRefinementFeedback(e.target.value)}
                  placeholder="e.g., 'Too expensive, find cheaper options under $150'"
                  className="flex-1 px-4 py-2 border-2 border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition text-gray-900"
                />
                <button
                  onClick={handleRefineSearch}
                  className="bg-gray-600 hover:bg-gray-700 text-white font-semibold py-2 px-6 rounded-lg transition"
                >
                  Refine Search
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Complete State - Show Final Plan */}
        {planningState.status === 'complete' && (
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-2xl font-bold text-indigo-900">
                📋 Your Vacation Plan
              </h2>
              <button
                onClick={() => setPlanningState({ status: 'idle' })}
                className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 px-4 rounded-lg transition"
              >
                Plan Another Trip
              </button>
            </div>
            <div className="prose prose-lg max-w-none">
              <pre className="whitespace-pre-wrap text-gray-800 font-sans leading-relaxed">
                {planningState.result}
              </pre>
            </div>
          </div>
        )}

        {/* Error State */}
        {planningState.status === 'error' && (
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <h2 className="text-2xl font-bold text-red-600 mb-4">
              ❌ Error
            </h2>
            <p className="text-gray-700 mb-4">{planningState.message}</p>
            <button
              onClick={() => setPlanningState({ status: 'idle' })}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 px-4 rounded-lg transition"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </main>
  );
}