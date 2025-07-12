import os
import redis
from rq import Worker, Queue, Connection
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração do Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Define as filas que este worker irá escutar
listen = ['default']

conn = redis.from_url(REDIS_URL)

if __name__ == '__main__':
    print(f"Iniciando worker RQ, escutando as filas: {', '.join(listen)}")
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()