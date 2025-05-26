#!/bin/bash
# Deployment script for Gemini API integration
# Run this on your EC2 instance after pulling the updated code

set -e

echo "=== Nautilus Gemini Integration Deployment ==="
echo ""

# Check if we're in the right directory
if [ ! -f "Makefile" ] || [ ! -d "src/nautilus-server" ]; then
    echo "Error: Please run this script from the nautilus repository root"
    exit 1
fi

# Step 1: Backup current configuration
echo "Step 1: Backing up current configuration..."
mkdir -p ~/nautilus-backup-$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=~/nautilus-backup-$(date +%Y%m%d-%H%M%S)
cp .env $BACKUP_DIR/ 2>/dev/null || true
cp secrets.json $BACKUP_DIR/ 2>/dev/null || true
echo "✓ Backup created in $BACKUP_DIR"

# Step 2: Install Python dependencies
echo ""
echo "Step 2: Installing Python dependencies..."
pip3 install --user google-generativeai requests
echo "✓ Python dependencies installed"

# Step 3: Update VSOCK proxy configuration
echo ""
echo "Step 3: Updating VSOCK proxy configuration..."
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
echo "✓ VSOCK proxy configuration updated"

# Step 4: Stop services
echo ""
echo "Step 4: Stopping existing services..."
sudo systemctl stop nautilus-expose 2>/dev/null || true
sudo systemctl stop nautilus-enclave 2>/dev/null || true

# Force kill any remaining enclaves
pid=$(nitro-cli describe-enclaves | jq -r ".[0].ProcessID // empty")
if [ -n "$pid" ]; then
    echo "Force killing enclave process $pid..."
    sudo kill -9 $pid 2>/dev/null || true
fi
nitro-cli terminate-enclave --all 2>/dev/null || true
echo "✓ Services stopped"

# Step 5: Rebuild enclave
echo ""
echo "Step 5: Rebuilding enclave with Gemini support..."
make clean
make
echo "✓ Enclave rebuilt"

# Step 6: Restart services
echo ""
echo "Step 6: Restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart nautilus-vsock-proxy
sleep 5
sudo systemctl start nautilus-enclave
echo "Waiting for enclave to initialize..."
sleep 10

# Get new CID
NEW_CID=$(nitro-cli describe-enclaves | jq -r ".[0].EnclaveCID // empty")
if [ -z "$NEW_CID" ]; then
    echo "Error: Enclave failed to start"
    exit 1
fi
echo "Enclave started with CID: $NEW_CID"

sudo systemctl start nautilus-expose
echo "✓ All services restarted"

# Step 7: Verify services
echo ""
echo "Step 7: Verifying services..."
sleep 65  # Wait for expose service startup delay

# Check service status
for service in nautilus-enclave nautilus-expose nautilus-vsock-proxy; do
    if sudo systemctl is-active --quiet $service; then
        echo "✓ $service is running"
    else
        echo "✗ $service is not running!"
        sudo systemctl status $service --no-pager | head -10
    fi
done

# Step 8: Test endpoints
echo ""
echo "Step 8: Testing endpoints..."
echo -n "Health check: "
if curl -s http://127.0.0.1:3000/health | grep -q "healthy"; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
fi

echo -n "Weather API: "
if curl -s http://127.0.0.1:3000/allowed_endpoints | grep -q "api.weatherapi.com"; then
    echo "✓ Available"
else
    echo "✗ Not found"
fi

echo -n "Gemini API: "
if curl -s http://127.0.0.1:3000/allowed_endpoints | grep -q "generativelanguage.googleapis.com"; then
    echo "✓ Available"
else
    echo "✗ Not found"
fi

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Next steps:"
echo "1. Update AWS Secrets Manager with both API keys (if not already done)"
echo "2. Deploy the updated Move contracts (see deployment_guide.md Part 4)"
echo "3. Test Gemini integration with the sample commands in the guide"
echo ""
echo "To test Gemini locally:"
echo 'curl -X POST http://127.0.0.1:3000/process_gemini -H "Content-Type: application/json" -d '"'"'{"payload":{"question":"Hello","file_content":"","file_type":"txt"}}'"'" 