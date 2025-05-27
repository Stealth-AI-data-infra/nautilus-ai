// Copyright (c), Mysten Labs, Inc.
// SPDX-License-Identifier: Apache-2.0

module app::gemini;

use enclave::enclave::{Self, Enclave};
use std::string::String;

/// ====
/// Gemini AI inference attestation logic
/// ====

const GEMINI_INTENT: u8 = 1;
const EInvalidSignature: u64 = 1;

public struct AiInferenceNFT has key, store {
    id: UID,
    question: String,
    answer: String,
    filename: String,
    timestamp_ms: u64,
}

/// Should match the inner struct T used for IntentMessage<T> in Rust.
public struct GeminiResponse has copy, drop {
    question: String,
    answer: String,
    filename: String,
}

public struct GEMINI has drop {}

fun init(otw: GEMINI, ctx: &mut TxContext) {
    let cap = enclave::new_cap(otw, ctx);

    cap.create_enclave_config(
        b"gemini enclave".to_string(),
        x"000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000", // pcr0
        x"000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000", // pcr1
        x"000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000", // pcr2
        ctx,
    );

    transfer::public_transfer(cap, ctx.sender())
}

public fun query_gemini<T>(
    question: String,
    answer: String,
    filename: String,
    timestamp_ms: u64,
    sig: &vector<u8>,
    enclave: &Enclave<T>,
    ctx: &mut TxContext,
): AiInferenceNFT {
    let res = enclave.verify_signature(
        GEMINI_INTENT,
        timestamp_ms,
        GeminiResponse { question, answer, filename },
        sig,
    );
    assert!(res, EInvalidSignature);
    
    AiInferenceNFT {
        id: object::new(ctx),
        question,
        answer,
        filename,
        timestamp_ms,
    }
} 