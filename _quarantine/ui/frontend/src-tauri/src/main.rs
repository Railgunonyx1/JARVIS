#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::sync::Mutex;
use tauri::State;

// ── App State ──

struct AppState {
    backend_host: String,
    backend_port: u16,
}

impl AppState {
    fn new() -> Self {
        Self {
            backend_host: "127.0.0.1".to_string(),
            backend_port: 8765,
        }
    }
}

struct AppStateWrapper(Mutex<AppState>);

// ── Commands ──

#[derive(Debug, Serialize)]
struct BackendStatus {
    running: bool,
    ok: bool,
    report: String,
    error: Option<String>,
}

#[tauri::command]
async fn check_backend(state: State<'_, AppStateWrapper>) -> Result<BackendStatus, String> {
    let url = {
        let app = state.0.lock().map_err(|e| e.to_string())?;
        format!("http://{}:{}/api/health", app.backend_host, app.backend_port)
    };

    match reqwest::get(&url).await {
        Ok(resp) => match resp.json::<serde_json::Value>().await {
            Ok(json) => {
                let ok = json.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
                let report = json
                    .get("report")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                Ok(BackendStatus {
                    running: true,
                    ok,
                    report,
                    error: None,
                })
            }
            Err(e) => Ok(BackendStatus {
                running: true,
                ok: false,
                report: String::new(),
                error: Some(format!("Failed to parse health response: {}", e)),
            }),
        },
        Err(e) => Ok(BackendStatus {
            running: false,
            ok: false,
            report: String::new(),
            error: Some(format!("Backend unreachable: {}", e)),
        }),
    }
}

// ── Entry Point ──

fn main() {
    tauri::Builder::default()
        .manage(AppStateWrapper(Mutex::new(AppState::new())))
        .invoke_handler(tauri::generate_handler![check_backend])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
