import os
import subprocess
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# --- Configurações ---
# O ID da pasta no Drive para onde as legendas .srt serão salvas.
# Abra a pasta no seu browser e copie o ID da URL.
OUTPUT_FOLDER_ID = 'SEU_ID_DA_PASTA_MEET_SUBTITLES' 

def process_recording(request):
    """
    Função principal acionada por HTTP.
    Recebe um fileId do Google Drive, baixa o vídeo, extrai a legenda e faz o upload.
    """
    request_json = request.get_json(silent=True)

    if not request_json or 'fileId' not in request_json:
        return ('O parâmetro "fileId" é obrigatório no corpo do JSON.', 400)

    file_id = request_json['fileId']
    
    # O ambiente da Cloud Function usa as credenciais da conta de serviço associada.
    credentials = service_account.Credentials.from_service_account_file(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )
    scoped_credentials = credentials.with_scopes([
        'https://www.googleapis.com/auth/drive'
    ])
    drive_service = build('drive', 'v3', credentials=scoped_credentials)

    try:
        # 1. Baixar o arquivo de vídeo do Drive
        file_metadata = drive_service.files().get(fileId=file_id, fields='name').execute()
        file_name = file_metadata.get('name')
        
        # Define os caminhos dos arquivos no ambiente temporário da função
        video_file_path = f"/tmp/{file_name}"
        subtitle_file_path = f"/tmp/{file_name}.srt"

        request = drive_service.files().get_media(fileId=file_id)
        with open(video_file_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                print(f"Download {int(status.progress() * 100)}%.")

        # 2. Executar FFmpeg para extrair a legenda
        # O FFmpeg já está disponível no ambiente do Python no GCP!
        command = [
            'ffmpeg',
            '-i', video_file_path,
            '-map', '0:s:0',
            subtitle_file_path
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        
        # 3. Fazer o upload do arquivo de legenda (.srt) de volta para o Drive
        media = MediaFileUpload(subtitle_file_path, mimetype='text/srt')
        drive_service.files().create(
            body={'name': f"{file_name}.srt", 'parents': [OUTPUT_FOLDER_ID]},
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"Sucesso! Legenda extraída e salva para o arquivo: {file_name}")
        return ('Processo concluído com sucesso.', 200)

    except Exception as e:
        print(f"Erro ao processar o arquivo {file_id}: {e}")
        return ('Ocorreu um erro interno.', 500)
