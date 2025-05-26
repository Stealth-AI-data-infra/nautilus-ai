# Complete Nautilus Deployment Guide

A comprehensive guide for deploying Nautilus to AWS with weather API integration, persistent services, and on-chain attestation contracts.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Part 1: AWS Infrastructure Setup](#part-1-aws-infrastructure-setup)
3. [Part 2: Server Configuration](#part-2-server-configuration)
4. [Part 3: Deploy Attestation Contracts](#part-3-deploy-attestation-contracts)
5. [Testing & Verification](#testing--verification)
6. [Troubleshooting](#troubleshooting)
7. [Key Learnings](#key-learnings)

---

## Prerequisites

### On Windows Local Machine
1. **Install required tools:**
   ```powershell
   # Install Python 3.x
   # Install AWS CLI
   pip install boto3 pyyaml
   ```

2. **Configure AWS credentials:**
   ```powershell
   aws configure
   # Enter your AWS Access Key ID
   # Enter your AWS Secret Access Key
   # Enter default region (e.g., us-east-1)
   ```

3. **Prepare your SSH key pair:**
   - Create or use existing AWS key pair
   - Save the .pem file to `~/.ssh/`
   - Set permissions: `icacls ~/.ssh/your-key.pem /inheritance:r /grant:r "%USERNAME%":"(R)"`

---

## Part 1: AWS Infrastructure Setup

### Step 1: Create Configuration File

Create `nautilus_config.json`:
```json
{
  "key_pair": "your-aws-keypair-name",
  "region": "us-east-1",
  "instance_name": "nautilus-server",
  "use_secret": true,
  "secret_name": "nautilus-secrets",
  "secret_value": "{\"weatherApiKey\":\"your-weather-api-key\"}"
}
```

### Step 2: Deploy Infrastructure

```powershell
python nautilus_deploy_improved.py nautilus_config.json
```

This will:
- Create security group (ports 22, 443, 3000)
- Create IAM role with secrets access
- Store weather API key in AWS Secrets Manager
- Launch m5.xlarge EC2 instance with Nitro Enclave
- Configure vsock-proxy endpoints

### Step 3: Wait for Deployment

Wait 10-15 minutes for instance initialization, then SSH in:
```powershell
ssh -i ~/.ssh/your-key.pem ec2-user@<public-ip>
```

---

## Part 2: Server Configuration

### Step 1: Clone Repository and Initial Setup

```bash
# Clone your repository
git clone https://github.com/your-repo/nautilus-deployment.git nautilus
cd nautilus

# Make scripts executable
chmod +x expose_enclave.sh run.sh configure_enclave.sh update_weather.sh
```

### Step 2: Build the Enclave

```bash
# Build the enclave
make

# This creates nautilus-server.eif in the root directory
```

### Step 3: Create Systemd Services

**Important:** We use `Type=simple` and `RemainAfterExit=yes` for proper service management.

#### A. Enclave Service
```bash
sudo tee /etc/systemd/system/nautilus-enclave.service > /dev/null << 'EOF'
[Unit]
Description=Nautilus Enclave Service
After=network.target nitro-enclaves-allocator.service
Requires=nitro-enclaves-allocator.service

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/nautilus
ExecStartPre=/bin/bash -c 'sudo systemctl restart nitro-enclaves-allocator.service && sleep 5'
ExecStart=/usr/bin/nitro-cli run-enclave --cpu-count 2 --memory 1024 --eif-path /home/ec2-user/nautilus/nautilus-server.eif --debug-mode
RemainAfterExit=yes
ExecStop=/bin/bash -c 'nitro-cli terminate-enclave --all || true'
ExecStopPost=/bin/bash -c 'pid=$(nitro-cli describe-enclaves | jq -r ".[0].ProcessID // empty") && [ -n "$pid" ] && sudo kill -9 $pid || true'
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
```

#### B. Expose Service
```bash
sudo tee /etc/systemd/system/nautilus-expose.service > /dev/null << 'EOF'
[Unit]
Description=Nautilus Expose Service
After=nautilus-enclave.service
Requires=nautilus-enclave.service

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/nautilus
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStartPre=/bin/sleep 60
ExecStart=/bin/bash -c 'cd /home/ec2-user/nautilus && exec ./expose_enclave.sh'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

#### C. VSOCK Proxy Service
```bash
sudo tee /etc/systemd/system/nautilus-vsock-proxy.service > /dev/null << 'EOF'
[Unit]
Description=Nautilus VSOCK Proxy Service
After=network.target nitro-enclaves-allocator.service
Requires=nitro-enclaves-allocator.service

[Service]
Type=simple
ExecStart=/usr/bin/vsock-proxy 8101 api.weatherapi.com 443 --config /etc/nitro_enclaves/vsock-proxy.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

### Step 4: Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable all services
sudo systemctl enable nautilus-enclave.service
sudo systemctl enable nautilus-expose.service  
sudo systemctl enable nautilus-vsock-proxy.service

# Start services
sudo systemctl start nautilus-vsock-proxy.service
sudo systemctl start nautilus-enclave.service
# The expose service will start automatically after enclave
```

### Step 5: Verify Services

```bash
# Check all services
sudo systemctl status nautilus-enclave nautilus-expose nautilus-vsock-proxy

# Wait for expose service to complete startup (60 seconds)
sleep 65

# Test endpoints
curl http://127.0.0.1:3000/health
curl http://127.0.0.1:3000/allowed_endpoints
```

---

## Part 3: Deploy Attestation Contracts

### Step 1: Install Sui CLI with Docker

Due to GLIBC version requirements on Amazon Linux, we use Docker:

```bash
# Pull Sui Docker image
sudo docker pull mysten/sui-tools:stable

# Create interactive wrapper script
cat > ~/sui << 'EOF'
#!/bin/bash
sudo docker run -it --rm \
  -v ~/.sui:/root/.sui \
  -v $(pwd):/workspace \
  -w /workspace \
  mysten/sui-tools:stable sui "$@"
EOF

chmod +x ~/sui

# Add to PATH
echo 'export PATH=$HOME:$PATH' >> ~/.bashrc
source ~/.bashrc
```

### Step 2: Initialize Sui Configuration

```bash
# Create config directory
mkdir -p ~/.sui

# Initialize Sui (choose testnet)
sui client new-address ed25519
# Enter: y, 1 (for testnet), (0 for ed25519)

# Switch to the new address
sui client switch --address $(sui client addresses | head -1)

# Get test SUI from faucet
curl -X POST https://faucet.testnet.sui.io/v1/gas \
  -H "Content-Type: application/json" \
  -d "{\"FixedAmountRequest\":{\"recipient\":\"$(sui client active-address)\"}}"
```

### Step 3: Deploy Contracts

```bash
# Navigate to move directory
cd ~/nautilus/move

# Build the enclave package
sui move build --path enclave

# Publish enclave package
sui client publish enclave
# Save the package ID

# Build the app package 
sui move build --path app

# Publish app package
sui client publish app
```

### Step 4: Extract Object IDs

From the app deployment output, save:
```bash
# From enclave deployment
export ENCLAVE_PACKAGE_ID=<enclave-package-id>

# From app deployment  
export EXAMPLES_PACKAGE_ID=<app-package-id>
export WEATHER_CAP_ID=<weather-cap-object-id>
export ENCLAVE_CONFIG_ID=<enclave-config-object-id>
```

### Step 5: Register Enclave

```bash
# Get current timestamp
export CURRENT_TIMESTAMP=$(date +%s)000

# Register enclave
sui client call \
  --package $ENCLAVE_PACKAGE_ID \
  --module enclave \
  --function register_enclave \
  --args \
    $WEATHER_CAP_ID \
    $ENCLAVE_CONFIG_ID \
    "$CURRENT_TIMESTAMP"

# Save the created Enclave object ID
export ENCLAVE_OBJECT_ID=<created-enclave-object-id>
```

### Step 6: Update Weather Data

```bash
# Create configuration file
cat > ~/nautilus/.env << EOF
export ENCLAVE_PACKAGE_ID=$ENCLAVE_PACKAGE_ID
export EXAMPLES_PACKAGE_ID=$EXAMPLES_PACKAGE_ID  
export WEATHER_CAP_ID=$WEATHER_CAP_ID
export ENCLAVE_CONFIG_ID=$ENCLAVE_CONFIG_ID
export ENCLAVE_OBJECT_ID=$ENCLAVE_OBJECT_ID
EOF

# Source the configuration
source ~/nautilus/.env

# Update weather for a city
./update_weather.sh \
  $EXAMPLES_PACKAGE_ID \
  weather \
  WEATHER \
  $ENCLAVE_OBJECT_ID \
  "your-weather-api-key" \
  $(date +%s)000 \
  "San Francisco" \
  14
```

---

## Testing & Verification

### From the Server

```bash
# Check service status
sudo systemctl status nautilus-enclave nautilus-expose nautilus-vsock-proxy

# Test locally
curl http://127.0.0.1:3000/health
curl http://127.0.0.1:3000/process_data \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"payload":{"location":"New York"}}'
```

### From Windows (PowerShell)

```powershell
# Test health endpoint
Invoke-RestMethod -Uri "http://<public-ip>:3000/health"

# Test weather data (view full response)
$response = Invoke-RestMethod -Uri "http://<public-ip>:3000/process_data" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"payload":{"location":"New York"}}'

$response | ConvertTo-Json -Depth 10
```

### Verify on Blockchain

```bash
# View your weather NFT on Sui Explorer
echo "https://suiscan.xyz/testnet/object/<your-weather-nft-id>"
```

---

## Part 4: Google Gemini API Integration

### Prerequisites

1. **Get a Gemini API Key**
   - Visit https://makersuite.google.com/app/apikey
   - Create a new API key
   - Save it securely

### Step 1: Update AWS Secrets

From your Windows machine:
```powershell
# Update secrets to include both weather and Gemini API keys
aws secretsmanager update-secret `
  --secret-id nautilus-secrets `
  --secret-string "{\"weatherApiKey\":\"your-weather-api-key\",\"geminiApiKey\":\"your-gemini-api-key\"}" `
  --region us-east-1
```

### Step 2: Install Python Dependencies

On the server:
```bash
# Install required Python packages
pip3 install --user google-generativeai requests
```

### Step 3: Update VSOCK Proxy Configuration

```bash
# Add Gemini endpoints to vsock proxy
echo "- {address: generativelanguage.googleapis.com, port: 443}" | sudo tee -a /etc/nitro_enclaves/vsock-proxy.yaml
echo "- {address: storage.googleapis.com, port: 443}" | sudo tee -a /etc/nitro_enclaves/vsock-proxy.yaml

# Update the vsock proxy service
sudo tee /etc/systemd/system/nautilus-vsock-proxy.service > /dev/null << 'EOF'
[Unit]
Description=Nautilus VSOCK Proxy Service
After=network.target nitro-enclaves-allocator.service

[Service]
Type=forking
ExecStart=/bin/bash -c 'vsock-proxy 8101 api.weatherapi.com 443 --config /etc/nitro_enclaves/vsock-proxy.yaml & \
vsock-proxy 8102 generativelanguage.googleapis.com 443 --config /etc/nitro_enclaves/vsock-proxy.yaml & \
vsock-proxy 8103 storage.googleapis.com 443 --config /etc/nitro_enclaves/vsock-proxy.yaml &'
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart nautilus-vsock-proxy
```

### Step 4: Deploy Gemini Contracts

```bash
# Navigate to move directory
cd ~/nautilus/move

# Build the app package with Gemini module
sui move build --path app

# Publish updated app package
sui client publish app

# Save the new package ID and Gemini Cap ID
export GEMINI_CAP_ID=<gemini-cap-object-id>
export NEW_APP_PACKAGE_ID=<new-app-package-id>

# Update your .env file
echo "export GEMINI_CAP_ID=$GEMINI_CAP_ID" >> ~/.env
echo "export GEMINI_PACKAGE_ID=$NEW_APP_PACKAGE_ID" >> ~/.env
source ~/.env
```

### Step 5: Test Gemini Integration

#### A. Create Test Data
```bash
# Create a sample CSV file
cat > ~/test_data.csv << 'EOF'
Product,Sales,Quarter
Widget A,150,Q1
Widget B,200,Q1
Widget A,180,Q2
Widget B,220,Q2
EOF
```

#### B. Test Locally
```bash
# Test the Gemini endpoint
curl -X POST http://127.0.0.1:3000/process_gemini \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "question": "What were the total sales for Widget A?",
      "file_content": "'$(base64 -w 0 ~/test_data.csv)'",
      "file_type": "csv"
    }
  }'
```

#### C. Test from Windows
```powershell
# Prepare test file
$csvContent = @"
Product,Sales,Quarter
Widget A,150,Q1
Widget B,200,Q1
Widget A,180,Q2
Widget B,220,Q2
"@

$bytes = [System.Text.Encoding]::UTF8.GetBytes($csvContent)
$base64 = [Convert]::ToBase64String($bytes)

# Test Gemini endpoint
$body = @{
    payload = @{
        question = "What were the total sales for Widget A?"
        file_content = $base64
        file_type = "csv"
    }
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://<public-ip>:3000/process_gemini" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body

$response | ConvertTo-Json -Depth 10
```

### Step 6: Query Gemini with Move Script

```bash
# Use the helper script
./query_gemini.sh \
  $GEMINI_PACKAGE_ID \
  gemini \
  GEMINI \
  $ENCLAVE_OBJECT_ID \
  $(date +%s)000 \
  "What is the trend in sales data?" \
  "$(base64 -w 0 ~/test_data.csv)" \
  "csv"
```

---

## Troubleshooting

### Common Issues

1. **Enclave won't start**
   ```bash
   # Kill any existing enclaves
   nitro-cli describe-enclaves
   pid=$(nitro-cli describe-enclaves | jq -r ".[0].ProcessID")
   sudo kill -9 $pid
   nitro-cli terminate-enclave --all
   ```

2. **Expose service keeps restarting**
   - Check if enclave is running: `nitro-cli describe-enclaves`
   - Verify CID in expose_enclave.sh matches running enclave
   - Check logs: `sudo journalctl -u nautilus-expose -f`

3. **VSOCK proxy not working**
   ```bash
   # Check if process is running
   ps aux | grep vsock-proxy
   
   # Restart the service
   sudo systemctl restart nautilus-vsock-proxy
   ```

4. **Sui CLI issues**
   - Ensure Docker wrapper is executable: `chmod +x ~/sui`
   - Check keystore exists: `ls -la ~/.sui/sui_config/`
   - Verify active address: `sui client active-address`

---

## Key Learnings

### Infrastructure
- Use `Type=simple` with `RemainAfterExit=yes` for enclave service
- Add 60-second delay in expose service to ensure enclave is ready
- Force kill enclaves with PID when standard termination fails

### Sui Deployment  
- Use Docker wrapper for Sui CLI on Amazon Linux
- Build packages from parent directory, not inside package folder
- Don't use `--path` flag with `sui client publish`
- Interactive mode (`-it`) required for Docker wrapper

### Networking
- Use `127.0.0.1` instead of `localhost` for local testing
- VSOCK proxy must be running for external API calls
- Port 3000 must be open in security group

### Best Practices
- Always save deployment output for object IDs
- Create `.env` file for easy configuration management
- Test locally before remote access
- Monitor services with `journalctl -f`

---

## Production Considerations

1. **Security**
   - Restrict SSH access to specific IPs
   - Use VPC with private subnets
   - Implement API rate limiting
   - Rotate API keys regularly

2. **Monitoring**
   - Set up CloudWatch alarms
   - Configure log aggregation
   - Monitor enclave health
   - Track gas usage on Sui

3. **Backup**
   - Backup Sui wallet keystore
   - Save all deployment configurations
   - Document all object IDs
   - Create AMI snapshots

4. **Scaling**
   - Use Auto Scaling Groups
   - Implement load balancing
   - Consider multi-region deployment
   - Cache frequently accessed data

---

## Support

For issues or questions:
- Check service logs: `sudo journalctl -u <service-name> -f`
- Verify enclave status: `nitro-cli describe-enclaves`
- Test endpoints individually
- Review AWS CloudWatch logs

This guide is based on real deployment experience and includes all discovered optimizations and fixes.