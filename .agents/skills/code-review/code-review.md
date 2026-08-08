# Morakot Python Coding Style Guide

## Purpose
The purpose of this document is to establish and enforce standardized rules, conventions, and formatting for Python coding within Morakot's VB Framework. As the framework grows, maintaining clean, readable, and manageable source code is critical for maintenance, support, bug fixing, and ensuring accessibility for new and existing developers. These guidelines must be strictly followed by all developers and are subject to double-checking by QA, Team Lead, SDM, and HOD based on the level of review.

## Naming Convention and Format

### Folder Name, Field Name, Variable Name
- Start each word with a capital letter (Camel Case).
- Do not use underscores to separate words.
- Names should be clear, understandable, and reflect their purpose.
- Examples: `Customer`, `LoanContract`, `LoanApplication`, `User`, `Holiday`.

### Table Name
- Use uppercase letters.
- Separate words with underscores for readability.
- Prefix with `MKT_`.
- Examples: `MKT_CUSTOMER`, `MKT_USER`, `MKT_LOAN_CONTRACT`.

### Form Class
- Use uppercase letters.
- Separate words with underscores for readability.
- Prefix with `FRM_`.
- Examples: `FRM_CUSTOMER`, `FRM_USER`, `FRM_LOAN_CONTRACT`.

### Class Name (Utility Class)
- **Old Convention**: Use uppercase letters, separate words with underscores, and prefix with `CLS_`. Examples: `CLS_BATCH_UPLOAD`, `CLS_CUSTOM_REPORT`.
- **New Convention**: Use Camel Case, starting each word with a capital letter, without underscores. Examples: `Schedule`, `ReportBuilder`, `MenuBuilder`.

### Function
- No spaces between words.
- Start with a lowercase verb from the following: `is`, `validate`, `get`, `set`, `update`, `insert`, `post`, `remove`, `delete`, `del`, `format`, `convert`, `to`.
- Subsequent words use Camel Case.
- Other verbs require special approval from the Management Team.
- Examples: `getCustomerName()`, `loadExcel()`, `setBalance()`, `updateAccount()`, `insertRecord()`, `postAccounting()`, `deleteRecord()`, `delRecord()`, `removeListItem()`, `formatDate()`, `convertExcelToFile()`, `toMoney()`.

### Constant
- Use uppercase letters.
- Separate words with underscores.
- Follow the Length Rule (see below).
- Examples: `CONSTANT`, `MY_SCOTTISH`, `MY_LONG_CONSTANT`.

### Package
- Use short, lowercase words.
- Do not separate words with underscores.
- Follow the Length Rule.
- Examples: `package`, `mypackage`.

### Length Rule
- Applies to folder, file, variable, class, module, function, method, constant, and table names with 18 or more characters.
- Use a maximum of three words, preferably two.
- For two-word names exceeding 18 characters, shorten the first word to its first three characters.
- For three-word names exceeding 18 characters, shorten the middle word to its first three characters.
- For form class or table names, exclude `MKT_` or `FRM_` when measuring length.
- If still over 18 characters after shortening, further shorten the first or middle words.
- Examples: `AccountStatement` → `AccStatement`, `IncomeExpenseBooking` → `IncomeExpBooking`.

### Module File Name
- Use short, lowercase words.
- Do not separate words with underscores.
- Follow the Length Rule.
- Examples: `modules.py`, `forms.py`, `views.py`.

### Form URL
- Use Camel Case.
- Follow the Length Rule.
- Example: `registerCRUD(admin, '/Customer', 'Customer', FRM_CUSTOMER, [MKT_CUSTOMER])`.

### Template Jinja
- Use short, lowercase words.
- Do not separate words with underscores.
- Follow the Length Rule.
- Examples: `user.html`, `profile.html`, `print.html`.

### Template Folder
- Use lowercase letters.
- Separate words with underscores for readability.
- Follow the Length Rule.
- Examples: `template/customer`, `template/loan`, `template/report`.

### Import File from Tools
- Use short, lowercase words starting with `mkt`.
- Do not separate words with underscores.
- Import only the required module.
- Use a prefix alias starting with `mkt`.
- Never use `import *`.
- Place import statements at the top of the file in this order:
  1. Standard library imports.
  2. Related third-party imports.
  3. Local application/library-specific imports.
- Leave one blank line after import statements.
- Example: `import app.tools.user as mktuser`.

## Formatting

### Break Lines
- Use two blank lines between classes.
- Use one blank line between methods within a class.

### Block of Code
- A block of code is a group of code that describes step-by-step processes or achieves a specific purpose.
- Separate blocks with one blank line.
- Example:
```python
def setCalculateVariance(NumberList):
    # Block 1
    SumList = 0
    for Number in NumberList:
        SumList = SumList + Number
    Mean = SumList / len(NumberList)
    
    # Block 2
    SumSquares = 0
    for Number in NumberList:
        SumSquares = SumSquares + Number**2
    ResultSquares = SumSquares / len(NumberList)
    return ResultSquares - Mean**2
```

### Maximum Line of Code
- **File**: Maximum 2000 lines.
- **Class**: Maximum 20 methods (10 private, 10 public).
- **Code Per Line**: Maximum 79 characters, including in-line comments.
- **Block Comment**: Maximum 100 lines, with 5 lines per function or method.
- **Function/Method Body**: Maximum 70 lines, excluding `def` and `return` statements.
- **Doc String**: Maximum 200 lines, with 24 lines per method or function.

### Tab and Space
- Use spaces instead of tabs for indentation (Python 3 does not support tabs).
- Set the tab key to 4 spaces per tab.

## Comment and Block Comment

### In-Line Comment
- Add comments for logical code, functions, methods, classes, or anything requiring explanation.
- Limit comment length to 72 characters.
- Use complete sentences starting with a capital letter.
- Update comments when code changes.

### Block Comment
- Use when an in-line comment exceeds 72 characters.
- Example:
```python
def quadratic(a, b, c, x):
    # Calculate the solution to a quadratic equation using the quadratic
    # formula.
    # There are always two solutions to a quadratic equation, x_1
    # and x_2.
    x_1 = (-b + (b * 2 - 4 * a * c) * (1 / 2)) / (2 * a)
    x_2 = (-b - (b * 2 - 4 * a * c) * (1 / 2)) / (2 * a)
    return x_1, x_2
```

## Doc String
- Follow Google Documentation format.
- Enclose with triple double quotes (`"""..."""`).
- Structure:
  - Brief description at the top.
  - List of arguments with data type and purpose.
  - Description of return values.
  - One or two usage examples.
  - Exceptions raised.
- Do not include `self` parameter in the `Args` section.
- Example:
```python
"""This is an example of Google style.
Explanation goes here.

Args:
    param1 (type): This is the first param.
    param2 (type): This is a second param.

Attributes:
    attr1 (type): This is the first attribute for class.
    attr2 (type): This is the second attribute for class.

Returns:
    This is a description of what is returned.

Raises:
    KeyError: Raises an exception.

Examples:
    Examples should be written in doctest format, and should illustrate how
    to use the function.
    >>> print([i for i in example_generator(4)])
    [0, 1, 2, 3]
"""
```

## Auto-format and Convention Check Tool
- Rules and conventions are semi-automatically checked using an automated tool with a configuration file set by the QA team and approved by Management.
- Developers and Team Leads must download and use the same configuration file, updating it as needed.
- Recommended tool: **Flake8**.
  - Supports Python 2.7.
  - Allows add-ons and configuration.
  - Open source.
- Comparison with other tools:
  - **Black**: Supports Python 3, configurable, open source, no add-ons.
  - **PyCodeStyle**: Supports Python 2.7, configurable, open source, no add-ons.

## Complexity of Code and Tools
- Code complexity is measured by how code is written, read, organized, cleaned, and its ease of modification, support, and bug fixing.
- Recommended tool: **Radon**.
  - Measures code complexity similar to **Wily** but lacks git integration, graphs, and reports.
  - Compatible with Morakot’s Python version (unlike Wily, which is incompatible with Python 2).

## Grading
- Radon provides a complexity score and rank to evaluate source code and determine if it can be committed to git.
- Complexity Matrix:
  - **1-5 (Rank A)**: Low risk, simple block. Git commit allowed.
  - **6-10 (Rank B)**: Low risk, well-structured block. Git commit allowed.
  - **11-20 (Rank C)**: Moderate risk, slightly complex block. Git commit allowed, but consider updating to Rank B.
  - **21-30 (Rank D)**: More than moderate risk, complex block. Git commit not allowed; update encouraged.
  - **31-40 (Rank E)**: High risk, complex block. Git commit not allowed; update highly advised.
  - **41+ (Rank F)**: Very high risk, error-prone block. Git commit not allowed; update required.
- Special cases require review and approval from Management Team (MT).

## Access and Permission Level
- Permissions for creating, modifying, or deleting source code files in Morakot VB Framework are strictly defined:

### Standard Module
- **New/Modify**: Junior.
- **Delete**: Senior.
- **Reviewer 1**: Team Lead (TL).
- **Approver**: QA.

### Custom Module
- **New/Modify/Delete**: Senior.
- **Reviewer 1**: Team Lead (TL).
- **Approver**: QA.

### Core - Login (Utility: MenuBuilder, ReportBuilder, TemplateBuilder)
- **New/Modify/Delete**: Team Lead (TL).
- **Reviewer 1**: QA.
- **Reviewer 2**: SDM.
- **Approver**: HOD, CTO.

### Core Framework
- **New/Modify/Delete**: CTO, HOD.
- **Reviewer 1**: QA.
- **Approver**: CTO, HOD.

### Tools
- **New/Modify/Delete**: Senior.
- **Reviewer 1**: Team Lead (TL).
- **Reviewer 2**: QA.
- **Approver**: SDM, HOD.

### Third-Party
- **New (Install)**: Senior.
- **Modify (Update Version)**: Senior.
- **Delete (Remove)**: Team Lead (TL).
- **Reviewer 1**: Team Lead (TL).
- **Reviewer 2**: QA.
- **Approver**: SDM, HOD.

### Extra Rules
In addition to the above rules, there are some extra rules:
- Input Validation: Always validate and sanitize user inputs
- Parameterized Queries: Always use parameterized queries to prevent SQL injection attacks
- Escape the string before render them in browser, ex. escape(input_value)
- Secure Authentication: Implement strong password policies, and secure session management.
- Delete unused code, unused comment, print(), and console.log()
- Always to up to updated version library of python or js
- Delete unused code, unused comment, print(), and console.log()
- Use Framework built-in functions if available
- Check user input-value before store for custom page
- Always check authentication and permission to custom page using standard function of Morakot framework.
- Implement a friendly user-message for error handler, such as 500, 400, 406, ect.

### Don'ts: These are things you MUST NOT do
- Don’t use eval() function in code (eg., python, js)
- Don’t use |safe filter of jinja2 in template
- Don’t use include external link to resources (eg, link from cdn)
- Don’t trust user input: Never assume inputs are safe.
- Don’t concatenate strings in queries: Avoid building SQL queries with user data.
- Don’t store sensitive data in plain text: Encrypt passwords, API keys, etc.
- Don’t rely on client-side validation alone: Always validate and sanitize user inputs 
- Don’t ignore framework security tools: Use CSRF tokens, XSS filters provided by frameworks.
- Don’t display user input value in flash message.

### Output Format
When reporting the code review findings, you MUST produce a **well-structured, beautiful, and easy-to-read** output. Follow this format strictly:

---

#### 📋 Review Summary Table
Start with a high-level summary table:

```
| # | File | Line | Severity | Category | Issue Title |
|---|------|------|----------|----------|-------------|
| 1 | views.py | 42 | 🔴 Critical | XSS | Unsafe user input rendered without escaping |
| 2 | forms.py | 15 | 🟠 High | Naming | Function name does not start with a valid verb |
| 3 | user.html | 88 | 🟡 Medium | Security | |safe filter used on user-supplied data |
```

Severity icons:
- 🔴 **Critical** — Must fix immediately, high security risk
- 🟠 **High** — Must fix before release
- 🟡 **Medium** — Should fix, technical debt / convention violation
- 🔵 **Low** — Nice to fix, code quality improvement
- ⚪ **Info** — Informational note

---

#### 🔍 Detailed Issue Report
After the summary table, list every issue in detail using this structure:

---

**Issue #[N] — [Issue Title]**

| Field | Details |
|-------|---------|
| **File** | `filename.py` |
| **Line** | Line 42 |
| **Severity** | 🔴 Critical |
| **Category** | XSS Prevention |
| **Rule** | Escape all user-supplied values before rendering in browser |

**❌ Problematic Code (Reproduce the Issue)**
```python
# Line 42 — views.py
flash(f"Welcome {request.form['username']}")  # user input directly in flash
```

**⚠️ What Goes Wrong (Impact)**
> If a user enters `<script>alert('XSS')</script>` as their username, it will be rendered as raw HTML in the flash message, allowing a Cross-Site Scripting (XSS) attack that can steal session cookies or perform actions on behalf of other users.

**✅ Fixed Code (After Fix)**
```python
# Line 42 — views.py (fixed)
from markupsafe import escape
flash(f"Welcome {escape(request.form['username'])}")
```

**💡 Why This Fix Works**
> `markupsafe.escape()` converts special HTML characters (e.g., `<`, `>`, `&`) into safe HTML entities, preventing any injected script from being interpreted by the browser.

---

Repeat the above block for **every issue found**. Use horizontal rules (`---`) between each issue for clarity.

---

#### ✅ Passed Checks
After all issues, list what was checked and passed:

```
✅ Parameterized queries used correctly
✅ CSRF tokens present on all forms
✅ No eval() usage detected
✅ No external CDN links detected
```

---

#### 📊 Grading Summary
End with the complexity/grading summary:

```
| File | Complexity Score | Rank | Git Commit Allowed |
|------|-----------------|------|--------------------|
| views.py | 8 | B | ✅ Yes |
| forms.py | 14 | C | ✅ Yes (consider refactor) |
| user.html | 3 | A | ✅ Yes |
```

---

### After Completed
- After scanning, checking, and detected the issue, prompt user if they want to fix it or not.
- After completed fixed all issue, prompt user if they want to generate a REPORT of md file.
- After completed fixed all issue, prompt user if they need a VERIFIED REPORT as md file to prove it to their line manager or not.

### Most Important things you MUST Remember
- When refactoring the code to fix the issue, you MUST be very carefully check their dependency, their references, their usage at somewhere else,
- Also, you MUST always be guarantee that the changes you made will not break any other part of the code and/or break their existing functionality.
- You MUST always pay most attention when changing `import *` to specific import, avoid exception `ImportError` therefore you MUST ALWAYS check before refactoring.



## Appendix
- **PEP 8 -- Style Guide for Python Code**: [https://www.python.org/dev/peps/pep-0008](https://www.python.org/dev/peps/pep-0008)
- **How to Write Beautiful Python Code With PEP 8**: [https://realpython.com/python-pep8/](https://realpython.com/python-pep8/)
- **Documenting Python Code: A Complete Guide**: [https://realpython.com/documenting-python-code](https://realpython.com/documenting-python-code)
- **Refactoring Python Applications for Simplicity**: [https://realpython.com/python-refactoring](https://realpython.com/python-refactoring)
