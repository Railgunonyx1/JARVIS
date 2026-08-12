# Optimizer Agent Skill

**Name:** optimizer-agent  
**Description:** Iterative prompt optimization using LangSmith evals and error analysis. Walks you through setting up datasets, running baselines, analyzing error patterns, and improving prompts until convergence.

---

## Overview

The optimizer-agent helps you get the best possible performance from LLM prompts by implementing an iterative optimization loop:

1. **Setup dataset** - Create train/validation split in LangSmith
2. **Run baseline** - Eval current prompt, save results
3. **Analyze errors** - Use error_analyzer subagent to find patterns
4. **Update prompt** - Translate patterns into prompt improvements
5. **Rerun & compare** - Check train vs val accuracy for overfitting
6. **Converge** - Repeat until performance plateaus

This skill is reusable across projects and follows the [optimizer-agent](https://github.com/hwchase17/optimizer-agent) methodology.

---

## Best Practices

### Dataset Setup
- **Always** use stratified sampling for train/validation split
- Typical split: 70-80% train, 20-30% validation
- Create two LangSmith datasets: `name-train` and `name-val`
- Validation set: ONLY use for overall accuracy, NEVER inspect individual errors

### Eval Execution
- **Always** run baseline eval first before making changes
- Use `max_concurrency=5` as default for `langsmith.evaluate()`
- When script changes: test on 5 examples FIRST, then run full dataset
- When only changing prompt: skip 5-example test, run full dataset directly
- Use higher concurrency (20+) if evals timeout or take too long
- Results CSV must include: `input`, `expected_output`, `predicted_output`, `is_correct`
- Rich context columns (optional but recommended): `ground_truth_reasoning`, `model_reasoning`

### Overfitting Prevention
- Monitor both train AND validation accuracy
- If train ↑ but val ↓ → you're overfitting, revert changes
- Best validation accuracy may come from a simpler prompt
- Track best val version for rollback

### Error Analysis
- Focus on **high-level patterns**, not individual failures
- Two prompts with same accuracy can have very different error profiles
- Check: how many cases improved vs regressed between versions?
- A net-zero accuracy change might mask 14 fixed + 14 broken = churn
- Use pandas to merge result CSVs on example_id to find differences

### Label Quality
- Some "errors" may be labeling inconsistencies, not prompt issues
- If cases contradict stated classification rules, may be mislabeled
- Accuracy ceiling may be limited by label quality, not prompt quality
- Don't chase 100% if labels themselves are inconsistent

### Prompt Versioning
- Keep final prompt in `prompt.txt`
- Save earlier versions in `prompt_versions/` for rollback and audit
- Update `prompt.txt` after each iteration, save previous to `prompt_versions/`
- Maintain `experiment_log.md` tracking each iteration

---

## Process (Imperative Steps)

### Step 1: Initialize
```bash
# Create project directory
mkdir -p .agents/skills/optimizer-agent

# Ensure prompt.txt exists with your starting prompt
# Ensure run_evals.py exists and is configured
# Ensure LangSmith credentials are available
```

### Step 2: Create Dataset
```python
from langsmith import Client

client = Client()
dataset_name = "my-project-train"
description = "Prompt optimization dataset - training split"

dataset = client.create_dataset(
    dataset_name,
    description=description,
    tags=["prompt-optimization"]
)
```

Create separate validation dataset: `my-project-val`

### Step 3: Run Baseline
```bash
python run_evals.py
```
- This should load `prompt.txt` and evaluate on the dataset
- Results saved to `results/uuid.csv`
- Verify results CSV has required columns

### Step 4: Analyze Errors
```bash
# Call the error_analyzer subagent
# Provide: path to train results CSV, path to prompt.txt
# It will write analysis to analysis/ directory and return the file path
```

Read the analysis file to identify patterns:
- Is the model too aggressive or too conservative?
- What categories of errors are occurring?
- Are there over-specific criteria causing failures?
- Is the model missing important concepts?

### Step 5: Update Prompt
Based on the analysis, update `prompt.txt`:
- Add targeted exceptions rather than rewriting entire rules
- Avoid over-specifying criteria (can break more cases than it fixes)
- Err toward safer classification in safety-critical contexts
- Consider combining best parts of different iterations

### Step 6: Track and Iterate
```markdown
# experiment_log.md entry example

### Iteration 1
- Prompt: prompt_v1.txt → prompt.txt
- Results: results/baseline.csv
- Train Accuracy: 72% | Val Accuracy: 70%
- Changes: Added clarity to concept X, softened aggressive rule Y
- Outcome: Net positive, no overfitting

### Iteration 2
- Prompt: prompt.txt (current) → prompt_v2.txt
- Results: results/iter2.csv
- Train Accuracy: 80% | Val Accuracy: 78%
- Changes: Refined rule Z exception, removed over-specific criterion
- Outcome: Converged, validation stable
```

Repeat Steps 3-6 until:
- Performance converges (train and val both stable)
- You're stuck and no improvements apparent
- Validation accuracy starts declining (overfitting)

---

## Common Pitfalls

### Overfitting to Training Set
- Train accuracy improves but validation drops
- Solution: Revert to version with better val accuracy, or simplify prompt

### Over-Specifying Criteria
- Adding too many specific rules/keywords
- Solution: Remove rules that fix fewer cases than they break

### Chasing 100% Accuracy
- May be limited by label quality, not prompt quality
- Solution: Accept reasonable accuracy, check label consistency

### Ignoring Validation Set
- Only looking at train errors, overfitting creeps in
- Solution: Always track and report both train AND val accuracy

### Label Noise
- Dataset has inconsistent labels
- Solution: Review questionable labels, may need dataset cleanup

---

## LangSmith Dataset Workflow (Reusable Skill)

### Creating Datasets Programmatically
```python
from langsmith import Client
import os

client = Client(api_key=os.getenv("LANGSMITH_API_KEY"))

# Create training dataset
train_dataset = client.create_dataset(
    name="my-project-train",
    description="Training split for prompt optimization",
    tags=["prompt-optimization", "train"]
)

# Create validation dataset  
val_dataset = client.create_dataset(
    name="my-project-val", 
    description="Validation split for prompt optimization",
    tags=["prompt-optimization", "val"]
)
```

### Uploading Examples
```python
from langsmith import Client
import os
import json

client = Client(api_key=os.getenv("LANGSMITH_API_KEY"))
dataset_id = "your-dataset-id-here"

# Examples are dicts with 'inputs' and 'outputs' keys
examples = [
    {
        "inputs": {"question": "What is the capital of France?"},
        "outputs": {"answer": "Paris"}
    },
    # ... more examples
]

# Bulk upload in batches to avoid timeouts
client.create_examples(dataset_id=dataset_id, examples=examples)
```

### Required Environment
- `LANGSMITH_API_KEY` preferred for LangSmith operations
- `LANGCHAIN_API_KEY` may work as fallback
- Ensure write permissions for `results/` and `analysis/` directories

---

## Skill Authoring Conventions

### Frontmatter (Minimum Required)
```yaml
name: optimizer-agent
description: Iterative prompt optimization using LangSmith evals and error analysis
```

### Body Template
- **Overview**: High-level description of the skill's purpose
- **Best Practices**: Key guidelines and rules to follow
- **Process**: Imperative steps the agent should follow
- **Common Pitfalls**: Known issues and how to avoid them
- **LangSmith Dataset Workflow**: Reusable API patterns (if applicable)
- **Integration Notes**: How this fits into broader system (JARVIS in this case)

### Placement
- Skills live under `.agents/skills/<skill-name>/`
- Must include `SKILL.md` and optionally helper scripts
- Use absolute paths in examples and documentation

---

## JARVIS Integration Notes

### As an Agent Profile
The optimizer-agent can be registered as a JARVIS agent profile for on-demand prompt optimization:

```python
from agents.agent_ecosystem import get_agent_registry, AgentProfile, ExecutionMode

registry = get_agent_registry()
optimizer_profile = AgentProfile(
    name="optimizer_agent",
    role="Prompt Optimizer",
    description="Iteratively optimizes LLM prompts using LangSmith evals and error analysis",
    capabilities=[
        "prompt_optimization", "eval_management", "error_analysis", "experiment_tracking"
    ],
    required_permissions=["langsmith.*", "memory.*", "web.search"],
    supported_modes=[ExecutionMode.SMART, ExecutionMode.AGENT],
    max_concurrent_tasks=1,
    priority=AgentPriority.NORMAL,
)
registry.register(BaseAgent(optimizer_profile))
```

### As a Reusable Skill
- Import and use the AGENTS.md guidelines for prompt optimization workflows
- The `error_analyzer` subagent pattern can be adapted for other analysis tasks
- LangSmith dataset creation/management scripts can be reused across projects

### Commands (when deepagents CLI integration is set up)
- `deepagents-cli --agent opt-agent` - Launch the optimizer agent CLI
- Integration with JARVIS's existing agent routing system for on-demand optimization

---