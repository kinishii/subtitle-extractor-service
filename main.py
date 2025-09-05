import os
import subprocess
from fastapi import FastAPI, Request, HTTPException
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from fastapi.responses import PlainTextResponse
import google.auth

app = FastAPI()

def get_drive_service():
    """Cria e retorna um cliente de serviço autenticado para a API do Google Drive."""
    print("Iniciando a criação do serviço do Drive com escopo de apenas leitura...")
    
    # Pedimos apenas a permissão de LEITURA, o que é mais seguro.
    scopes = ['https://www.googleapis.com/auth/drive.readonly']
    
    # O método 'google.auth.default' é o padrão para ambientes do Google Cloud (como Cloud Run)
    # e para testes locais onde a variável de ambiente está definida.
    credentials, project_id = google.auth.default(scopes=scopes)
    
    # Constrói o cliente de serviço
    service = build('drive', 'v3', credentials=credentials)
    print("Serviço do Drive criado com sucesso.")
    return service

@app.post("/")
async def process_and_return_subtitles(request: Request):
    """
    Endpoint principal: recebe um fileId, baixa o vídeo, extrai a legenda
    e retorna o conteúdo da legenda como texto puro.
    """
    file_id = None
    video_file_path = None
    subtitle_file_path = None
    
    try:
        # 1. Pega o fileId da requisição do n8n
        data = await request.json()
        file_id = data.get('fileId')
        print(f"Requisição recebida para o fileId: {file_id}")
        if not file_id:
            raise HTTPException(status_code=400, detail='O "fileId" é obrigatório no corpo do JSON.')
        
        drive_service = get_drive_service()

        # 2. Busca o nome do arquivo para usar localmente
        print("Buscando metadados do arquivo...")
        file_metadata = drive_service.files().get(fileId=file_id, fields='name').execute()
        file_name = file_metadata.get('name')

        if not file_name:
            raise Exception(f"CRÍTICO: Nome do arquivo retornou como 'None' para o fileId '{file_id}'. "
                            f"Isso geralmente indica um problema de PERMISSÃO. "
                            f"Verifique se a Conta de Serviço ({drive_service._credentials.service_account_email}) "
                            f"tem pelo menos permissão de 'Leitor' no arquivo/pasta do Drive.")

        print(f"Nome do arquivo obtido: {file_name}")

        # 3. Baixa o arquivo para o ambiente temporário do Cloud Run
        safe_file_name = "".join(c for c in file_name if c.isalnum() or c in ('.', '-', '_')).rstrip()
        os.makedirs("/tmp", exist_ok=True)
        video_file_path = f"/tmp/{safe_file_name}"
        subtitle_file_path = f"{video_file_path}.srt"
        
        print(f"Iniciando download para: {video_file_path}")
        drive_request = drive_service.files().get_media(fileId=file_id)
        with open(video_file_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, drive_request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

        # 4. Executa FFmpeg para extrair a legenda
        print("Download completo. Iniciando FFmpeg...")
        command = ['ffmpeg', '-y', '-i', video_file_path, '-map', '0:s:0', subtitle_file_path]
        process = subprocess.run(command, capture_output=True, text=True, check=False) # check=False para capturar o erro nós mesmos
        
        if process.returncode != 0:
            raise Exception(f"FFmpeg não conseguiu extrair a legenda. Erro: {process.stderr}")

        # 5. Lê o conteúdo do arquivo .srt que foi criado
        print("Extração da legenda concluída. Lendo o arquivo .srt...")
        with open(subtitle_file_path, 'r', encoding='utf-8') as f:
            subtitle_content = f.read()

        # 6. Retorna o conteúdo como resposta para o n8n
        print("Processo concluído. Retornando conteúdo da legenda para o n8n.")
        return PlainTextResponse(content=subtitle_content)

    except Exception as e:
        error_message = f"Erro detalhado no processamento: {str(e)}"
        print(error_message)
        raise HTTPException(status_code=500, detail=error_message)

    finally:
        # 7. Garante que os arquivos temporários sejam sempre limpos, mesmo se houver um erro
        print("Iniciando limpeza de arquivos temporários...")
        if video_file_path and os.path.exists(video_file_path):
            os.remove(video_file_path)
            print(f"Arquivo de vídeo temporário removido: {video_file_path}")
        if subtitle_file_path and os.path.exists(subtitle_file_path):
            os.remove(subtitle_file_path)
            print(f"Arquivo de legenda temporário removido: {subtitle_file_path}")
