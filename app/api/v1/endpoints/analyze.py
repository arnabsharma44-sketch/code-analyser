import json

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from app.db.models.user import User
from app.dependencies.auth import get_current_user
from app.db.session import get_connection, init_db
from sqlalchemy import text
from app.schemas.analysis import AnalyzeTextRequest, AnalyserGraphResponse, SavedAnalysisCreate, SavedAnalysisResponse
from app.services.llm_chain import run_code_analysis
from app.services.file_parser import parse_source_file

router = APIRouter()
 
@router.post("/text", response_model=AnalyserGraphResponse)
async def analyze_text(
    payload: AnalyzeTextRequest,
    current_user: User = Depends(get_current_user),
) -> AnalyserGraphResponse:
    if not payload.code.strip():
        raise HTTPException(status_code=400, detail="Code payload cannot be empty.")
    
    return await run_code_analysis(
        code=payload.code,
        language=payload.language,
        filename=payload.filename
    )

@router.post("/save", response_model=SavedAnalysisResponse)
async def save_analysis(
    payload: SavedAnalysisCreate,
    current_user: User = Depends(get_current_user),
) -> SavedAnalysisResponse:
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guest users cannot save analyses")

    init_code = payload.code
    def _mapping_for_row(row):
        return row._mapping if hasattr(row, "_mapping") else row

    with get_connection() as connection:
        cursor = connection.execute(
            text(
                "INSERT INTO saved_analyses (user_id, code, filename, language, summary, nodes_json, edges_json, diagnostics_json, fixed_code)"
                " VALUES (:user_id, :code, :filename, :language, :summary, :nodes_json, :edges_json, :diagnostics_json, :fixed_code)"
            ),
            {
                "user_id": current_user.id,
                "code": init_code,
                "filename": payload.filename,
                "language": payload.language,
                "summary": payload.summary,
                "nodes_json": json.dumps([node.model_dump() for node in payload.nodes]),
                "edges_json": json.dumps([edge.model_dump() for edge in payload.edges]),
                "diagnostics_json": json.dumps([diagnostic.model_dump() for diagnostic in payload.diagnostics]),
                "fixed_code": payload.fixed_code,
            },
        )
        analysis_id = cursor.lastrowid
        connection.commit()

        row = connection.execute(
            text("SELECT id, user_id, code, filename, language, summary, nodes_json, edges_json, diagnostics_json, fixed_code, created_at, updated_at FROM saved_analyses WHERE id = :id"),
            {"id": analysis_id},
        ).fetchone()

    mapping = _mapping_for_row(row)
    return SavedAnalysisResponse(
        id=mapping["id"],
        user_id=mapping["user_id"],
        code=mapping["code"],
        filename=mapping["filename"],
        language=mapping["language"],
        summary=mapping["summary"],
        nodes=[node for node in json.loads(mapping["nodes_json"])],
        edges=[edge for edge in json.loads(mapping["edges_json"])],
        diagnostics=[diagnostic for diagnostic in json.loads(mapping["diagnostics_json"])],
        fixed_code=mapping["fixed_code"],
        created_at=mapping["created_at"],
        updated_at=mapping["updated_at"],
    )


@router.get("/history", response_model=list[SavedAnalysisResponse])
async def list_saved_analysis(
    current_user: User = Depends(get_current_user),
) -> list[SavedAnalysisResponse]:
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guest users do not have saved history")

    def _mapping_for_row(row):
        return row._mapping if hasattr(row, "_mapping") else row

    with get_connection() as connection:
        rows = connection.execute(
            text("SELECT id, user_id, code, filename, language, summary, nodes_json, edges_json, diagnostics_json, fixed_code, created_at, updated_at FROM saved_analyses WHERE user_id = :user_id ORDER BY created_at DESC"),
            {"user_id": current_user.id},
        ).fetchall()

    return [
        SavedAnalysisResponse(
            id=_mapping_for_row(row)["id"],
            user_id=_mapping_for_row(row)["user_id"],
            code=_mapping_for_row(row)["code"],
            filename=_mapping_for_row(row)["filename"],
            language=_mapping_for_row(row)["language"],
            summary=_mapping_for_row(row)["summary"],
            nodes=json.loads(_mapping_for_row(row)["nodes_json"]),
            edges=json.loads(_mapping_for_row(row)["edges_json"]),
            diagnostics=json.loads(_mapping_for_row(row)["diagnostics_json"]),
            fixed_code=_mapping_for_row(row)["fixed_code"],
            created_at=_mapping_for_row(row)["created_at"],
            updated_at=_mapping_for_row(row)["updated_at"],
        )
        for row in rows
    ]


@router.get("/history/{analysis_id}", response_model=SavedAnalysisResponse)
async def get_saved_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
) -> SavedAnalysisResponse:
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guest users do not have saved history")

    def _mapping_for_row(row):
        return row._mapping if hasattr(row, "_mapping") else row

    with get_connection() as connection:
        row = connection.execute(
            text("SELECT id, user_id, code, filename, language, summary, nodes_json, edges_json, diagnostics_json, fixed_code, created_at, updated_at FROM saved_analyses WHERE id = :id"),
            {"id": analysis_id},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    mapping = _mapping_for_row(row)
    if mapping["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this saved analysis")

    return SavedAnalysisResponse(
        id=mapping["id"],
        user_id=mapping["user_id"],
        code=mapping["code"],
        filename=mapping["filename"],
        language=mapping["language"],
        summary=mapping["summary"],
        nodes=json.loads(mapping["nodes_json"]),
        edges=json.loads(mapping["edges_json"]),
        diagnostics=json.loads(mapping["diagnostics_json"]),
        fixed_code=mapping["fixed_code"],
        created_at=mapping["created_at"],
        updated_at=mapping["updated_at"],
    )

@router.delete("/history/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
) -> Response:
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guest users do not have saved history")

    with get_connection() as connection:
        row = connection.execute(
            text("SELECT user_id FROM saved_analyses WHERE id = :id"),
            {"id": analysis_id},
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Analysis not found")

        mapping = row._mapping if hasattr(row, "_mapping") else row
        if mapping["user_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this saved analysis")

        connection.execute(
            text("DELETE FROM saved_analyses WHERE id = :id"),
            {"id": analysis_id},
        )
        connection.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/file", response_model=AnalyserGraphResponse)
async def analyze_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> AnalyserGraphResponse:
    code = await parse_source_file(file)
    
    await file.close()
    
    return await run_code_analysis(
        code=code,
        filename=file.filename
    )
