
import os
import redis
from rq import Worker, Queue
from redis import Redis

redis_conn = Redis()  # Usa localhost:6379 por padrão
queue = Queue(connection=redis_conn)
worker = Worker([queue], connection=redis_conn)
worker.work()

# Carrega variáveis de ambiente do arquivo .env
from dotenv import load_dotenv
load_dotenv()

# Configuração do Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Conecta ao Redis
conn = redis.from_url(REDIS_URL)

# Define as filas que este worker irá escutar
# Você pode ter múltiplas filas e workers escutando filas diferentes
listen = ['default']

if __name__ == '__main__':
    print(f"Iniciando worker RQ, escutando as filas: {', '.join(listen)}")
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
