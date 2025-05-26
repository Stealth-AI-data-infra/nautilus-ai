# Nautilus AI Integration Changes

## New Features Added

### Google Gemini AI Integration
- New Move contract for AI inference attestation (move/app/sources/gemini.move)
- Gemini API endpoint implementation (src/nautilus-server/src/gemini.rs)
- File processing with SHA256 hashing for data integrity
- Support for multiple file types (JSON, CSV, TXT, MD)

### Infrastructure Updates
- Extended allowed endpoints for Google APIs
- Additional VSOCK proxy configuration for Gemini services
- Updated secrets management to support multiple API keys

### Helper Scripts
- query_gemini.sh - Script to submit AI inference results on-chain
- gemini_query_helper.py - Python helper for querying Gemini through the enclave
- 
autilus-vsock-gemini.service - Systemd service for Gemini VSOCK proxies

### Deployment Improvements
- 
autilus_deploy_improved.py - Windows-compatible AWS deployment script
- Docker-based Sui CLI installation for Amazon Linux compatibility
- Improved systemd service configurations with proper restart handling

## Modified Files

1. src/nautilus-server/allowed_endpoints.yaml - Added Google API endpoints
2. src/nautilus-server/src/common.rs - Added Gemini intent scope
3. src/nautilus-server/src/main.rs - Added Gemini route and module
4. src/nautilus-server/src/lib.rs - Added gemini_api_key to AppState
5. src/nautilus-server/Cargo.toml - Added sha2 and base64 dependencies
6. configure_enclave.sh - Added Gemini endpoint configuration

## Setup Instructions

See NAUTILUS_DEPLOYMENT_GUIDE.md for complete setup and deployment instructions.
