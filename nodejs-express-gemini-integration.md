# Node.js Express Backend Integration Guide: Gemini AI Analysis & NFT Minting

## Overview
This guide provides a complete Node.js Express backend implementation for integrating with the Nautilus AI enclave to process data with Gemini AI and mint NFTs on the Sui blockchain.

## Prerequisites
```bash
npm install express axios multer dotenv child_process express-rate-limit
```

## Environment Setup
Create a `.env` file:
```env
ENCLAVE_ENDPOINT=http://54.91.81.96:3000
GEMINI_ENCLAVE_ID=0xcbbf5bb5bb60f3b1a5db4394a92be4a2e26cbf28924af12e3450ed6b6e0a784b
APP_PACKAGE_ID=0x52d141a32883dd46c17986a78991d4f6cd4378351dcd884c1fcbd3faa13ff6e4
GAS_BUDGET=100000000
NODE_ENV=development
PORT=3001
```

## Complete Express Server Implementation

### 1. Main Server File (app.js)
```javascript
const express = require('express');
const multer = require('multer');
const axios = require('axios');
const { exec } = require('child_process');
const util = require('util');
const fs = require('fs').promises;
const path = require('path');
const rateLimit = require('express-rate-limit');
require('dotenv').config();

const app = express();
const execPromise = util.promisify(exec);

// Configure multer for file uploads
const upload = multer({ 
  dest: 'uploads/',
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB limit
  }
});

app.use(express.json());

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 10, // limit each IP to 10 requests per windowMs
  message: 'Too many requests, please try again later'
});

app.use('/api/gemini', limiter);

// Request logging
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} - ${req.method} ${req.path}`);
  next();
});

// Middleware for error handling
const asyncHandler = (fn) => (req, res, next) => {
  Promise.resolve(fn(req, res, next)).catch(next);
};

// Helper function to convert hex to Sui vector format
function hexToSuiVector(hexString) {
  const bytes = [];
  for (let i = 0; i < hexString.length; i += 2) {
    bytes.push(`${parseInt(hexString.substr(i, 2), 16)}u8`);
  }
  return `[${bytes.join(', ')}]`;
}

// Helper function to clean string for shell command
function escapeShellArg(arg) {
  return `"${arg.replace(/"/g, '\\"')}"`;
}

// Blockchain submission function
async function submitToBlockchain(question, answer, filename, timestamp, signature, userAddress) {
  // Convert signature to Sui vector format
  const sigVector = hexToSuiVector(signature);
  
  // Build the Sui CLI command
  const command = [
    'sui', 'client', 'ptb',
    '--move-call',
    `${process.env.APP_PACKAGE_ID}::gemini::query_gemini<${process.env.APP_PACKAGE_ID}::gemini::GEMINI>`,
    escapeShellArg(question),
    escapeShellArg(answer),
    escapeShellArg(filename),
    timestamp.toString(),
    `"vector${sigVector}"`,
    `@${process.env.GEMINI_ENCLAVE_ID}`,
    '--assign', 'nft_result',
    '--transfer-objects', '[nft_result]', `@${userAddress}`,
    '--gas-budget', process.env.GAS_BUDGET,
    '--json'
  ].join(' ');

  try {
    const { stdout, stderr } = await execPromise(command);
    
    if (stderr) {
      console.error('Sui CLI stderr:', stderr);
    }

    const result = JSON.parse(stdout);
    
    if (result.effects.status.status !== 'success') {
      throw new Error(`Blockchain transaction failed: ${result.effects.status.error || 'Unknown error'}`);
    }

    // Extract NFT ID from created objects
    const createdObject = result.effects.created[0];
    if (!createdObject) {
      throw new Error('No NFT created in transaction');
    }

    return {
      nftId: createdObject.reference.objectId,
      txDigest: result.digest,
      gasUsed: result.effects.gasUsed
    };

  } catch (error) {
    console.error('Blockchain submission error:', error);
    throw new Error(`Blockchain submission failed: ${error.message}`);
  }
}

// POST /api/gemini/analyze - Main file analysis endpoint
app.post('/api/gemini/analyze', upload.single('file'), asyncHandler(async (req, res) => {
  const { question, userAddress } = req.body;
  const file = req.file;

  // Validation
  if (!question || !userAddress || !file) {
    return res.status(400).json({
      success: false,
      error: 'Missing required fields: question, userAddress, and file'
    });
  }

  // Validate Sui address format
  if (!userAddress.match(/^0x[a-fA-F0-9]{64}$/)) {
    return res.status(400).json({
      success: false,
      error: 'Invalid Sui address format'
    });
  }

  try {
    // Step 1: Read and encode file
    const fileContent = await fs.readFile(file.path);
    const base64Content = fileContent.toString('base64');
    
    // Step 2: Request Gemini analysis from enclave
    console.log('Requesting Gemini analysis...');
    const enclaveResponse = await axios.post(`${process.env.ENCLAVE_ENDPOINT}/process_gemini`, {
      payload: {
        question: question,
        file_content: base64Content,
        filename: file.originalname || 'uploaded_file'
      }
    });

    const { response: enclaveData, signature } = enclaveResponse.data;
    
    // Step 3: Submit to blockchain
    console.log('Submitting to blockchain...');
    const nftResult = await submitToBlockchain(
      enclaveData.data.question,
      enclaveData.data.answer,
      enclaveData.data.filename,
      enclaveData.timestamp_ms,
      signature,
      userAddress
    );

    // Step 4: Clean up uploaded file
    await fs.unlink(file.path);

    // Step 5: Return success response
    res.json({
      success: true,
      nft: {
        id: nftResult.nftId,
        owner: userAddress,
        txDigest: nftResult.txDigest
      },
      analysis: {
        question: enclaveData.data.question,
        answer: enclaveData.data.answer,
        filename: enclaveData.data.filename,
        timestamp: enclaveData.timestamp_ms
      },
      explorerUrl: `https://suiscan.xyz/testnet/object/${nftResult.nftId}`
    });

  } catch (error) {
    // Clean up file on error
    if (file && file.path) {
      await fs.unlink(file.path).catch(() => {});
    }
    
    throw error;
  }
}));

// GET /api/gemini/status - Check enclave status
app.get('/api/gemini/status', asyncHandler(async (req, res) => {
  try {
    const response = await axios.get(`${process.env.ENCLAVE_ENDPOINT}/health_check`);
    res.json({
      success: true,
      enclave: {
        status: 'online',
        publicKey: response.data.pk,
        endpoints: response.data.endpoints_status
      }
    });
  } catch (error) {
    res.json({
      success: false,
      enclave: {
        status: 'offline',
        error: error.message
      }
    });
  }
}));

// POST /api/gemini/analyze-text - Analyze text without file upload
app.post('/api/gemini/analyze-text', asyncHandler(async (req, res) => {
  const { question, textContent, userAddress } = req.body;

  if (!question || !textContent || !userAddress) {
    return res.status(400).json({
      success: false,
      error: 'Missing required fields: question, textContent, and userAddress'
    });
  }

  // Validate Sui address format
  if (!userAddress.match(/^0x[a-fA-F0-9]{64}$/)) {
    return res.status(400).json({
      success: false,
      error: 'Invalid Sui address format'
    });
  }

  // Convert text to base64
  const base64Content = Buffer.from(textContent).toString('base64');
  
  try {
    // Process similar to file upload
    const enclaveResponse = await axios.post(`${process.env.ENCLAVE_ENDPOINT}/process_gemini`, {
      payload: {
        question: question,
        file_content: base64Content,
        filename: 'text_input.txt'
      }
    });

    const { response: enclaveData, signature } = enclaveResponse.data;
    
    const nftResult = await submitToBlockchain(
      enclaveData.data.question,
      enclaveData.data.answer,
      enclaveData.data.filename,
      enclaveData.timestamp_ms,
      signature,
      userAddress
    );

    res.json({
      success: true,
      nft: {
        id: nftResult.nftId,
        owner: userAddress,
        txDigest: nftResult.txDigest
      },
      analysis: {
        question: enclaveData.data.question,
        answer: enclaveData.data.answer,
        timestamp: enclaveData.timestamp_ms
      },
      explorerUrl: `https://suiscan.xyz/testnet/object/${nftResult.nftId}`
    });
  } catch (error) {
    throw error;
  }
}));

// GET /api/nft/:id - Get NFT details
app.get('/api/nft/:id', asyncHandler(async (req, res) => {
  const { id } = req.params;
  
  try {
    const { stdout } = await execPromise(`sui client object ${id} --json`);
    const nftData = JSON.parse(stdout);
    
    res.json({
      success: true,
      nft: {
        id: nftData.data.objectId,
        owner: nftData.data.owner,
        content: nftData.data.content.fields,
        type: nftData.data.content.type
      }
    });
  } catch (error) {
    res.status(404).json({
      success: false,
      error: 'NFT not found'
    });
  }
}));

// GET /health - Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    enclave: process.env.ENCLAVE_ENDPOINT
  });
});

// Global error handler
app.use((err, req, res, next) => {
  console.error('Error:', err);
  
  // Handle specific error types
  if (err.code === 'LIMIT_FILE_SIZE') {
    return res.status(413).json({
      success: false,
      error: 'File too large. Maximum size is 10MB.'
    });
  }
  
  if (err.response && err.response.status === 422) {
    return res.status(400).json({
      success: false,
      error: 'Invalid request format for enclave'
    });
  }
  
  // Default error response
  res.status(500).json({
    success: false,
    error: process.env.NODE_ENV === 'production' 
      ? 'Internal server error' 
      : err.message
  });
});

// Start server
const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Enclave status: http://localhost:${PORT}/api/gemini/status`);
});

module.exports = app;
```

### 2. Package.json
```json
{
  "name": "gemini-nft-backend",
  "version": "1.0.0",
  "description": "Express backend for Gemini AI analysis and NFT minting",
  "main": "app.js",
  "scripts": {
    "start": "node app.js",
    "dev": "nodemon app.js",
    "test": "echo \"Error: no test specified\" && exit 1"
  },
  "dependencies": {
    "express": "^4.18.2",
    "axios": "^1.6.0",
    "multer": "^1.4.5-lts.1",
    "dotenv": "^16.3.1",
    "express-rate-limit": "^7.1.5"
  },
  "devDependencies": {
    "nodemon": "^3.0.1"
  },
  "keywords": ["gemini", "ai", "nft", "sui", "blockchain", "enclave"],
  "author": "Your Name",
  "license": "MIT"
}
```

## Setup Instructions

### 1. Initialize Project
```bash
mkdir gemini-nft-backend
cd gemini-nft-backend
npm init -y
npm install express axios multer dotenv express-rate-limit
npm install --save-dev nodemon
```

### 2. Create Directory Structure
```bash
mkdir uploads
touch app.js
touch .env
touch .gitignore
```

### 3. Configure .gitignore
```
node_modules/
uploads/
.env
*.log
.DS_Store
```

### 4. Start Development Server
```bash
npm run dev
```

## API Endpoints

### 1. File Analysis
**POST** `/api/gemini/analyze`

**Form Data:**
- `file`: File to analyze (CSV, TXT, etc.)
- `question`: Analysis question
- `userAddress`: Sui wallet address (64-char hex with 0x prefix)

**Response:**
```json
{
  "success": true,
  "nft": {
    "id": "0xd34da250884dd0fa9a476af662442093e7c3766e28c679dc8dc1e08a4bf2a272",
    "owner": "0xf74be72609a5d368f511ac5b9e690e9f23085dfd8f76a0d4a943bbbac142ed47",
    "txDigest": "AA9y1adMa8kXDN1NDKtoh81nFwC7oMTJpHzRo3D8rBzB"
  },
  "analysis": {
    "question": "What is the total revenue?",
    "answer": "The total revenue is 38750",
    "filename": "sales_data.csv",
    "timestamp": 1748401262472
  },
  "explorerUrl": "https://suiscan.xyz/testnet/object/0xd34da250884dd0fa9a476af662442093e7c3766e28c679dc8dc1e08a4bf2a272"
}
```

### 2. Text Analysis
**POST** `/api/gemini/analyze-text`

**JSON Body:**
```json
{
  "question": "Summarize this text",
  "textContent": "Your text content here...",
  "userAddress": "0xf74be72609a5d368f511ac5b9e690e9f23085dfd8f76a0d4a943bbbac142ed47"
}
```

### 3. Enclave Status
**GET** `/api/gemini/status`

**Response:**
```json
{
  "success": true,
  "enclave": {
    "status": "online",
    "publicKey": "6efe2a091ccbc99de171684ba89f6b3da35b6938a86168006f0b1c9d8aa58f22",
    "endpoints": {
      "api.weatherapi.com": true,
      "generativelanguage.googleapis.com": true,
      "storage.googleapis.com": true
    }
  }
}
```

### 4. NFT Details
**GET** `/api/nft/:id`

**Response:**
```json
{
  "success": true,
  "nft": {
    "id": "0xd34da250884dd0fa9a476af662442093e7c3766e28c679dc8dc1e08a4bf2a272",
    "owner": "0xf74be72609a5d368f511ac5b9e690e9f23085dfd8f76a0d4a943bbbac142ed47",
    "content": {
      "question": "What is the total revenue?",
      "answer": "The total revenue is 38750",
      "filename": "sales_data.csv",
      "timestamp_ms": "1748401262472"
    },
    "type": "0x52d141a32883dd46c17986a78991d4f6cd4378351dcd884c1fcbd3faa13ff6e4::gemini::AiInferenceNFT"
  }
}
```

## Usage Examples

### 1. cURL Examples
```bash
# File analysis
curl -X POST http://localhost:3001/api/gemini/analyze \
  -F "file=@sales_data.csv" \
  -F "question=What is the total revenue?" \
  -F "userAddress=0xf74be72609a5d368f511ac5b9e690e9f23085dfd8f76a0d4a943bbbac142ed47"

# Text analysis
curl -X POST http://localhost:3001/api/gemini/analyze-text \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Summarize this text",
    "textContent": "Lorem ipsum dolor sit amet...",
    "userAddress": "0xf74be72609a5d368f511ac5b9e690e9f23085dfd8f76a0d4a943bbbac142ed47"
  }'

# Check enclave status
curl http://localhost:3001/api/gemini/status

# Get NFT details
curl http://localhost:3001/api/nft/0xd34da250884dd0fa9a476af662442093e7c3766e28c679dc8dc1e08a4bf2a272
```

### 2. JavaScript Frontend Example
```javascript
// File upload example
async function analyzeFile(file, question, userAddress) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('question', question);
  formData.append('userAddress', userAddress);

  try {
    const response = await fetch('http://localhost:3001/api/gemini/analyze', {
      method: 'POST',
      body: formData
    });

    const result = await response.json();
    
    if (result.success) {
      console.log('NFT created:', result.nft.id);
      console.log('Analysis:', result.analysis);
      window.open(result.explorerUrl, '_blank');
    } else {
      console.error('Error:', result.error);
    }
  } catch (error) {
    console.error('Request failed:', error);
  }
}

// Text analysis example
async function analyzeText(text, question, userAddress) {
  try {
    const response = await fetch('http://localhost:3001/api/gemini/analyze-text', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        question,
        textContent: text,
        userAddress
      })
    });

    const result = await response.json();
    return result;
  } catch (error) {
    console.error('Request failed:', error);
    throw error;
  }
}
```

## Production Deployment

### 1. PM2 Process Manager
```bash
npm install -g pm2

# Start application
pm2 start app.js --name gemini-backend

# Save PM2 configuration
pm2 save

# Setup startup script
pm2 startup

# Monitor logs
pm2 logs gemini-backend
```

### 2. Environment Variables for Production
```env
NODE_ENV=production
PORT=3001
ENCLAVE_ENDPOINT=http://54.91.81.96:3000
GEMINI_ENCLAVE_ID=0xcbbf5bb5bb60f3b1a5db4394a92be4a2e26cbf28924af12e3450ed6b6e0a784b
APP_PACKAGE_ID=0x52d141a32883dd46c17986a78991d4f6cd4378351dcd884c1fcbd3faa13ff6e4
GAS_BUDGET=100000000
```

### 3. Nginx Configuration
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

## Error Handling

The backend handles various error scenarios:

1. **File Upload Errors**: Size limits, invalid formats
2. **Enclave Communication Errors**: Network issues, invalid responses
3. **Blockchain Errors**: Gas issues, signature verification failures
4. **Validation Errors**: Invalid Sui addresses, missing fields

## Security Considerations

1. **Rate Limiting**: 10 requests per 15 minutes per IP
2. **File Size Limits**: 10MB maximum
3. **Input Validation**: Sui address format validation
4. **Error Sanitization**: Production mode hides internal errors

## Testing

### Health Check
```bash
curl http://localhost:3001/health
```

### Enclave Connectivity
```bash
curl http://localhost:3001/api/gemini/status
```

This Express backend provides a complete, production-ready integration with the Nautilus AI enclave for Gemini analysis and automatic NFT minting! 