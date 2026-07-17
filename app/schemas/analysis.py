from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class AnalyzeTextRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200_000, description="The source code to analyze")
    language: Optional[str] = Field(default=None, description="The programming language of the code")
    filename: Optional[str] = Field(default=None, description="The original filename of the code")

class AnalyserNode(BaseModel):
    id: str = Field(..., description="Unique identifier for the node, e.g., 'err_line_5'")
    label: str = Field(..., description="Contains the issue context and line number")
    node_type: Literal["root_cause", "intermediate_effect", "final_crash"] = Field(..., description="Classification of the error node")

class AnalyserEdge(BaseModel):
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    relationship: str = Field(..., description="Text description explaining how the source error causes or leads to the target error/crash")

class CodeDiagnostic(BaseModel):
    source: str = Field(..., description="Compiler, parser, or linter that produced the diagnostic")
    severity: Literal["error", "warning", "info"] = Field(..., description="Diagnostic severity")
    message: str = Field(..., description="Human-readable diagnostic message")
    line: Optional[int] = Field(default=None, description="One-based source line number")
    column: Optional[int] = Field(default=None, description="One-based source column number")
    end_line: Optional[int] = Field(default=None, description="One-based ending source line number")
    end_column: Optional[int] = Field(default=None, description="One-based ending source column number")

class AnalyserGraphResponse(BaseModel):
    summary: str = Field(..., description="Clear, actionable paragraph describing the issue")
    nodes: List[AnalyserNode] = Field(..., description="List of nodes in the dependency graph")
    edges: List[AnalyserEdge] = Field(..., description="List of edges representing cascading errors")
    diagnostics: List[CodeDiagnostic] = Field(default_factory=list, description="Trusted local compiler or linter diagnostics collected before the LLM call")
    fixed_code: Optional[str] = Field(default=None, description="The fully corrected replacement code")
    unified_diff: Optional[str] = Field(default=None, description="Unified diff showing exactly what changed")


class SavedAnalysisCreate(BaseModel):
    code: str = Field(..., description="The source code used for analysis")
    language: Optional[str] = Field(default=None, description="The programming language of the submitted code")
    filename: Optional[str] = Field(default=None, description="The original filename for the analysis")
    summary: str = Field(..., description="Summary of the analysis results")
    nodes: List[AnalyserNode] = Field(..., description="Saved dependency graph nodes")
    edges: List[AnalyserEdge] = Field(..., description="Saved dependency graph edges")
    diagnostics: List[CodeDiagnostic] = Field(default_factory=list, description="Diagnostics captured during analysis")
    fixed_code: Optional[str] = Field(default=None, description="The corrected code version")


class SavedAnalysisResponse(SavedAnalysisCreate):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
