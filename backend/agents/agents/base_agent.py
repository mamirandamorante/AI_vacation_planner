"""
Base Agent Class
All specialized agents inherit from this class
"""

import os
from typing import Dict, Any
import google.generativeai as genai
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """
    Abstract base class for all agents
    Provides common functionality: logging, AI client, error handling
    """
    
    def __init__(self, agent_name: str, gemini_api_key: str):
        """
        Initialize base agent
        
        Args:
            agent_name: Name of the agent (e.g., "FlightAgent")
            gemini_api_key: Google Gemini API key
        """
        self.name = agent_name
        self.gemini_api_key = gemini_api_key
        
        # Initialize Gemini
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        self.log(f"✅ {agent_name} initialized")
    
    def log(self, message: str, level: str = "INFO"):
        """Log messages with agent name"""
        print(f"[{self.name}] [{level}] {message}")
    
    def ask_ai(self, prompt: str) -> str:
        """
        Query Gemini AI
        
        Args:
            prompt: The prompt to send to AI
            
        Returns:
            AI response as string
        """
        try:
            self.log(f"Querying AI: {prompt[:100]}...")
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            self.log(f"AI query error: {str(e)}", "ERROR")
            raise
    
    def format_error(self, error: Exception) -> Dict:
        """
        Format error response
        
        Args:
            error: The exception that occurred
            
        Returns:
            Formatted error dictionary
        """
        return {
            "success": False,
            "error": str(error),
            "agent": self.name
        }
    
    @abstractmethod
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution method - must be implemented by child classes
        
        Args:
            input_data: Input parameters for the agent
            
        Returns:
            Agent execution results
        """
        pass