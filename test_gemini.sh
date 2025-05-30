#!/bin/bash

# Create a sample CSV file
cat > sales_data.csv << EOF
Date,Product,Quantity,Revenue
2024-01-01,Widget A,150,4500
2024-01-02,Widget B,200,8000
2024-01-03,Widget A,175,5250
2024-01-04,Widget C,100,12000
2024-01-05,Widget B,225,9000
EOF

# Encode the CSV file to base64
FILE_CONTENT=$(base64 -w 0 sales_data.csv)

# Create the request payload - wrapped in "payload" object
cat > gemini_request.json << EOF
{
  "payload": {
    "question": "What is the total revenue and which product generated the most revenue?",
    "file_content": "$FILE_CONTENT",
    "filename": "sales_data.csv"
  }
}
EOF

echo "Sending Gemini request to enclave..."
echo "Question: What is the total revenue and which product generated the most revenue?"
echo ""

# Send request to the enclave
RESPONSE=$(curl -s -X POST http://54.91.81.96:3000/process_gemini \
  -H "Content-Type: application/json" \
  -d @gemini_request.json)

echo "Response from enclave:"
echo "$RESPONSE" | jq '.'

# Save the response for processing
echo "$RESPONSE" > gemini_response.json

# Extract values for blockchain submission
INTENT=$(echo "$RESPONSE" | jq -r '.response.intent')
TIMESTAMP=$(echo "$RESPONSE" | jq -r '.response.timestamp_ms')
QUESTION=$(echo "$RESPONSE" | jq -r '.response.data.question')
ANSWER=$(echo "$RESPONSE" | jq -r '.response.data.answer')
FILENAME=$(echo "$RESPONSE" | jq -r '.response.data.filename')
SIGNATURE=$(echo "$RESPONSE" | jq -r '.signature')

echo ""
echo "Extracted values:"
echo "Intent: $INTENT"
echo "Timestamp: $TIMESTAMP"
echo "Question: $QUESTION"
echo "Answer: $ANSWER"
echo "Filename: $FILENAME"
echo "Signature: $SIGNATURE" 