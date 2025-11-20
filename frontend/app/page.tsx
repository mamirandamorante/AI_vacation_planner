"use client";

import { useEffect, useState } from "react";
import { useSession, signIn, signOut } from "next-auth/react";

export default function Home() {
  const { data: session, status } = useSession();
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [authToken, setAuthToken] = useState<string | null>(null);

  /**
   * When the session changes, ask NextAuth for the JWT token.
   * This token will be sent to the Express backend so it knows
   * which authenticated user is requesting a plan.
   */
  useEffect(() => {
    if (status === "authenticated" && session?.user?.email) {
      // Use email as simple auth token
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

    setLoading(true);
    setResult("");

    try {
      const backendUrl =
        process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";
      const response = await fetch(`${backendUrl}/api/plan-vacation-agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // Include the JWT so Express can verify the user
          Authorization: authToken ? `Bearer ${authToken}` : "",
        },
        body: JSON.stringify({ prompt }),
      });

      const data = await response.json();

      if (data.needs_clarification) {
        setResult(data.data || "Please provide more details about your trip.");
      } else if (data.success) {
        setResult(data.data);
      } else {
        setResult(
          `Error: ${data.error || "Something went wrong. Please try again."}`
        );
      }
    } catch (error) {
      console.error("Request error:", error);
      setResult(
        "Error: Unable to connect to the server. Please make sure all services are running."
      );
    } finally {
      setLoading(false);
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

        {/* Input Form */}
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
                placeholder="Example: Plan a 5-day family vacation to Tokyo..."
                className="w-full h-32 px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition text-gray-900 resize-none"
                disabled={loading}
              />

              <button
                type="submit"
                disabled={loading}
                className="mt-4 w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-bold py-4 px-6 rounded-lg transition-all transform hover:scale-[1.02] disabled:scale-100 shadow-lg"
              >
                {loading ? (
                  <span className="flex items-center justify-center">
                    <svg
                      className="animate-spin h-5 w-5 mr-3"
                      viewBox="0 0 24 24"
                    >
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
                    Planning your vacation...
                  </span>
                ) : (
                  "🚀 Plan My Vacation"
                )}
              </button>
            </form>
          )}
        </div>

        {/* Results */}
        {result && (
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <h2 className="text-2xl font-bold text-indigo-900 mb-4">
              📋 Your Vacation Plan
            </h2>
            <div className="prose prose-lg max-w-none">
              <pre className="whitespace-pre-wrap text-gray-800 font-sans leading-relaxed">
                {result}
              </pre>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}