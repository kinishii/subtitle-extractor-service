import os
import subprocess
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

def get_drive_service():
    credentials, project_id = google.auth.default(scopes=['https://www.googleapis.com/auth/drive.readonly'])
    credentials.refresh(GoogleAuthRequest())
    return build('drive', 'v3', credentials=credentials)

def process_file(file_id: str):
    drive_service = get_drive_service()
    
    file_metadata = drive_service.files().get(fileId=file_id, fields='name').execute()
    file_name = file_metadata.get('name')
    if not file_name:
        raise Exception("Nome do arquivo não encontrado.")

    video_file_path = f"/tmp/{file_name.replace(' ', '_')}"
    subtitle_file_path = f"{video_file_path}.srt"

    drive_request = drive_service.files().get_media(fileId=file_id)
    with open(video_file_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, drive_request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

    command = ['ffmpeg', '-y', '-i', video_file_path, '-map', '0:s:0', subtitle_file_path]
    process = subprocess.run(command, capture_output=True, text=True)
    
    if process.returncode != 0:
        os.remove(video_file_path)
        raise Exception(f"FFmpeg falhou: {process.stderr}")

    with open(subtitle_file_path, 'r', encoding='utf-8') as f:
        subtitle_content = f.read()

    os.remove(video_file_path)
    os.remove(subtitle_file_path)
    
    return subtitle_content

@app.post("/")
async def endpoint(request: Request):
    try:
        data = await request.json()
        file_id = data.get('fileId')
        if not file_id:
            raise HTTPException(status_code=400, detail='"fileId" obrigatório.')
        
        # Usa um executor para rodar a função síncrona em um thread separado
        # para não bloquear o servidor web assíncrono.
        loop = asyncio.get_event_loop()
        subtitle_content = await loop.run_in_executor(None, process_file, file_id)
        
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=subtitle_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
