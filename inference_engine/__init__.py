"""Inference Engine — model routing, complexity analysis, speculative execution, optimization."""

from inference_engine.async_deps import get_dependency_resolver
from inference_engine.complexity_analyzer import ComplexityAnalyzer, get_complexity_analyzer
from inference_engine.micro_profiler import get_micro_profiler
from inference_engine.model_router import ModelRouter, get_model_router
from inference_engine.runtime_dashboard import get_runtime_dashboard
from inference_engine.speculative_executor import SpeculativeExecutor, get_speculative_executor
from inference_engine.worker_scaling import get_worker_scaler
