// Copyright (c), Mysten Labs, Inc.
// SPDX-License-Identifier: Apache-2.0

use crate::common::IntentMessage;
use crate::common::{to_signed_response, IntentScope, ProcessDataRequest, ProcessedDataResponse};
use crate::{AppState, EnclaveError};
use axum::extract::State;
use axum::Json;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;
use sha2::{Sha256, Digest};
use reqwest;
use base64::{Engine as _, engine::general_purpose};

/// Inner type T for IntentMessage<T>
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GeminiResponse {
    pub question: String,
    pub answer: String,
    pub model: String,
    pub file_hash: Vec<u8>,
}

/// Inner type T for ProcessDataRequest<T>
#[derive(Debug, Serialize, Deserialize)]
pub struct GeminiRequest {
    pub question: String,
    pub file_content: String, // Base64 encoded file content
    pub file_type: String,    // mime type
}

pub async fn process_gemini_query(
    State(state): State<Arc<AppState>>,
    Json(request): Json<ProcessDataRequest<GeminiRequest>>,
) -> Result<Json<ProcessedDataResponse<IntentMessage<GeminiResponse>>>, EnclaveError> {
    // Decode the base64 file content
    let file_bytes = general_purpose::STANDARD.decode(&request.payload.file_content)
        .map_err(|e| EnclaveError::GenericError(format!("Failed to decode file content: {}", e)))?;
    
    let mut hasher = Sha256::new();
    hasher.update(&file_bytes);
    let file_hash = hasher.finalize().to_vec();

    // Prepare Gemini API request
    let model = "gemini-1.5-flash"; // or "gemini-1.5-pro"
    let url = format!(
        "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}",
        model, state.gemini_api_key
    );

    let prompt = format!(
        "Analyze the following {} file and answer this question: {}\n\nFile content:\n{}",
        request.payload.file_type,
        request.payload.question,
        String::from_utf8_lossy(&file_bytes)
    );

    let body = serde_json::json!({
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
        }
    });

    let client = reqwest::Client::new();
    let response = client
        .post(&url)
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .await
        .map_err(|e| EnclaveError::GenericError(format!("Failed to call Gemini API: {}", e)))?;

    if !response.status().is_success() {
        let error_text = response.text().await.unwrap_or_default();
        return Err(EnclaveError::GenericError(format!("Gemini API error: {}", error_text)));
    }

    let json = response.json::<Value>().await
        .map_err(|e| EnclaveError::GenericError(format!("Failed to parse Gemini response: {}", e)))?;

    let answer = json["candidates"][0]["content"]["parts"][0]["text"]
        .as_str()
        .unwrap_or("No response generated");

    let current_timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|e| EnclaveError::GenericError(format!("Failed to get timestamp: {}", e)))?
        .as_millis() as u64;

    Ok(Json(to_signed_response(
        &state.eph_kp,
        GeminiResponse {
            question: request.payload.question.clone(),
            answer: answer.to_string(),
            model: model.to_string(),
            file_hash,
        },
        current_timestamp,
        IntentScope::Gemini,
    )))
} 