//! WebView2 engine bootstrap.
//!
//! Everything Windows- or COM-shaped lives here so that `orbit-core` stays
//! portable and testable. The first thing this module does is the thing the
//! whole migration hinges on: prove that Orbit can create a WebView2
//! environment and a controller on this machine, and report what the engine
//! will and will not let us do.
//!
//! Why raw `webview2-com` rather than a wrapper (wry, Tauri): Orbit needs
//! `ICoreWebView2Controller` itself — for `Fetch` domain request blocking, for
//! `PermissionRequested`, for per-profile controllers sharing one process
//! collection. Those are exactly the APIs wrappers hide. `orbit-probe` is how
//! we find out which of them actually work before committing to them.

use std::ffi::c_void;
use windows::core::{Interface, IUnknown, GUID, HSTRING};
use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::WindowsAndMessaging::*;

use webview2_com::{
    CoreWebView2EnvironmentOptions, CoreWebView2EnvironmentOptionsBuilder, CreateCoreWebView2EnvironmentOptions,
    CreateCoreWebView2ControllerOptions, CreateCoreWebView2ControllerOptionsBuilder, ICoreWebView2,
    ICoreWebView2Controller, ICoreWebView2Controller3, ICoreWebView2Environment,
};

pub const WEBVIEW2_BROWSER_EXECUTABLE_KEY: &str = "WEBVIEW2_BROWSER_EXECUTABLE_FOLDER";

/// Where the engine keeps browser data for one profile.
///
/// All profiles share ONE user data folder and are distinguished by
/// `--profile-directory`, which is what keeps them in a single browser process
/// collection. Giving each profile its own folder is what WebView2 documents as
/// expensive, and it is the mistake worth refusing to make at the type level.
pub fn profile_data_root() -> std::path::PathBuf {
    let base = std::env::var("LOCALAPPDATA")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_else(|_| ".".to_string());
    std::path::PathBuf::from(base).join("JARVIS").join("OrbitNative")
}

pub fn profile_dir_name(profile: &str) -> String {
    // Profile names come from config, not from the web, but they become a
    // directory name; refuse anything that could escape the root.
    let safe: String = profile
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
        .take(32)
        .collect();
    if safe.is_empty() {
        "Default".to_string()
    } else {
        safe
    }
}

/// A hidden-but-real Win32 parent window.
///
/// The controller must be parented to a real HWND; creating a window rather
/// than using an off-screen message loop keeps this testable in the same shape
/// the real shell will use.
pub struct ParentWindow {
    pub hwnd: HWND,
}

impl ParentWindow {
    pub fn new(title: &str, width: i32, height: i32) -> windows::core::Result<Self> {
        let hinstance = unsafe { GetModuleHandleW(None)? };
        let class_name = w!("OrbitProbeWindowClass");

        let wc = WNDCLASSW {
            lpfnWndProc: Some(DefWindowProcW),
            hInstance: hinstance.into(),
            lpszClassName: class_name,
            ..Default::default()
        };
        // Ignore ERROR_CLASS_ALREADY_EXISTS: a second run in the same session is
        // legitimate and reusing the class is correct.
        let _ = unsafe { RegisterClassW(&wc) };

        let hwnd = unsafe {
            CreateWindowExW(
                WINDOW_EX_STYLE(0),
                class_name,
                HSTRING::from(title),
                WS_OVERLAPPEDWINDOW,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                width,
                height,
                None,
                None,
                Some(hinstance.into()),
                None,
            )
        }?;
        let hwnd = HWND(hwnd.0);
        Ok(Self { hwnd })
    }

    pub fn show(&self) -> windows::core::Result<()> {
        unsafe { ShowWindow(self.hwnd, SW_SHOW) };
        Ok(())
    }
}

impl Drop for ParentWindow {
    fn drop(&mut self) {
        unsafe {
            let _ = DestroyWindow(self.hwnd);
        }
    }
}

/// Create the WebView2 environment for a user data folder.
///
/// The returned environment is the expensive object: one per browser process
/// collection, shared by every profile and every tab.
pub fn create_environment(user_data_folder: &std::path::Path) -> windows::core::Result<ICoreWebView2Environment> {
    let _ = std::fs::create_dir_all(user_data_folder);

    let options: CoreWebView2EnvironmentOptions = CreateCoreWebView2EnvironmentOptions(
        CoreWebView2EnvironmentOptionsBuilder::new()
            // Orbit injects its own scripts; the WebView2 devtools are a
            // separate concern and would add a second debugging surface.
            .with_additional_browser_arguments("--disable-extensions --remote-debugging-port=0")
            .build(),
    )?;

    let mut env: ICoreWebView2Environment = core::ptr::null_mut();
    let user_data = HSTRING::from(user_data_folder.to_string_lossy().as_ref());
    unsafe {
        webview2_com::CreateCoreWebView2EnvironmentWithOptions(
            &user_data,
            &options,
            None,
            &mut env,
        )
    }?;
    Ok(env)
}

/// Create a controller parented to `hwnd`.
pub fn create_controller(
    env: &ICoreWebView2Environment,
    hwnd: HWND,
) -> windows::core::Result<ICoreWebView2Controller> {
    let controller_options: CreateCoreWebView2ControllerOptions =
        CreateCoreWebView2ControllerOptions(CreateCoreWebView2ControllerOptionsBuilder::new().build());
    let mut controller: ICoreWebView2Controller = core::ptr::null_mut();
    unsafe {
        env.CreateCoreWebView2Controller(HSTRING::from("orbit"), &controller_options, Some(hwnd), &mut controller)
    }?;
    Ok(controller)
}

/// The live controller, narrowed to the interface that supports navigation.
pub fn controller_core(controller: &ICoreWebView2Controller) -> windows::core::Result<ICoreWebView2> {
    unsafe { Ok(controller.CoreWebView2()?) }
}

/// Pump pending messages so the WebView2 controller can attach.
///
/// WebView2 delivers its first events through the host's message loop. Without
/// this, `Navigate` is issued against a controller that has not finished
/// initialising and the navigation silently never completes — the single most
/// common way a first WebView2 program appears to hang.
pub fn pump(hwnd: HWND, iterations: u32) {
    unsafe {
        for _ in 0..iterations {
            let mut msg = MSG::default();
            while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {
                let _ = TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
            // Let the controller know the window exists and has a size.
            let _ = InvalidateRect(Some(hwnd), None, false);
            std::thread::sleep(std::time::Duration::from_millis(8));
        }
    }
}

/// Keep the window alive for the duration of the program.
pub fn pump_until(hwnd: HWND, deadline: std::time::Instant, stop: impl Fn() -> bool) -> bool {
    unsafe {
        let mut msg = MSG::default();
        while std::time::Instant::now() < deadline {
            if stop() {
                return true;
            }
            while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {
                let _ = TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
            std::thread::sleep(std::time::Duration::from_millis(8));
        }
    }
    false
}

/// COM initialisation for the calling thread.
///
/// Returns false if the thread was already initialised, which is not an error.
pub fn com_init() -> bool {
    let hr = unsafe {
        windows::Win32::System::Com::CoInitializeEx(
            None,
            windows::Win32::System::Com::COINIT_APARTMENTTHREADED,
        )
    };
    hr.is_ok()
}