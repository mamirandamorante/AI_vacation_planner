"""
MCP Flight Server
=================
This is a Model Context Protocol (MCP) server for flight searches.

What is MCP?
- MCP is a protocol that lets AI agents use tools/functions
- Think of it like a menu of actions agents can perform
- Agents say "I need to use the search_flights tool"
- This server executes that tool and returns results

Architecture:
  FlightAgent (needs flight data)
      ↓
  "Call search_flights tool"
      ↓
  **THIS SERVER** (MCP Flight Server)
      ↓
  AmadeusClient
      ↓
  Amadeus API (real flight data)

This server:
1. Defines available tools (search_flights)
2. Receives tool calls from agents
3. Executes the tool (searches Amadeus)
4. Returns results to agent
"""

import os
import asyncio
import json
from typing import Any
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp import types
from dotenv import load_dotenv

# Import our Amadeus client
from amadeus_client import AmadeusFlightClient

# Load environment variables
# Go up two directories to find backend/.env
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path)

# Get Amadeus credentials from environment
AMADEUS_API_KEY = os.getenv('AMADEUS_API_KEY')
AMADEUS_API_SECRET = os.getenv('AMADEUS_API_SECRET')

# Validate credentials exist
if not AMADEUS_API_KEY or not AMADEUS_API_SECRET:
    print("❌ ERROR: Amadeus credentials not found in .env")
    print("   Make sure AMADEUS_API_KEY and AMADEUS_API_SECRET are set")
    exit(1)

# Initialize Amadeus client
amadeus_client = AmadeusFlightClient(AMADEUS_API_KEY, AMADEUS_API_SECRET)

# Create MCP server instance
# This is the core server object that handles MCP protocol
server = Server("flights-mcp")

print("✅ MCP Flight Server initialized")


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================
# This section defines what tools are available to agents

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List Available Tools
    
    This is called when an agent asks "what tools do you have?"
    We return a list of tool definitions.
    
    Each tool definition includes:
    - name: The tool identifier
    - description: What the tool does (helps agent decide when to use it)
    - inputSchema: What parameters the tool needs (JSON Schema format)
    
    Returns:
        List of available tools (just search_flights for now)
    """
    return [
        types.Tool(
            name="search_flights",
            description="""Search for flight options between two cities.
            
            This tool searches the Amadeus API for real flight data including:
            - Available flights with times and airlines
            - Prices in USD
            - Number of stops
            - Flight duration
            
            Use this when you need to find flights for a user's trip.""",
            
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "Origin airport code (e.g., 'SFO', 'JFK')"
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination airport code (e.g., 'BCN', 'CDG')"
                    },
                    "departure_date": {
                        "type": "string",
                        "description": "Departure date in YYYY-MM-DD format"
                    },
                    "return_date": {
                        "type": "string",
                        "description": "Return date in YYYY-MM-DD format (optional, for round trip)"
                    },
                    "adults": {
                        "type": "integer",
                        "description": "Number of adult passengers (default: 1)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)"
                    }
                },
                "required": ["origin", "destination", "departure_date"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """
    Execute a Tool
    
    This is called when an agent says "execute the search_flights tool with these parameters"
    
    Flow:
    1. Agent requests tool execution
    2. This function receives tool name and parameters
    3. We validate the tool name
    4. We execute the tool (call Amadeus API)
    5. We return results to the agent
    
    Args:
        name: Name of the tool to execute (e.g., "search_flights")
        arguments: Dictionary of parameters for the tool
        
    Returns:
        List of TextContent with results (MCP protocol format)
        
    Raises:
        ValueError: If tool name is unknown
    """
    # Check which tool is being called
    if name != "search_flights":
        raise ValueError(f"Unknown tool: {name}")
    
    # STEP 1: Log the request
    print(f"\n[MCP Server] Tool call: {name}")
    print(f"[MCP Server] Arguments: {json.dumps(arguments, indent=2)}")
    
    # STEP 2: Extract parameters (with defaults)
    origin = arguments.get('origin')
    destination = arguments.get('destination')
    departure_date = arguments.get('departure_date')
    return_date = arguments.get('return_date')  # Optional
    adults = arguments.get('adults', 1)
    max_results = arguments.get('max_results', 5)
    
    # STEP 3: Validate required parameters
    if not origin or not destination or not departure_date:
        error_msg = "Missing required parameters: origin, destination, or departure_date"
        print(f"[MCP Server] ERROR: {error_msg}")
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": error_msg})
        )]
    
    try:
        # STEP 4: Call Amadeus API via our client
        print(f"[MCP Server] Calling Amadeus API...")
        
        flights = amadeus_client.search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            max_results=max_results
        )
        
        # STEP 5: Format response
        result = {
            "success": True,
            "flights": flights,
            "count": len(flights),
            "query": {
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "return_date": return_date
            }
        }
        
        print(f"[MCP Server] Returning {len(flights)} flights")
        
        # STEP 6: Return results in MCP format
        # MCP requires results as TextContent
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
        
    except Exception as e:
        # If anything goes wrong, return error
        error_msg = f"Flight search error: {str(e)}"
        print(f"[MCP Server] ERROR: {error_msg}")
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": error_msg
            })
        )]


# ============================================================================
# SERVER STARTUP
# ============================================================================

async def main():
    """
    Main entry point for MCP server
    
    This starts the server using stdio (standard input/output).
    The server communicates via stdin/stdout, which is how MCP works.
    
    What happens:
    1. Create stdio server (reads from stdin, writes to stdout)
    2. Run the server with our configuration
    3. Server listens for MCP protocol messages
    4. Handles tool list requests and tool execution requests
    """
    print("\n" + "="*60)
    print("🚀 MCP Flight Server Starting")
    print("="*60)
    print("📡 Protocol: Model Context Protocol (MCP)")
    print("🔧 Tools: search_flights")
    print("✈️  API: Amadeus Flight Search")
    print("="*60 + "\n")
    
    # Start stdio server
    # This creates a server that communicates via standard input/output
    async with stdio_server() as (read_stream, write_stream):
        # Run the server
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="flights-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                )
            )
        )


# Entry point
if __name__ == "__main__":
    """
    Script entry point
    Run this with: python server.py
    """
    # Run the async main function
    asyncio.run(main())