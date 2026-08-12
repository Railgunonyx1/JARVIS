# Optimizer Agent Skill

A prompt optimization agent that iteratively improves prompts using LangSmith evals and error analysis.

## When to Use
- You want to optimize a prompt for better performance on a specific task
- You have a dataset (train/validation split) and want to iterate on prompt improvements
- You need to track experiments and analyze error patterns

## Core Workflow
1. **Setup**: Create a LangSmith dataset with train/validation split (70-80% train, 20-30% val)
2. **Baseline**: Run initial evals with current prompt, save results CSV
3. **Analyze**: Use the `error_analyzer` subagent to identify error patterns from training results
4. **Update**: Modify prompt.txt based on identified patterns (avoid overfitting to training set)
5. **Iterate**: Rerun evals, compare train vs validation accuracy, watch for overfitting
6. **Converge**: Repeat until performance plateaus or validation accuracy drops

## Required Files
- `prompt.txt` - The current prompt being optimized (final prompt should always be here)
- `prompt_versions/` - Directory to save previous prompt versions for rollback
- `experiment_log.md` - Track each iteration: prompt version, results file, accuracy, changes
- `results/` - Directory for eval result CSVs
- `analysis/` - Directory for error analysis output from subagent

## Key Rules
- **NEVER** truncate input data when saving CSV results - always save FULL input
- **ALWAYS** split dataset into TRAIN and VALIDATION sets using stratified sampling
- **NEVER** look at individual errors in validation set - only use for overall accuracy tracking
- **ALWAYS** run baseline eval first before making any changes
- Watch for overfitting: if train accuracy improves but validation drops, revert changes
- Report both train and validation accuracy in experiment_log.md
- Results CSV must include: `input`, `expected_output`, `predicted_output`, `is_correct`
- Optional rich context columns: `ground_truth_reasoning`, `model_reasoning`

## Subagents
- `error_analyzer`: Analyzes train set result CSVs and writes pattern analysis to `analysis/` directory
  - Does NOT suggest specific prompt wording - you translate patterns into prompt changes
  - Focus on high-level patterns, not individual examples
  - May identify: exceptions to rules, over-specific criteria, train vs val divergence, label noise

## Experiment Tracking
- Maintain `experiment_log.md` with entries like:
  ```
  ### Iteration 1
  - Prompt: prompt_v1.txt → prompt.txt
  - Results: results/iteration_1.csv
  - Train Accuracy: 78% | Val Accuracy: 75%
  - Changes: Added specificity to rule X, clarified Y concept
  - Outcome: Net positive, no overfitting detected

  ### Iteration 2
  - Prompt: prompt.txt (current) → prompt_v2.txt
  - Results: results/iteration_2.csv
  - Train Accuracy: 85% | Val Accuracy: 82%
  - Changes: Refined rule Z exception, removed over-specific criterion
  - Outcome: Converged, validation stable
  ```

## Integration with JARVIS
- Use LangSmith credentials (LANGSMITH_API_KEY preferred, LANGCHAIN_API_KEY as fallback)
- Dataset paths and experiment names are project-configurable
- Results can be stored in `~/.jarvis/optimizer/` or project-local `results/` directory
- Compatible with JARVIS's agent ecosystem - can be invoked as a specialized agent