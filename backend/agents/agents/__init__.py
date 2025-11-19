"""
Agents Package
==============
This file makes the 'agents' folder a Python package.

What this does:
- Tells Python "this folder contains importable modules"
- Defines what can be imported from this package
- Makes imports cleaner and more organized

Without this file:
  from agents.agents.flight_agent import FlightAgent  # Ugly

With this file:
  from agents import FlightAgent  # Clean!
"""

# Import our agent classes so they're available at package level
from .base_agent import BaseAgent
from .flight_agent import FlightAgent
from .hotel_agent import HotelAgent
from .restaurant_agent import RestaurantAgent
from .attractions_agent import AttractionsAgent
from .orchestrator_agent import OrchestratorAgent
from .itinerary_agent import ItineraryAgent   

# Define what gets exported when someone does "from agents import *"
# This is like saying "these are the public APIs of this package"
__all__ = [
    'BaseAgent',
    'FlightAgent',
    'HotelAgent',
    'RestaurantAgent',
    'AttractionsAgent',
    'OrchestratorAgent',
    'ItineraryAgent'
    
]

# As we add more agents, we'll add them here:
# from .restaurant_agent import RestaurantAgent
# __all__.append('RestaurantAgent')
