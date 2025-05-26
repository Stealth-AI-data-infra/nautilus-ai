#!/usr/bin/env python3
import requests
import json
import base64
import sys
import hashlib
import os

def query_gemini_enclave(enclave_url, question, file_path):
    # Read and encode file
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found")
        sys.exit(1)
    
    # Check file size (10MB limit)
    file_size = os.path.getsize(file_path)
    if file_size > 10 * 1024 * 1024:
        print("Error: File size exceeds 10MB limit")
        sys.exit(1)
    
    with open(file_path, 'rb') as f:
        file_content = base64.b64encode(f.read()).decode('utf-8')
    
    # Determine file type
    file_type = "text/plain"
    if file_path.endswith('.json'):
        file_type = "application/json"
    elif file_path.endswith('.csv'):
        file_type = "text/csv"
    elif file_path.endswith('.txt'):
        file_type = "text/plain"
    elif file_path.endswith('.md'):
        file_type = "text/markdown"
    
    # Prepare request
    payload = {
        "payload": {
            "question": question,
            "file_content": file_content,
            "file_type": file_type
        }
    }
    
    print(f"Querying Gemini with file: {file_path} ({file_size} bytes)")
    print(f"Question: {question}")
    print("Waiting for response...")
    
    # Make request
    try:
        response = requests.post(
            f"{enclave_url}/process_gemini",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120  # 2 minute timeout for large files
        )
    except requests.exceptions.Timeout:
        print("Error: Request timed out")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {enclave_url}")
        sys.exit(1)
    
    if response.status_code == 200:
        data = response.json()
        print("\n=== Response ===")
        print(json.dumps(data, indent=2))
        
        # Extract values for Sui transaction
        sig = data['response']['sig']
        timestamp = data['response']['data']['timestamp_ms']
        answer = data['response']['data']['data']['answer']
        model = data['response']['data']['data']['model']
        file_hash = ''.join(format(x, '02x') for x in data['response']['data']['data']['file_hash'])
        
        print(f"\n=== Use these values for Sui transaction ===")
        print(f"export GEMINI_SIGNATURE={sig}")
        print(f"export GEMINI_TIMESTAMP={timestamp}")
        print(f"export GEMINI_ANSWER='{answer[:100]}...'")  # Truncate for display
        print(f"export GEMINI_MODEL={model}")
        print(f"export GEMINI_FILE_HASH={file_hash}")
        
        # Save full answer to file for reference
        with open('gemini_answer.txt', 'w') as f:
            f.write(answer)
        print(f"\nFull answer saved to: gemini_answer.txt")
        
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python gemini_query_helper.py <enclave_url> <question> <file_path>")
        print("Example: python gemini_query_helper.py http://localhost:3000 'What are the key insights?' data.csv")
        sys.exit(1)
    
    query_gemini_enclave(sys.argv[1], sys.argv[2], sys.argv[3]) 