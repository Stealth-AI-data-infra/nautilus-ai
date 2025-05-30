#!/bin/bash

# Gemini data from enclave
QUESTION="What is the total revenue and which product generated the most revenue?"
ANSWER="The total revenue is 38750 Widget C generated the most revenue"
FILENAME="sales_data.csv"
TIMESTAMP_MS=1748401262472
SIG_HEX="41a05156a77e79bdfa42903c1c42e3587bf05cc81acb23e0a349271ee1df6e64bc69c76c8998d29d49f98e7847ae81d27c5c36d06b27f1b8121a7e1138df720a"
GEMINI_ENCLAVE_ID="0xcbbf5bb5bb60f3b1a5db4394a92be4a2e26cbf28924af12e3450ed6b6e0a784b"
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

echo "Submitting Gemini inference data to blockchain..."
echo "Question: $QUESTION"
echo "Answer: $ANSWER"
echo "Filename: $FILENAME"
echo "Timestamp: $TIMESTAMP_MS"

# Submit using PTB (programmable transaction block)
sui client ptb \
    --move-call "${APP_PACKAGE_ID}::gemini::query_gemini<${APP_PACKAGE_ID}::gemini::GEMINI>" \
        "\"$QUESTION\"" \
        "\"$ANSWER\"" \
        "\"$FILENAME\"" \
        $TIMESTAMP_MS \
        "vector$SIG_ARRAY" \
        @$GEMINI_ENCLAVE_ID \
    --assign nft_result \
    --transfer-objects "[nft_result]" @$(sui client active-address) \
    --gas-budget 100000000 