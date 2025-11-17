"""
Base Agent Class
=================
This is the foundation class that ALL agents inherit from.
Think of it as a template that provides common functionality every agent needs.

Why do we need this?
- Avoid repeating code across different agents
- Ensure all agents work the same way
- Easy to add new features to all agents at once
"""

import os
from typing import Dict, Any
import google.generativeai as genai
from abc import ABC, abstractmethod  # ABC = Abstract Base Class, helps create templates


class BaseAgent(ABC):
    """
    Abstract Base Class for All Agents
    
    This class cannot be used directly - it's a template.
    Other agents (FlightAgent, HotelAgent) will inherit from this.
    
    What it provides:
    1. Connection to Gemini AI
    2. Logging system (so we can see what agents are doing)
    3. Error handling (consistent error messages)
    4. AI query method (ask questions to Gemini)
    """
    
    def __init__(self, agent_name: str, gemini_api_key: str):
        """
        Constructor - runs when we create a new agent
        
        What happens here:
        1. Save the agent's name (like "FlightAgent")
        2. Save the API key
        3. Connect to Google's Gemini AI
        4. Create an AI model we can talk to
        5. Log that the agent is ready
        
        Args:
            agent_name: The name of this agent (e.g., "FlightAgent", "HotelAgent")
            gemini_api_key: Your Google Gemini API key from .env file
        """
        # Store the agent's name so we can identify it in logs
        self.name = agent_name
        
        # Store API key (needed for AI requests)
        self.gemini_api_key = gemini_api_key
        
        # STEP 1: Configure the Gemini API with our key
        # This tells Google "hey, this is me, let me use your AI"
        genai.configure(api_key=gemini_api_key)
        
        # STEP 2: Create a specific AI model to use
        # 'gemini-2.5-flash' is Google's fast, smart model
        # This is the "brain" that will answer questions
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # STEP 3: Log that we're ready
        self.log(f"✅ {agent_name} initialized")
    
    def log(self, message: str, level: str = "INFO"):
        """
        Logging Method - prints messages with the agent's name
        
        Why do we need this?
        - When multiple agents run, we need to know WHO is doing WHAT
        - Makes debugging much easier
        - Professional applications always have good logging
        
        Example output: [FlightAgent] [INFO] Searching for flights...
        
        Args:
            message: What to print (e.g., "Starting search")
            level: Type of message - "INFO", "ERROR", "WARN"
        """
        # Print in format: [AgentName] [Level] Message
        print(f"[{self.name}] [{level}] {message}")
    
    def ask_ai(self, prompt: str) -> str:
        """
        Ask Gemini AI a Question
        
        This is the core method that talks to Google's AI.
        We send a prompt (question/instruction) and get back a text response.
        
        How it works:
        1. Log what we're asking (first 100 characters)
        2. Send the prompt to Gemini
        3. Wait for response
        4. Return the text answer
        5. If anything fails, log error and raise exception
        
        Example:
            response = self.ask_ai("What are the best restaurants in Paris?")
            # response = "Here are the top restaurants in Paris: ..."
        
        Args:
            prompt: The question or instruction to send to AI
            
        Returns:
            AI's response as a string
            
        Raises:
            Exception: If the AI request fails (network, API limits, etc.)
        """
        try:
            # Log what we're asking (truncate to 100 chars to keep logs clean)
            self.log(f"Querying AI: {prompt[:100]}...")
            
            # Send prompt to Gemini and get response
            # This is the actual AI call - it happens over the internet
            response = self.model.generate_content(prompt)
            
            # Extract just the text from the response object
            return response.text
            
        except Exception as e:
            # Something went wrong - log it
            self.log(f"AI query error: {str(e)}", "ERROR")
            
            # Re-raise the exception so the caller knows something failed
            raise
    
    def format_error(self, error: Exception) -> Dict:
        """
        Format Error Messages Consistently
        
        When something goes wrong, we need to tell the user in a clear way.
        This method creates a standard error response that all agents use.
        
        Why standardize errors?
        - Frontend always knows what to expect
        - Easy to display error messages to users
        - Can add error tracking/monitoring later
        
        Args:
            error: The Python exception that occurred
            
        Returns:
            Dictionary with error details:
            {
                "success": False,
                "error": "what went wrong",
                "agent": "which agent had the problem"
            }
        """
        return {
            "success": False,           # Tells caller: this failed
            "error": str(error),         # Human-readable error message
            "agent": self.name           # Which agent had the problem
        }
    
    @abstractmethod
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main Execution Method - MUST BE IMPLEMENTED BY CHILD CLASSES
        
        This is an "abstract method" - it's a placeholder.
        Every agent that inherits from BaseAgent MUST implement this.
        
        Why abstract?
        - Different agents do different things:
          * FlightAgent searches flights
          * HotelAgent searches hotels
          * RestaurantAgent finds restaurants
        - But they all need an execute() method
        - This ensures consistency across all agents
        
        Pattern:
        1. Receive input (what the user wants)
        2. Do the work (search, analyze, etc.)
        3. Return results in standard format
        
        Args:
            input_data: Dictionary with agent-specific parameters
                       (e.g., for FlightAgent: origin, destination, dates)
            
        Returns:
            Dictionary with results:
            {
                "success": True/False,
                "data": ... agent-specific results ...,
                "agent": "agent name"
            }
        """
        pass  # Child classes will replace this with real code