# Copyright (c), Mysten Labs, Inc.
# SPDX-License-Identifier: Apache-2.0
#!/bin/bash

# Gets the encalve id and CID
# expects there to be only one enclave running
ENCLAVE_ID=$(nitro-cli describe-enclaves | jq -r ".[0].EnclaveID")
ENCLAVE_CID=$(nitro-cli describe-enclaves | jq -r ".[0].EnclaveCID")

sleep 5
# Secrets-block
SECRET_VALUE=$(aws secretsmanager get-secret-value --secret-id  --region us-east-1 | jq -r .SecretString)
echo "$SECRET_VALUE" | jq -R '{"API_KEY": .}' > secrets.json
# Combine both secrets into a single JSON

socat TCP4-LISTEN:3000,reuseaddr,fork VSOCK-CONNECT:$ENCLAVE_CID:3000 &