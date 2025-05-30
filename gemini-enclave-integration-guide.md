# Simplified Gemini Enclave Integration Guide

## Enclave Endpoint
- **Base URL**: `http://54.91.81.96:3000`
- **Status**: Active and running in AWS Nitro Enclave

## Available APIs

### 1. Health Check
- **GET** `/health_check`
- **Purpose**: Check if enclave is online and get public key
- **Response Structure**:
  ```json
  {
    "status": "healthy",
    "pk": "<enclave_public_key_hex>",
    "endpoints_status": {
      "generativelanguage.googleapis.com": true/false
    }
  }
  ```

### 2. Process Gemini Request
- **POST** `/process_gemini`
- **Purpose**: Send data to Gemini AI for analysis
- **Request Structure**:
  ```json
  {
    "payload": {
      "question": "Your question about the data",
      "file_content": "base64_encoded_content",
      "filename": "filename.ext"
    }
  }
  ```
- **Response Structure**:
  ```json
  {
    "response": {
      "data": {
        "question": "...",
        "answer": "Gemini's response",
        "filename": "..."
      },
      "timestamp_ms": 1234567890
    },
    "signature": "hex_signature"
  }
  ```

### 3. Get Attestation
- **GET** `/get_attestation`
- **Purpose**: Get enclave attestation document
- **Response**: Raw attestation document bytes

## Blockchain Integration

### Contract Addresses (Sui Testnet)
- **App Package**: `0x52d141a32883dd46c17986a78991d4f6cd4378351dcd884c1fcbd3faa13ff6e4`
- **Gemini Enclave Object**: `0xcbbf5bb5bb60f3b1a5db4394a92be4a2e26cbf28924af12e3450ed6b6e0a784b`

### Registering Enclave Attestation

To register the enclave's attestation signature on-chain:

1. **Get the attestation** from the enclave:
   ```bash
   GET http://54.91.81.96:3000/get_attestation
   ```

2. **Submit to blockchain** using Sui CLI:
   ```bash
   sui client ptb \
     --move-call "<APP_PACKAGE>::gemini::register_enclave_pubkey" \
     "<PUBLIC_KEY_HEX>" \
     "vector[<ATTESTATION_BYTES>]" \
     @<GEMINI_ENCLAVE_OBJECT> \
     --gas-budget 100000000
   ```

   Where:
   - `<PUBLIC_KEY_HEX>`: The public key from health_check response
   - `<ATTESTATION_BYTES>`: Attestation document as Sui vector format (e.g., `[1u8, 2u8, 3u8, ...]`)
   - `<GEMINI_ENCLAVE_OBJECT>`: The deployed Gemini enclave object ID

### Submitting Gemini Results to Chain

After getting a signed response from `/process_gemini`:

```bash
sui client ptb \
  --move-call "<APP_PACKAGE>::gemini::query_gemini<APP_PACKAGE::gemini::GEMINI>" \
  "<QUESTION>" \
  "<ANSWER>" \
  "<FILENAME>" \
  <TIMESTAMP> \
  "vector[<SIGNATURE_BYTES>]" \
  @<GEMINI_ENCLAVE_OBJECT> \
  --assign result \
  --transfer-objects [result] @<USER_ADDRESS> \
  --gas-budget 100000000
```

## Integration Flow

1. **Backend receives** user request with file/text and question
2. **Backend encodes** file content to base64
3. **Backend calls** POST `/process_gemini` 
4. **Enclave processes** with Gemini AI and returns signed response
5. **Backend submits** signed response to Sui blockchain
6. **NFT minted** and transferred to user's address

## Key Considerations

- All file content must be base64 encoded before sending
- Signatures are returned as hex strings
- Timestamps are in milliseconds
- User addresses must be valid 64-character Sui addresses (with 0x prefix)
- The enclave validates all responses with its private key
- PCRs are verified on-chain to ensure enclave authenticity 