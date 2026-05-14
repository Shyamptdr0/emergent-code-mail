import sys
try:
    import server
    print("Server imported successfully. No syntax errors.")
except Exception as e:
    print(f"Error importing server: {e}")
    import traceback
    traceback.print_exc()
