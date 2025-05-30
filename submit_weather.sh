#!/bin/bash

# Weather data from enclave
LOCATION="New York"
TEMPERATURE=18
TIMESTAMP_MS=1748399400000
SIG_HEX="edcc32e4b73f219c74cf68264a161c33c8131da08dd9c3bbe496edc7c96f012bf44714f0be89e94390c20cb281bea97d65eaa5d40f7c708befa646fe4ade1705"
WEATHER_ENCLAVE_ID="0x6b7370a56588959fccc10cb37f5b54bdbf02542c39848756fec5d4559b571197"
APP_PACKAGE_ID="0x52d141a32883dd46c17986a78991d4f6cd4378351dcd884c1fcbd3faa13ff6e4"

# Convert hex to vector array using Python
SIG_ARRAY=$(py - <<EOF
import sys

def hex_to_vector(hex_string):
    byte_values = [str(int(hex_string[i:i+2], 16)) for i in range(0, len(hex_string), 2)]
    rust_array = [f"{byte}u8" for byte in byte_values]
    return f"[{', '.join(rust_array)}]"

print(hex_to_vector("$SIG_HEX"))
EOF
)

echo "Submitting weather data to blockchain..."
echo "Location: $LOCATION"
echo "Temperature: $TEMPERATURE"
echo "Timestamp: $TIMESTAMP_MS"

# Submit using PTB (programmable transaction block)
sui client ptb \
    --move-call "${APP_PACKAGE_ID}::weather::update_weather<${APP_PACKAGE_ID}::weather::WEATHER>" \
        "\"$LOCATION\"" \
        $TEMPERATURE \
        $TIMESTAMP_MS \
        "vector$SIG_ARRAY" \
        @$WEATHER_ENCLAVE_ID \
    --assign nft_result \
    --transfer-objects "[nft_result]" @$(sui client active-address) \
    --gas-budget 100000000 