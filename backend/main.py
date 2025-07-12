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
    Recebe múltiplos documentos, enfileira-os para processamento assíncrono com Doctr e LLM.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    job_ids = []
    for file in files:
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"Tipo de arquivo inválido para {file.filename}. Apenas imagens são permitidas.")

        try:
            image_bytes = await file.read()
            # Codifica a imagem em base64 para passar para a tarefa RQ
            image_bytes_b64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # Enfileira a tarefa no RQ
            job = rq_queue.enqueue(process_single_document_task, image_bytes_b64)
            job_ids.append({"filename": file.filename, "job_id": job.id})

        except Exception as e:
            # Se houver um erro ao enfileirar um arquivo, registra e continua com os outros
            print(f"Erro ao enfileirar {file.filename}: {str(e)}")
            job_ids.append({"filename": file.filename, "job_id": None, "error": str(e)})

    return JSONResponse(content={
        "message": "Documentos enfileirados para processamento.",
        "job_ids": job_ids
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