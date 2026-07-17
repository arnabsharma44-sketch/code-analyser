from fastapi import UploadFile, HTTPException
from app.core.config import settings

async def parse_source_file(file: UploadFile) -> str:
    """
    Reads and decodes an UploadFile.
    Enforces maximum file size, rejects binary and unsupported extensions.
    """
    unsupported_extensions = {".exe", ".dll", ".so", ".zip", ".tar", ".gz", ".bin"}
    if file.filename:
        ext = file.filename[file.filename.rfind('.'):].lower() if '.' in file.filename else ""
        if ext in unsupported_extensions:
            raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")
            
    contents = await file.read()
    
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large.")
        
    if not contents:
        raise HTTPException(status_code=400, detail="File is empty.")
        
    try:
        decoded_text = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 text.")
    
    if not decoded_text.strip():
        raise HTTPException(status_code=400, detail="File content is blank.")
        
    return decoded_text
