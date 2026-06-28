# EBLAN Browser Extensions (.eblp)

## Format Specification

`.eblp` files are plain-text extension files with three sections separated by `---`:

```
JS CODE
---
Meta
key: value
key: value
---
CSS CODE
```

## Sections

### 1. JavaScript (JS)
- **Position**: First section
- **Purpose**: Execute JavaScript code on every page load
- **Access**: Full DOM and window object access
- **Example**:
  ```javascript
  console.log('Extension loaded!');
  document.body.style.background = '#1a1a2e';
  ```

### 2. Metadata (Meta)
- **Position**: Second section (after first `---`)
- **Format**: `key: value` pairs (one per line)
- **Required fields**:
  - `name`: Extension name
  - `version`: Version (semver recommended: 1.0.0)
  - `author`: Author name
- **Optional fields**:
  - `description`: What your extension does
  - `url`: Extension website/repo
  - `license`: License type

**Example**:
```
Meta
name: Dark Mode
version: 1.2.0
author: Your Name
description: Enables dark mode on all websites
```

### 3. CSS (Optional)
- **Position**: Third section (after second `---`)
- **Purpose**: Inject custom styles
- **Scope**: Global - applies to entire page
- **Example**:
```css
body {
    background: #0f0f0f !important;
    color: #ffffff !important;
}
```

## Installation

1. **Create file**: Save your extension as `myextension.eblp`
2. **Navigate to folder**:
   - **Windows**: `%APPDATA%\EBLAN\extensions\`
   - **Linux/Mac**: `~/etc/eblan/extensions/`
3. **Reload**: Go to `Extensions → Перезагрузить` or restart browser
4. **Done**: Extension loads automatically on every page

## Complete Example

```
// Dark mode extension
document.documentElement.style.colorScheme = 'dark';
const style = document.createElement('style');
style.textContent = 'html { filter: invert(1) hue-rotate(180deg); }';
document.head.appendChild(style);

---

Meta
name: Quick Dark Mode
version: 1.0.0
author: EBLAN Community
description: Inverts page colors for dark theme

---

CSS
/* Additional tweaks */
img { filter: invert(1) hue-rotate(180deg); }
video { filter: invert(1) hue-rotate(180deg); }
```

## Best Practices

1. **Avoid conflicts**: Use unique class/ID names or namespace your code
2. **Performance**: Minimize DOM queries and use event delegation
3. **Errors**: Wrap code in try-catch to prevent page breaking
4. **Testing**: Manually test on various websites
5. **Comments**: Document your extension code
6. **Security**: Don't inject sensitive data or credentials

## Advanced: Global Extension Object

EBLAN Browser automatically creates `window.eblanExtension` object:

```javascript
// Check if in EBLAN Browser
if (window.eblanExtension) {
    console.log('Running in EBLAN Browser!');
}
```

## Troubleshooting

- **Extension not loading**: Check file ends with `.eblp` and is in correct folder
- **JS errors**: Check console (F12) for syntax errors
- **CSS not applying**: Use `!important` flag on rules
- **Meta not parsed**: Ensure `---` separators are on own lines with no trailing spaces

## Example Extensions Ideas

- 🌙 Dark mode for all sites
- 🚀 Keyboard shortcuts
- 🔒 Privacy enhancements  
- 🎨 Custom color themes
- 📊 Page analytics
- ⚡ Performance tweaks
- 🔊 Volume normalizer
- 🎯 Auto-clicker/macro
