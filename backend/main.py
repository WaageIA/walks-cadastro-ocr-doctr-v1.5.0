from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import base64 # Para codificar/decodificar imagens
import redis
from rq import Queue
from dotenv import load_dotenv
from typing import List

# Importa a função de tarefa do nosso módulo de tarefas
from .tasks import process_single_document_task

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# --- Configuração do Redis para RQ ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = redis.from_url(REDIS_URL)
rq_queue = Queue(connection=redis_conn)

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Walks Bank OCR API",
    description="API para processamento de documentos com doctr e LLM",
    version="1.0.0"
)

# --- CORS Middleware ---
# Lê a URL do frontend a partir das variáveis de ambiente
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

origins = [
    "http://localhost:3000",
    "http://localhost:3001",
]

# Adiciona a URL de produção à lista de origens se estiver definida
if FRONTEND_URL not in origins:
    origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Health Check Endpoint ---
@app.get("/health", tags=["Health"])
async def health_check():
    status = "ok"
    redis_status = "connected"
    try:
        redis_conn.ping()
    except Exception:
        redis_status = "disconnected"
        status = "degraded"

    # A chave da API da LLM é verificada no worker, mas podemos verificar a variável de ambiente aqui
    llm_api_key_status = "configured" if os.getenv("OPENAI_API_KEY") else "not_configured"
    if not os.getenv("OPENAI_API_KEY"):
        status = "degraded"

    return JSONResponse(content={
        "status": status,
        "redis": redis_status,
        "llm_api_key": llm_api_key_status
    })

# --- OCR Processing Endpoint (para múltiplos arquivos) ---
@app.post("/api/v1/ocr/process-documents", tags=["OCR"])
async def process_documents(files: List[UploadFile] = File(...)):
    """
    Recebe múltiplos documentos (imagens ou PDFs), enfileira-os para processamento assíncrono.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    job_ids = []
    # Usar um dicionário para rastrear arquivos por um identificador único se necessário
    # Por simplicidade, vamos assumir que o `file.name` pode ser usado para mapeamento,
    # mas o ideal seria o frontend enviar uma chave para cada arquivo.
    # Vamos adaptar para que o frontend envie `key:file` no form-data.

    # O frontend precisa enviar os arquivos com chaves, ex: `rg: file_bytes`, `cnpj: file_bytes`
    # Como o `files: List[UploadFile]` não preserva as chaves originais do form-data,
    # vamos ter que confiar no `file.filename` ou ajustar o lado do cliente.
    # Para uma solução robusta, o cliente deve enviar metadados.
    # Por agora, vamos assumir que o `file.name` contém a chave que precisamos.

    for file in files:
        # Valida se o tipo de arquivo é suportado (imagem ou PDF)
        if not (file.content_type.startswith("image/") or file.content_type == "application/pdf"):
            raise HTTPException(status_code=400, detail=f"Tipo de arquivo '{file.content_type}' para '{file.filename}' n
o suportado. Apenas imagens e PDFs s
o permitidos.")

        try:
            file_bytes = await file.read()
            file_bytes_b64 = base64.b64encode(file_bytes).decode("utf-8")
            
            # Extrair a chave do documento do nome do arquivo (ex: "rg_documento.pdf" -> "rg")
            document_key = file.filename.split('_')[0] if '_' in file.filename else file.filename

            job = rq_queue.enqueue(process_single_document_task, file_bytes_b64, file.content_type)
            job_ids.append({"document_key": document_key, "filename": file.filename, "job_id": job.id})

        except Exception as e:
            document_key = file.filename.split('_')[0] if '_' in file.filename else file.filename
            print(f"Erro ao enfileirar {file.filename}: {str(e)}")
            job_ids.append({"document_key": document_key, "filename": file.filename, "job_id": None, "error": str(e)})

    return JSONResponse(content={
        "message": "Documentos enfileirados para processamento.",
        "jobs": job_ids
    }, status_code=202)

# --- Endpoint para verificar o status de um job RQ ---
@app.get("/api/v1/ocr/job-status/{job_id}", tags=["OCR"])
async def get_job_status(job_id: str):
    """
    Verifica o status de um job de processamento de OCR enfileirado.
    """
    try:
        job = rq_queue.fetch_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job não encontrado.")
        
        status = job.get_status()
        result = job.result # O resultado da tarefa, se concluída

        response_content = {
            "job_id": job.id,
            "status": status,
            "result": result if status == "finished" else None,
            "error": job.exc_info if status == "failed" else None
        }
        return JSONResponse(content=response_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar status do job: {str(e)}")

# --- Uvicorn Runner ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)