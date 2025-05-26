// Copyright (c), Mysten Labs, Inc.
// SPDX-License-Identifier: Apache-2.0

use anyhow::Result;
use axum::{routing::get, routing::post, Router};
use fastcrypto::{ed25519::Ed25519KeyPair, traits::KeyPair};
use nautilus_server::app::process_data;
use nautilus_server::common::{get_attestation, health_check};
use nautilus_server::AppState;
use nautilus_server::gemini::process_gemini_query;
use std::sync::Arc;
use tower_http::cors::{Any, CorsLayer};
use tracing::info;

mod app;
mod common;
mod gemini;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let eph_kp = Ed25519KeyPair::generate(&mut rand::thread_rng());

    // Fetch API keys from environment variables (set by secrets.json)
    let api_key = std::env::var("weatherApiKey").expect("weatherApiKey must be set");
    let gemini_api_key = std::env::var("geminiApiKey").expect("geminiApiKey must be set");

    let state = Arc::new(AppState { 
        eph_kp, 
        api_key, 
        gemini_api_key 
    });

    // Define your own restricted CORS policy here if needed.
    let cors = CorsLayer::new().allow_methods(Any).allow_headers(Any);

    let app = Router::new()
        .route("/", get(ping))
        .route("/get_attestation", get(get_attestation))
        .route("/process_data", post(process_data))
        .route("/health_check", get(health_check))
        .route("/process_gemini", post(process_gemini_query))
        .with_state(state)
        .layer(cors);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await?;
    info!("listening on {}", listener.local_addr().unwrap());
    axum::serve(listener, app.into_make_service())
        .await
        .map_err(|e| anyhow::anyhow!("Server error: {}", e))
}

async fn ping() -> &'static str {
    "Pong!"
}
