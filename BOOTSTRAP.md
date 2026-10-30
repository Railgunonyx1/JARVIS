# Rust toolchain bootstrap recipe

This project targets Rust desktop components on KDE Wayland (Bazzite).

System build dependencies needed by Rust crates:
- gcc
- pkg-config
- cmake (some GTK/relm build helpers may need it)
- GTK4, libadwaita, and gtk4-layer-shell development packages (for GTK UI)
- Wayland client development headers (for layer-shell / protocol work)

Rust toolchain:
- rustup
- cargo / rustc

If `cargo` is not on PATH, install it via rustup and then continue in the workspace directory:
- curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
- source "$HOME/.cargo/env"
- rustup default stable

After the toolchain is available, the workspace can be prepared with:
- cd /var/home/Railgunonyx/Desktop/jarvis
- cargo init --name jarvis_dynamic_island --vcs none
- then add the workspace manifest and crates.

This file is a bootstrap note, not a build script.
