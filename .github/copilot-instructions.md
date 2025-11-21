# Copilot Instructions for AI_vacation_planner

## Project Architecture

- **Monorepo Structure**: Two main folders: `backend/` (Node.js/Express + Python agents) and `frontend/` (Next.js/React).
- **Backend**:
  - `server.js`: Express API server, authenticates users via JWT (email as token), proxies requests to Python agents.
  - `agents/`: Python agents for flights, hotels, restaurants, attractions, itinerary. Each agent inherits from `BaseAgent` (Gemini AI integration, logging, error handling).
  - `mcp-servers/`: API clients for Amadeus (flights/hotels) and Google Places (restaurants/attractions).
  - Agents communicate with external APIs via these clients, filter/rank results using Gemini AI, and return structured recommendations.
- **Frontend**:
  - Next.js app with NextAuth for authentication (Google OAuth, Email magic-link, Prisma adapter).
  - Main UI in `app/page.tsx`, sends vacation planning requests to backend, includes JWT in `Authorization` header.
  - Prisma ORM with SQLite for user/session management (`prisma/schema.prisma`).

## Developer Workflows

- **Backend**:
  - Start server: `npm run dev` (uses nodemon for hot reload).
  - Python agents: run via Flask or called from Node.js; dependencies in `agents/requirements.txt`.
  - Environment variables: set `GEMINI_API_KEY`, Amadeus/Google API keys in `.env`.
- **Frontend**:
  - Start dev server: `npm run dev`.
  - Auth: NextAuth config in `app/api/auth/[...nextauth]/route.ts`.
  - DB: Prisma migrations in `prisma/migrations/`.

## Key Patterns & Conventions

- **Agent Pattern**: All agents inherit from `BaseAgent` for consistent AI/logging/error handling. Orchestration via `OrchestratorAgent`.
- **API Clients**: Amadeus and Google Places clients wrap external APIs for flights/hotels/restaurants/attractions. Agents call these clients, not raw APIs.
- **Authentication**: Email is used as JWT for backend auth. Express checks for `Bearer <email>` in headers.
- **Cross-Language Integration**: Node.js server proxies requests to Python agents, which call external APIs and use Gemini for ranking/summarization.
- **Frontend-Backend Contract**: Frontend sends vacation requests to `/api/plan-vacation-agents` with JWT; expects structured JSON response (success, summary, recommendations).

## External Dependencies

- **Gemini AI**: Used by all agents for filtering, ranking, and summarizing results.
- **Amadeus API**: Flights and hotels data.
- **Google Places API**: Restaurants and attractions data.
- **Prisma/SQLite**: User/session management in frontend.

## Examples

- To add a new agent, inherit from `BaseAgent`, implement `execute(input_data)`, and register with `OrchestratorAgent`.
- To add a new API integration, create a client in `mcp-servers/`, wrap API logic, and call from relevant agent.
- To debug backend auth, check Express middleware in `server.js` and NextAuth config in frontend.

---

If any section is unclear or missing details, please specify which part needs improvement or more examples.