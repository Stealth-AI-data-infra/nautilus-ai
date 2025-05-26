#!/bin/bash

if [ "$#" -ne 10 ]; then
    echo "Usage: $0 <package_id> <module> <otw> <enclave_id> <sig> <timestamp> <question> <answer> <model> <file_hash>"
    echo "Example: $0 0x2b70e... gemini GEMINI 0x5fc237... bb0d31... 1743982200000 'What is...' 'The answer...' 'gemini-1.5-flash' a1b2c3..."
    exit 1
fi

PACKAGE_ID=$1
MODULE_NAME=$2
OTW_NAME=$3
ENCLAVE_ID=$4
SIG_HEX=$5
TIMESTAMP=$6
QUESTION=$7
ANSWER=$8
MODEL=$9
FILE_HASH=${10}

# Convert signature hex to vector array
SIG_ARRAY=$(python3 - <<EOF
hex_str = '$SIG_HEX'
bytes_arr = [str(int(hex_str[i:i+2], 16)) + 'u8' for i in range(0, len(hex_str), 2)]
print('[' + ', '.join(bytes_arr) + ']')
EOF
)

# Convert file hash hex to vector array
HASH_ARRAY=$(python3 - <<EOF
hex_str = '$FILE_HASH'
bytes_arr = [str(int(hex_str[i:i+2], 16)) + 'u8' for i in range(0, len(hex_str), 2)]
print('[' + ', '.join(bytes_arr) + ']')
EOF
)

echo "Converted signature, length=${#SIG_ARRAY}"
echo "Converted hash, length=${#HASH_ARRAY}"

sui client ptb \
    --move-call "${PACKAGE_ID}::gemini::query_gemini<${PACKAGE_ID}::${MODULE_NAME}::${OTW_NAME}>" \
        "\"$QUESTION\"" \
        "\"$ANSWER\"" \
        "\"$MODEL\"" \
        "vector$HASH_ARRAY" \
        $TIMESTAMP \
        "vector$SIG_ARRAY" \
        @$ENCLAVE_ID \
    --assign nft \
    --transfer-objects "[nft]" @$(sui client active-address) \
    --gas-budget 100000000 