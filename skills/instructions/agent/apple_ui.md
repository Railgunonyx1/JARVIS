---
name: apple-ui
description: High-quality UI design following Apple's human interface guidelines. San Francisco typography, monochrome palette, depth through layering not shadows, subtle micro-interactions, and system-native components. Lightweight implementation focused on readability and accessibility.
---

# Protocol: Apple Human Interface Design (Lightweight & High Quality)

## 1. Protocol Overview

Name: Apple-Inspired UI Design for JARVIS Desktop
Description: A lightweight, high-quality frontend design system inspired by Apple's Human Interface Guidelines. Emphasizes clarity, depth through layering rather than shadows, system-native San Francisco typography, subtle micro-interactions, and a monochrome palette with tasteful accents. Prioritizes readability, accessibility, and performance over visual clutter.

## 2. Absolute Negative Constraints (Banned Elements)

- DO NOT use gradients, glassmorphism, or blur effects that hurt performance
- DO NOT use heavy drop shadows or box-shadows (depth through layering only)
- DO NOT use bright primary-colored backgrounds for large sections
- DO NOT use rounded-full pill shapes for containers or primary buttons
- DO NOT use neon colors or high-saturation accent colors
- DO NOT use emojis anywhere in code, markup, text content, headings, or alt text
- DO NOT use generic placeholder names or AI copywriting clichés
- DO NOT overload with animations; motion should be subtle and purposeful

## 3. Typographic Architecture (San Francisco System Fonts)

- Primary Sans-Serif: `font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif`
- Monospace: `font-family: 'SF Mono', 'Menlo', 'Monaco', 'Courier New', monospace`
- Text Colors:
  - Primary text: `#1D1D1F` (near-black, not absolute black)
  - Secondary text: `#86868B` (muted gray)
  - Tertiary text: `#AEAEB2` (light gray for captions)
- Line-height: `1.5` for body, `1.2` for headings
- Font weights: 400 (regular), 500 (medium), 600 (semibold), 700 (bold)

## 4. Color Palette (Monochrome + Tasteful Accents)

- Background / Canvas: `#FFFFFF` (light), `#000000` (dark)
- Secondary Background: `#F5F5F7` (light), `#1C1C1E` (dark)
- Tertiary Background: `#E5E5EA` (light), `#2C2C2E` (dark)
- Separator / Border: `#D1D1D6` (light), `#38383A` (dark)
- Primary Text: `#1D1D1F` (light), `#F5F5F7` (dark)
- Secondary Text: `#86868B` (light), `#8E8E93` (dark)
- Accent Blue: `#007AFF` (primary action color)
- Accent Red: `#FF3B30` (destructive actions)
- Accent Green: `#34C759` (success/positive)
- Accent Orange: `#FF9500` (attention/warning)
- Accent Purple: `#AF52DE` (secondary accents)

## 5. Component Specifications

- Buttons:
  - Primary: `#007AFF` background, `#FFFFFF` text, corner radius `8px`, height `34px`, padding `0 16px`
  - Secondary: transparent background, `#007AFF` text, corner radius `8px`
  - Tertiary/Ghost: background `#F5F5F7`, text `#1D1D1F`, corner radius `8px`
  - Hover: opacity `0.9` transition `0.1s`
  - Active: scale `0.98` transform transition `0.1s`
  - Disabled: opacity `0.4`
- Cards / Containers:
  - Background: `#FFFFFF`, border `1px solid #D1D1D6`, corner radius `10px`
  - Padding: `16px` to `24px`
  - Depth: subtle `1px solid #D1D1D6` border, no shadow
- Input Fields:
  - Background: `#F5F5F7`, border `1px solid #D1D1D6`, corner radius `8px`
  - Padding: `8px 12px`, font size `14px`
  - Focus: border color `#007AFF`
- Status Indicators:
  - Active: green dot `#34C759`, `8px` diameter
  - Inactive: gray dot `#8E8E93`
  - Error: red dot `#FF3B30`
- Tags / Badges:
  - Background: `#F5F5F7`, text `#1D1D1F`, corner radius `6px`
  - Font size `12px`, font weight `500`, padding `2px 8px`

## 6. Micro-Interactions

- Hover states: subtle opacity shift `0.1s` ease
- Press states: scale `0.98` transform `0.1s` ease
- Focus rings: `2px solid #007AFF` with `2px` offset
- Transitions: all `0.1s` to `0.3s` ease, never longer
- Loading states: system activity indicator style, subtle pulse

## 7. Layout Principles

- Generous whitespace: `16px` to `24px` between major sections
- Content width: constrained to `max-width: 600px` for chat readability
- Sidebar: `260px` to `320px` width when present
- Header height: `44px` to `52px` (system-native proportions)
- Input bar height: `52px` to `60px`
- Grid: 8-point grid system for all spacing and sizing

## 8. Execution Protocol

When redesigning UI:

1. Establish monochrome color variables first
2. Apply system-native typography stack immediately
3. Use corner radius `8px` to `10px` consistently
4. Replace shadows with borders for depth
5. Add subtle micro-interactions (hover, press, focus)
6. Ensure all interactive elements meet 44x44px touch target minimum
7. Provide code that is lightweight, dependency-free, and performant
