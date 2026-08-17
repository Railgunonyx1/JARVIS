"""Terminal domain — frozen types, events, reducers, store, intents, keymap, breakpoints.

Architecture contract:
    Terminal UI → UIIntent → Event Bus → Core Kernel
    Core owns decisions. Events describe what happened.
    Terminal converts input into intents. Renderer only displays state.
"""
