import os
import subprocess
from fastapi import FastAPI, Request, HTTPException
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# Inicializa o app web com FastAPI
app = FastAPI()

# !! IMPORTANTE !! Substitua pelo ID da sua pasta de destino
OUTPUT_FOLDER_ID = '17bZbdSmshzqLuCcpTWuWwiwyzmbLLD3G' 

def get_drive_service():
    """
    Função Helper para criar um cliente autenticado para a API do Google Drive.
    """
    # Dentro da Cloud Function, as credenciais da conta de serviço associada
    # são encontradas automaticamente, não precisamos especificar o arquivo.
    credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/drive'])
    
    # Alternativa mais explícita se a de cima falhar (descomente as 5 linhas abaixo)
    # from google.oauth2 import service_account
    # credentials = service_account.Credentials.from_service_account_file(
    #     os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    #     scopes=['https://www.googleapis.com/auth/drive']
    # )
    
    service = build('drive', 'v3', credentials=credentials)
    return service

@app.post("/")
async def process_recording_endpoint(request: Request):
    """
    Endpoint principal acionado pelo n8n via HTTP.
    """
    try:
        request_json = await request.json()
        file_id = request_json.get('fileId')

        if not file_id:
            raise HTTPException(status_code=400, detail='O parâmetro "fileId" é obrigatório no corpo do JSON.')

        drive_service = get_drive_service()

        # 1. Obter metadados do arquivo para pegar o nome
        print(f"Buscando metadados para o fileId: {file_id}")
        file_metadata = drive_service.files().get(fileId=file_id, fields='name').execute()
        file_name = file_metadata.get('name')

        if not file_name:
            raise Exception(f"Não foi possível obter o nome do arquivo para o fileId: {file_id}. Verifique as permissões.")

        # Define os caminhos dos arquivos temporários
        video_file_path = f"/tmp/{file_name}"
        subtitle_file_path = f"/tmp/{file_name}.srt"
        
        # 2. Baixar o arquivo de vídeo do Drive
        print(f"Iniciando download de: {file_name}")
        drive_request = drive_service.files().get_media(fileId=file_id)
        with open(video_file_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, drive_request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                print(f"Download {int(status.progress() * 100)}%.")

        # 3. Executar FFmpeg para extrair a legenda
        print(f"Iniciando extração de legenda com FFmpeg...")
        command = ['ffmpeg', '-y', '-i', video_file_path, '-map', '0:s:0', subtitle_file_path]
        process = subprocess.run(command, capture_output=True, text=True)
        
        if process.returncode != 0:
            os.remove(video_file_path) # Limpa o arquivo de vídeo
            print(f"Erro do FFmpeg: {process.stderr}")
            raise Exception("FFmpeg não conseguiu extrair a legenda. Pode não haver uma trilha de legendas no arquivo.")

        # 4. Fazer o upload do arquivo de legenda (.srt) de volta para o Drive
        print(f"Iniciando upload da legenda: {file_name}.srt")
        media = MediaFileUpload(subtitle_file_path, mimetype='text/plain')
        drive_service.files().create(
            body={'name': f"{file_name}.srt", 'parents': [OUTPUT_FOLDER_ID]},
            media_body=media,
            fields='id'
        ).execute()

        # 5. Limpar arquivos temporários
        os.remove(video_file_path)
        os.remove(subtitle_file_path)

        return {"status": "sucesso", "message": f"Legenda para '{file_name}' processada."}

    except Exception as e:
        print(f"Erro detalhado no processamento: {str(e)}")
        # Para depuração, vamos retornar o erro real.
        raise HTTPException(status_code=500, detail=str(e))
