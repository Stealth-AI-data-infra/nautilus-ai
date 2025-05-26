#!/bin/bash
# Verification script to ensure all changes are correctly applied

echo "=== Verifying Local Changes for Gemini Integration ==="
echo ""

echo "1. Checking expose_enclave.sh secrets handling:"
echo "-------------------------------------------"
grep -A 2 "# Secrets-block" expose_enclave.sh
echo ""

echo "2. Checking run.sh endpoint mappings:"
echo "------------------------------------"
echo "Host entries:"
grep -E "echo.*127\.0\.0\.[0-9]+.*>> /etc/hosts" src/nautilus-server/run.sh | head -10
echo ""
echo "Traffic forwarders:"
grep "python3 /traffic_forwarder.py" src/nautilus-server/run.sh | head -10
echo ""

echo "3. Checking allowed_endpoints.yaml:"
echo "----------------------------------"
cat src/nautilus-server/allowed_endpoints.yaml
echo ""

echo "4. Checking secrets template:"
echo "----------------------------"
cat secrets_template.json
echo ""

echo "5. Checking new files exist:"
echo "---------------------------"
echo -n "gemini.rs: "; [ -f "src/nautilus-server/src/gemini.rs" ] && echo "✓ EXISTS" || echo "✗ MISSING"
echo -n "gemini.move: "; [ -f "move/app/sources/gemini.move" ] && echo "✓ EXISTS" || echo "✗ MISSING"
echo -n "query_gemini.sh: "; [ -f "query_gemini.sh" ] && echo "✓ EXISTS" || echo "✗ MISSING"
echo -n "gemini_query_helper.py: "; [ -f "gemini_query_helper.py" ] && echo "✓ EXISTS" || echo "✗ MISSING"
echo ""

echo "6. Checking Gemini module declaration in main.rs:"
echo "------------------------------------------------"
grep "mod gemini" src/nautilus-server/src/main.rs || echo "Gemini module declaration not found"
echo ""

echo "=== Verification Complete ==="
echo ""
echo "If all checks pass, you can:"
echo "1. Commit and push these changes to your repository"
echo "2. Pull them on your EC2 instance"
echo "3. Follow the deployment steps in deployment_guide.md" 