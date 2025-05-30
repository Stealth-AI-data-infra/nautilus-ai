import json

# Read the attestation.json file
with open('attestation.json', 'r') as f:
    data = json.load(f)
    
# Extract the attestation hex string
attestation_hex = data['attestation']

# Convert hex to byte array format
bytes_array = []
for i in range(0, len(attestation_hex), 2):
    byte_value = int(attestation_hex[i:i+2], 16)
    bytes_array.append(f"{byte_value}u8")

# Create vector string
vector_str = "[" + ", ".join(bytes_array) + "]"

# Write to file
with open('attestation_vector.txt', 'w') as f:
    f.write(vector_str)

# Print summary
print(f"Successfully converted {len(bytes_array)} bytes")
print(f"First 10 bytes: {', '.join(bytes_array[:10])}...")
print(f"Last 10 bytes: ...{', '.join(bytes_array[-10:])}")
print(f"Output saved to attestation_vector.txt") 