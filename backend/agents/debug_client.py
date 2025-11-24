import sys
import inspect
from pathlib import Path

# mimic the agent's path setup
mcp_path = Path(__file__).parent / 'backend' / 'mcp-servers' 
# Adjust this path string if your folder structure is different! 
# It needs to point to the folder containing the 'places' folder.
sys.path.insert(0, str(mcp_path.resolve()))

try:
    from places.google_places_client import GooglePlacesClient
    
    print(f"\n🔎 Python is loading the client from:\n   {inspect.getfile(GooglePlacesClient)}")
    
    sig = inspect.signature(GooglePlacesClient.search_restaurants)
    print(f"\n📋 The function signature Python sees is:\n   {sig}")
    
    if 'proximity_location' in str(sig):
        print("\n✅ SUCCESS: The code is updated.")
    else:
        print("\n❌ FAILURE: Python is still seeing the OLD code.")
        print("   Please edit the file at the path printed above!")

except ImportError as e:
    print(f"\n❌ Could not import: {e}")
    print(f"   Checked path: {mcp_path.resolve()}")