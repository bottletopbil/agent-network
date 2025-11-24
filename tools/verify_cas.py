import sys
import os
sys.path.insert(0, "src")
import cas

hash_hex = "383fb6ccccd528b0fd4efbeda082b01eaa20ea8fea32966e9a1b31903c7310fa"
try:
    data = cas.get_json(hash_hex)
    print(data)
except Exception as e:
    print(f"Error: {e}")
