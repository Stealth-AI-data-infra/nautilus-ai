// Copyright (c), Mysten Labs, Inc.
// SPDX-License-Identifier: Apache-2.0

use crate::common::IntentMessage;
use crate::common::{to_signed_response, IntentScope, ProcessDataRequest, ProcessedDataResponse};
use crate::AppState;
use crate::EnclaveError;
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
        "Analyze the following {} file and answer this question: {}\n\nFile content:\n{}\n\nIMPORTANT: Provide a clear, concise answer without using any special characters, markdown formatting, asterisks, dollar signs, or newlines. Use only plain text with spaces.",
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

    let raw_answer = json["candidates"][0]["content"]["parts"][0]["text"]
        .as_str()
        .unwrap_or("No response generated");

    // Clean the answer to make it blockchain-friendly
    let clean_answer = raw_answer
        .replace('\n', " ")          // Replace newlines with spaces
        .replace('\r', " ")          // Replace carriage returns
        .replace('\t', " ")          // Replace tabs with spaces
        .replace("**", "")           // Remove markdown bold
        .replace("*", "")            // Remove markdown italic/lists
        .replace("$", "USD ")        // Replace dollar signs
        .replace("#", "")            // Remove headers
        .replace("`", "'")           // Replace backticks
        .replace("\"", "'")          // Replace quotes with single quotes
        .replace("\\", "/")          // Replace backslashes
        .replace("  ", " ")          // Replace double spaces
        .trim()                      // Trim whitespace
        .to_string();

    // Also clean the question for consistency
    let clean_question = request.payload.question
        .replace('\n', " ")
        .replace('\r', " ")
        .replace("\"", "'")
        .trim()
        .to_string();

    let current_timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|e| EnclaveError::GenericError(format!("Failed to get timestamp: {}", e)))?
        .as_millis() as u64;

    Ok(Json(to_signed_response(
        &state.eph_kp,
        GeminiResponse {
            question: clean_question,
            answer: clean_answer,
            model: model.to_string(),
            file_hash,
        },
        current_timestamp,
        IntentScope::Gemini,
    )))
} 