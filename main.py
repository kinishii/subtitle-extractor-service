import os
import subprocess
from fastapi import FastAPI, Request, HTTPException
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import asyncio

# --- Aplicação Web ---
# Usamos FastAPI por ser leve e moderno para criar APIs.
app = FastAPI()

# --- Configurações ---
# !! IMPORTANTE !! Substitua pelo ID da sua pasta no Google Drive.
# Abra a pasta 'Meet Subtitles' no browser e copie o ID da URL.
OUTPUT_FOLDER_ID = 'SEU_ID_DA_PASTA_MEET_SUBTITLES' 

# --- Função de Acesso ao Google Drive ---
def get_drive_service():
    """Cria e retorna um cliente de serviço autenticado para o Google Drive."""
    # Cloud Run usa as credenciais da conta de serviço associada automaticamente.
    # O escopo define que queremos permissão total de acesso ao Drive.
    credentials = service_account.Credentials.from_service_account_file(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )
    scoped_credentials = credentials.with_scopes([
        'https://www.googleapis.com/auth/drive'
    ])
    return build('drive', 'v3', credentials=scoped_credentials)

# --- Endpoint da API ---
# @app.post("/") define que esta função responderá a requisições HTTP POST na rota raiz.
@app.post("/")
async def process_recording_endpoint(request: Request):
    """
    Endpoint principal acionado pelo n8n via HTTP.
    Extrai o fileId do corpo da requisição e inicia o processo.
    """
    try:
        request_json = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corpo da requisição inválido. JSON esperado.")

    file_id = request_json.get('fileId')
    if not file_id:
        raise HTTPException(status_code=400, detail='O parâmetro "fileId" é obrigatório no corpo do JSON.')
    
    # Chama a função de processamento pesado em background para não bloquear a resposta.
    # Isto não é essencial para começar, mas é uma boa prática.
    # Por simplicidade, vamos chamar diretamente e aguardar.
    try:
        result = await process_file(file_id)
        return {"status": "sucesso", "message": result}
    except Exception as e:
        print(f"Erro detalhado no processamento: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar o arquivo: {str(e)}")


async def process_file(file_id: str):
    """
    Lógica principal: baixa o vídeo, executa FFmpeg, e faz o upload da legenda.
    """
    loop = asyncio.get_event_loop()
    drive_service = await loop.run_in_executor(None, get_drive_service)

    # 1. Obter metadados e definir caminhos
    file_metadata = await loop.run_in_executor(None, lambda: drive_service.files().get(fileId=file_id, fields='name').execute())
    file_name = file_metadata.get('name', 'recording.mp4')
    
    video_file_path = f"/tmp/{file_id}_{file_name}"
    subtitle_file_path = f"/tmp/{file_id}_{file_name}.srt"
    
    # 2. Baixar o arquivo de vídeo do Drive
    print(f"Iniciando download de: {file_name}")
    request_download = drive_service.files().get_media(fileId=file_id)
    with open(video_file_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request_download)
        done = False
        while not done:
            status, done = await loop.run_in_executor(None, downloader.next_chunk)
            if status:
                print(f"Download {int(status.progress() * 100)}%.")
    
    # 3. Executar FFmpeg para extrair a legenda
    print(f"Iniciando extração de legenda com FFmpeg...")
    command = ['ffmpeg', '-y', '-i', video_file_path, '-map', '0:s:0', subtitle_file_path]
    process = await asyncio.create_subprocess_exec(*command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        # Se FFmpeg falhar, pode ser que não haja legenda.
        print(f"FFmpeg falhou com código {process.returncode}: {stderr.decode()}")
        # Limpa os arquivos temporários
        os.remove(video_file_path)
        raise Exception("FFmpeg não conseguiu extrair a legenda. O arquivo pode não conter uma trilha de legendas.")

    # 4. Fazer o upload do arquivo de legenda (.srt) de volta para o Drive
    print(f"Iniciando upload da legenda: {file_name}.srt")
    srt_file_name = f"{file_name}.srt"
    media = MediaFileUpload(subtitle_file_path, mimetype='text/plain', resumable=True)
    file_metadata_upload = {'name': srt_file_name, 'parents': [OUTPUT_FOLDER_ID]}
    
    await loop.run_in_executor(None, lambda: drive_service.files().create(body=file_metadata_upload, media_body=media, fields='id').execute())
    
    # 5. Limpar arquivos temporários
    os.remove(video_file_path)
    os.remove(subtitle_file_path)
    
    return f"Legenda para '{file_name}' processada e salva com sucesso."
