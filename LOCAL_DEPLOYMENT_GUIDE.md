# Guia de Deploy e Teste Local

Este guia detalha os passos para configurar e testar localmente o sistema de OCR com FastAPI, RQ, Doctr e LLM.

---

## Pré-requisitos:

*   **Python 3.9+** e `pip` instalados.
*   **Docker Desktop** (ou Docker Engine) instalado e rodando (para o Redis).
*   **Node.js e npm/yarn/pnpm** (para o frontend, se for testar a integração completa).

---

## Passo a Passo:

### **Passo 1: Configurar o Backend**

1.  **Navegue até o diretório `backend`:**
    ```bash
    cd D:\DEV VIBE CODE\SAAS CADASTRO WALKS\walks-cadastro-ocr-finalizado-auth-v1.0 - historico\walks-cadastro-ocr-finalizado-auth-v1.0 - historico\backend
    ```

2.  **Crie o arquivo `.env`:**
    Crie um arquivo chamado `.env` dentro do diretório `backend` com o seguinte conteúdo:
    ```
    GROQ_API_KEY="SUA_CHAVE_API_GROQ_AQUI"
    REDIS_URL="redis://localhost:6379/0"
    ```
    *Substitua `SUA_CHAVE_API_OPENAI_AQUI` pela sua chave de API real da OpenAI.*

3.  **Instale as dependências Python:**
    ```bash
    pip install -r requirements.txt
    ```

---

### **Passo 2: Iniciar o Servidor Redis (usando Docker)**

1.  **Abra um novo terminal** (mantenha o terminal do Passo 1 aberto).
2.  **Inicie o contêiner Redis:**
    ```bash
    docker run -d --name walks-bank-redis -p 6379:6379 redis/redis-stack-server:latest
    ```
    *Aguarde alguns segundos para o Redis iniciar.*

---

### **Passo 3: Iniciar o Worker do RQ**

1.  **Abra outro novo terminal** (total de 3 terminais agora).
2.  **Navegue até o diretório `backend`:**
    ```bash
    cd D:\DEV VIBE CODE\SAAS CADASTRO WALKS\walks-cadastro-ocr-finalizado-auth-v1.0 - historico\walks-cadastro-ocr-finalizado-auth-v1.0 - historico\backend
    ```
3.  **Inicie o worker do RQ:**
    ```bash
    python worker.py
    ```
    *Você verá mensagens indicando que o worker está escutando a fila.*

---

### **Passo 4: Iniciar a Aplicação FastAPI**

1.  **Abra mais um novo terminal** (total de 4 terminais).
2.  **Navegue até o diretório `backend`:**
    ```bash
    cd D:\DEV VIBE CODE\SAAS CADASTRO WALKS\walks-cadastro-ocr-finalizado-auth-v1.0 - historico\walks-cadastro-ocr-finalizado-auth-v1.0 - historico\backend
    ```
3.  **Inicie a aplicação FastAPI:**
    ```bash
    uvicorn main:app --reload
    ```
    *Aguarde as mensagens de inicialização. A primeira vez que o `doctr` carregar, pode levar alguns minutos.*

---

### **Passo 5: Testar o Backend**

1.  **Verificar Health Check:**
    Abra seu navegador e acesse: `http://localhost:8000/health`
    Você deve ver um JSON como `{"status":"ok","redis":"connected","llm_api_key":"configured"}`.

2.  **Acessar a Documentação da API (Swagger UI):**
    Abra seu navegador e acesse: `http://localhost:8000/docs`
    Aqui você pode ver os endpoints disponíveis e testá-los.

3.  **Testar o Endpoint de Processamento de Documentos:**
    *   Na página do Swagger UI (`/docs`), expanda o endpoint `POST /api/v1/ocr/process-documents`.
    *   Clique em "Try it out".
    *   Clique em "Choose File" para selecionar uma ou mais imagens (RG, CNPJ, etc.) ou PDFs do seu computador.
    *   Clique em "Execute".
    *   A resposta deve ser um `202 Accepted` com uma lista de `job_ids`.

4.  **Verificar o Status do Job:**
    *   Copie um dos `job_id`s da resposta do passo anterior.
    *   No Swagger UI, expanda o endpoint `GET /api/v1/ocr/job-status/{job_id}`.
    *   Clique em "Try it out".
    *   Cole o `job_id` no campo `job_id`.
    *   Clique em "Execute".
    *   Você pode precisar consultar este endpoint várias vezes até que o `status` mude para `"finished"`. Quando estiver `"finished"`, o `result` conterá o JSON extraído.

---

### **Passo 6: Iniciar o Frontend (Opcional, para teste completo)**

1.  **Abra um novo terminal** (total de 5 terminais).
2.  **Navegue até o diretório raiz do seu projeto** (onde está o `package.json`):
    ```bash
    cd D:\DEV VIBE CODE\SAAS CADASTRO WALKS\walks-cadastro-ocr-finalizado-auth-v1.0 - historico\walks-cadastro-ocr-finalizado-auth-v1.0 - historico
    ```
3.  **Instale as dependências Node.js:**
    ```bash
    npm install # ou yarn install, ou pnpm install
    ```
4.  **Inicie o aplicativo Next.js:**
    ```bash
    npm run dev # ou yarn dev, ou pnpm dev
    ```
5.  **Acesse o Frontend:**
    Abra seu navegador e acesse: `http://localhost:3000` (ou a porta que o Next.js indicar).
    Agora você pode testar a integração completa do frontend com o backend.

---

**Observações Importantes:**

*   **Consumo de Recursos:** O `doctr` e a LLM consomem bastante CPU e memória. Seu computador pode ficar lento durante o processamento.
*   **Primeira Execução:** A primeira vez que o `doctr` carregar os modelos (tanto no FastAPI quanto no worker do RQ), levará mais tempo, pois ele precisa baixá-los.
*   **Logs:** Fique de olho nos logs de cada terminal para depurar qualquer problema.
