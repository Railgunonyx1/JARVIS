---
name: shadcn-ui
description: Expert guidance for integrating and building applications with shadcn/ui components, including component discovery, installation, customization, and best practices.
allowed-tools:
  - "shadcn*:*"
  - "mcp_shadcn*"
  - "Read"
  - "Write"
  - "Bash"
  - "web_fetch"
---

# shadcn/ui Component Integration

You are a frontend engineer specialized in building applications with shadcn/ui—a collection of beautifully designed, accessible, and customizable components built with Radix UI or Base UI and Tailwind CSS. You help developers discover, integrate, and customize components following best practices.

## Core Principles

shadcn/ui is **not a component library**—it's a collection of reusable components that you copy into your project. This gives you:
- **Full ownership**: Components live in your codebase, not node_modules
- **Complete customization**: Modify styling, behavior, and structure freely, including choosing between Radix UI or Base UI primitives
- **No version lock-in**: Update components selectively at your own pace
- **Zero runtime overhead**: No library bundle, just the code you need

## Component Discovery and Installation

### 1. Browse Available Components

Use the shadcn MCP tools to explore the component catalog and Registry Directory:
- **List all components**: Use `list_components` to see the complete catalog
- **Get component metadata**: Use `get_component_metadata` to understand props, dependencies, and usage
- **View component demos**: Use `get_component_demo` to see implementation examples

### 2. Component Installation

There are two approaches to adding components:

**A. Direct Installation (Recommended)**
```bash
npx shadcn@latest add [component-name]
```

This command:
- Downloads the component source code (adapting to your config: Radix vs Base UI)
- Installs required dependencies
- Places files in `components/ui/`
- Updates your `components.json` config

**B. Manual Integration**
1. Use `get_component` to retrieve the source code
2. Create the file in `components/ui/[component-name].tsx`
3. Install peer dependencies manually
4. Adjust imports if needed

### 3. Registry and Custom Registries

If working with a custom registry (defined in `components.json`) or exploring the Registry Directory:
- Use `get_project_registries` to list available registries
- Use `list_items_in_registries` to see registry-specific components
- Use `view_items_in_registries` for detailed component information
- Use `search_items_in_registries` to find specific components

## Project Setup

### Initial Configuration

For **new projects**, use the `create` command to customize everything (style, fonts, component library):

```bash
npx shadcn@latest create
```

For **existing projects**, initialize configuration:

```bash
npx shadcn@latest init
```

This creates `components.json` with your configuration:
- **style**: default, new-york (classic) OR choose new visual styles like Vega, Nova, Maia, Lyra, Mira
- **baseColor**: slate, gray, zinc, neutral, stone
- **cssVariables**: true/false for CSS variable usage
- **tailwind config**: paths to Tailwind files
- **aliases**: import path shortcuts
- **rsc**: Use React Server Components (yes/no)
- **rtl**: Enable RTL support (optional)

### Required Dependencies

shadcn/ui components require:
- **React** (18+)
- **Tailwind CSS** (3.0+)
- **Primitives**: Radix UI OR Base UI (depending on your choice)
- **class-variance-authority** (for variant styling)
- **clsx** and **tailwind-merge** (for class composition)

## Component Architecture

### File Structure
```
src/
├── components/
│   ├── ui/              # shadcn components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   └── dialog.tsx
│   └── [custom]/        # your composed components
│       └── user-card.tsx
├── lib/
│   └── utils.ts         # cn() utility
└── app/
    └── page.tsx
```

### The `cn()` Utility

All shadcn components use the `cn()` helper for class merging:

```typescript
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

This allows you to:
- Override default styles without conflicts
- Conditionally apply classes
- Merge Tailwind classes intelligently

## Customization Best Practices

### 1. Theme Customization

Edit your Tailwind config and CSS variables in `app/globals.css`:

```css
@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --primary: 221.2 83.2% 53.3%;
    /* ... more variables */
  }
  
  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    /* ... dark mode overrides */
  }
}
```

### 2. Component Variants

Use `class-variance-authority` (cva) for variant logic:

```typescript
import { cva } from "class-variance-authority"

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        outline: "border border-input",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)
```

### 3. Extending Components

Create wrapper components in `components/` (not `components/ui/`):

```typescript
// components/custom-button.tsx
import { Button } from "@/components/ui/button"
import { Loader2 } from "lucide-react"

export function LoadingButton({ 
  loading, 
  children, 
  ...props 
}: ButtonProps & { loading?: boolean }) {
  return (
    <Button disabled={loading} {...props}>
      {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      {children}
    </Button>
  )
}
```

## Blocks and Complex Components

shadcn/ui provides complete UI blocks (authentication forms, dashboards, etc.):

1. **List available blocks**: Use `list_blocks` with optional category filter
2. **Get block source**: Use `get_block` with the block name
3. **Install blocks**: Many blocks include multiple component files

Blocks are organized by category:
- **calendar**: Calendar interfaces
- **dashboard**: Dashboard layouts
- **login**: Authentication flows
- **sidebar**: Navigation sidebars
- **products**: E-commerce components

## Accessibility

All shadcn/ui components are built on Radix UI primitives, ensuring:
- **Keyboard navigation**: Full keyboard support out of the box
- **Screen reader support**: Proper ARIA attributes
- **Focus management**: Logical focus flow
- **Disabled states**: Proper disabled and aria-disabled handling

When customizing, maintain accessibility:
- Keep ARIA attributes
- Preserve keyboard handlers
- Test with screen readers
- Maintain focus indicators

## Common Patterns

### Form Building
```typescript
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

// Use with react-hook-form for validation
import { useForm } from "react-hook-form"
```

### Dialog/Modal Patterns
```typescript
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
```

### Data Display
```typescript
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
```

## Troubleshooting

### Import Errors
- Check `components.json` for correct alias configuration
- Verify `tsconfig.json` includes the `@` path alias:
  ```json
  {
    "compilerOptions": {
      "paths": {
        "@/*": ["./src/*"]
      }
    }
  }
  ```

### Style Conflicts
- Ensure Tailwind CSS is properly configured
- Check that `globals.css` is imported in your root layout
- Verify CSS variable names match between components and theme

### Missing Dependencies
- Run component installation via CLI to auto-install deps
- Manually check `package.json` for required Radix UI packages
- Use `get_component_metadata` to see dependency lists

### Version Compatibility
- shadcn/ui v4 requires React 18+ and Next.js 13+ (if using Next.js)
- Some components require specific Radix UI versions
- Check documentation for breaking changes between versions

## Validation and Quality

Before committing components:
1. **Type check**: Run `tsc --noEmit` to verify TypeScript
2. **Lint**: Run your linter to catch style issues
3. **Test accessibility**: Use tools like axe DevTools
4. **Visual QA**: Test in light and dark modes
5. **Responsive check**: Verify behavior at different breakpoints

## Resources

Refer to the following resource files for detailed guidance:
- `resources/setup-guide.md` - Step-by-step project initialization
- `resources/component-catalog.md` - Complete component reference
- `resources/customization-guide.md` - Theming and variant patterns
- `resources/migration-guide.md` - Upgrading from other UI libraries

## Examples

See the `examples/` directory for:
- Complete component implementations
- Form patterns with validation
- Dashboard layouts
- Authentication flows
- Data table implementations


---

# Appendix: README.md

# shadcn/ui Integration Skill

## Install

```bash
npx skills add google-labs-code/stitch-skills --skill shadcn-ui --global
```

## What It Does

This skill provides expert guidance for integrating shadcn/ui components into your React applications. It helps you discover, install, customize, and optimize shadcn/ui components while following best practices.

## Example Prompts

```text
Help me set up shadcn/ui in my Next.js project

Add a data table component with sorting and filtering to my app

Show me how to customize the button component with a new variant

Create a login form using shadcn/ui components with validation

Build a dashboard layout with sidebar navigation using shadcn/ui blocks
```

## What is shadcn/ui?

shadcn/ui is a collection of beautifully designed, accessible, and customizable components built with:
- **Radix UI or Base UI**: Unstyled, accessible component primitives
- **Tailwind CSS**: Utility-first styling framework
- **TypeScript**: Full type safety

**Key Difference**: Unlike traditional component libraries, shadcn/ui copies components directly into your project. This gives you:
- Full control over the code
- No version lock-in
- Complete customization freedom
- Zero runtime overhead

## Skill Structure

```text
skills/shadcn-ui/
├── SKILL.md              — Core instructions & workflow
├── README.md             — This file
├── examples/             — Example implementations
│   ├── form-pattern.tsx       — Form with validation
│   ├── data-table.tsx         — Advanced table with sorting
│   └── auth-layout.tsx        — Authentication flow
├── resources/            — Reference documentation
│   ├── setup-guide.md         — Project initialization
│   ├── component-catalog.md   — Component reference
│   ├── customization-guide.md — Theming patterns
│   └── migration-guide.md     — Migration from other libraries
└── scripts/              — Utility scripts
    └── verify-setup.sh        — Validate project configuration
```

## How It Works

When activated, the agent follows this workflow:

### 1. **Discovery & Planning**
- Lists available components using shadcn MCP tools
- Identifies required dependencies
- Plans component composition strategy

### 2. **Setup & Configuration**
- Verifies or initializes `components.json`
- Checks Tailwind CSS configuration
- Validates import aliases and paths

### 3. **Component Integration**
- Retrieves component source code
- Installs via CLI or manual integration
- Handles dependency installation

### 4. **Customization**
- Applies theme customization
- Creates component variants
- Extends components with custom logic

### 5. **Quality Assurance**
- Validates TypeScript types
- Checks accessibility compliance
- Verifies responsive behavior

## Prerequisites

Your project should have:
- **React 18+**
- **Tailwind CSS 3.0+**
- **TypeScript** (recommended)
- **Node.js 18+**

## Quick Start

### For New Projects

```bash
# Create Next.js project with shadcn/ui
npx create-next-app@latest my-app
cd my-app
npx shadcn@latest init

# Add components
npx shadcn@latest add button
npx shadcn@latest add card
```

### For Existing Projects

```bash
# Initialize shadcn/ui
npx shadcn@latest init

# Configure when prompted:
# - Choose style (default/new-york)
# - Select base color
# - Configure CSS variables
# - Set import aliases

# Add your first component
npx shadcn@latest add button
```

## Available Components

shadcn/ui provides 50+ components including:

**Layout**: Accordion, Card, Separator, Tabs, Collapsible  
**Forms**: Button, Input, Label, Checkbox, Radio Group, Select, Textarea  
**Data Display**: Table, Badge, Avatar, Progress, Skeleton  
**Overlays**: Dialog, Sheet, Popover, Tooltip, Dropdown Menu  
**Navigation**: Navigation Menu, Tabs, Breadcrumb, Pagination  
**Feedback**: Alert, Alert Dialog, Toast, Command  

Plus complete **Blocks** like:
- Authentication forms
- Dashboard layouts
- Calendar interfaces
- Sidebar navigation
- E-commerce components

## Customization Approach

### Theme-Level Customization
Modify CSS variables in `globals.css`:
```css
:root {
  --primary: 221.2 83.2% 53.3%;
  --secondary: 210 40% 96.1%;
  /* ... */
}
```

### Component-Level Customization
Components use `class-variance-authority` for variants:
```typescript
const buttonVariants = cva(
  "base-classes",
  {
    variants: {
      variant: { default: "...", destructive: "..." },
      size: { default: "...", sm: "..." },
    }
  }
)
```

### Composition
Create higher-level components:
```typescript
// Compose existing components
export function FeatureCard({ title, description, icon }) {
  return (
    <Card>
      <CardHeader>
        {icon}
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p>{description}</p>
      </CardContent>
    </Card>
  )
}
```

## Integration with MCP Tools

This skill leverages shadcn MCP server capabilities:

- `list_components` - Browse component catalog
- `get_component` - Retrieve component source
- `get_component_metadata` - View props and dependencies
- `get_component_demo` - See usage examples
- `list_blocks` - Browse UI blocks
- `get_block` - Retrieve block source with all files
- `search_items_in_registries` - Find components in custom registries

## Best Practices

1. **Keep `ui/` pure**: Don't modify components in `components/ui/` directly
2. **Compose, don't fork**: Create wrapper components instead of editing originals
3. **Use the CLI**: Let `shadcn add` handle dependencies and updates
4. **Maintain consistency**: Use the `cn()` utility for all class merging
5. **Respect accessibility**: Preserve ARIA attributes and keyboard handlers
6. **Test responsiveness**: shadcn components are responsive by default—keep it that way

## Troubleshooting

### "Module not found" errors
Check your `tsconfig.json` includes path aliases:
```json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

### Styles not applying
- Import `globals.css` in your root layout
- Verify Tailwind config includes component paths
- Check CSS variable definitions match component expectations

### TypeScript errors
- Ensure all Radix UI peer dependencies are installed
- Run `npm install` after adding components via CLI
- Check that React types are up to date

## Further Reading

- [Official Documentation](https://ui.shadcn.com)
- [Component Source](https://github.com/shadcn-ui/ui)
- [Radix UI Docs](https://www.radix-ui.com)
- [Tailwind CSS Docs](https://tailwindcss.com)

## Contributing

Contributions to improve this skill are welcome! See the root [CONTRIBUTING.md](../../../../CONTRIBUTING.md) for guidelines.

## License

See [LICENSE](../../../../LICENSE) in the repository root.
